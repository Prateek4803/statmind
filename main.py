"""
StatMind v2.0 — Final Production Entry Point
All refinements: R1 (universal parser) + R2 (expanded CAPA) + R3 (SPC subrange)
Run: python main.py  OR  uvicorn main:app --port 8010

FIXES APPLIED (P0/P1/P2 audit items):
  P0-SEC-1   File upload size capped at MAX_UPLOAD_MB (default 25 MB).
             Prevents memory exhaustion from large uploads.
  P0-SEC-2   Bounded report cache (_ReportCache) with TTL eviction.
             Old dict grew without bound — would OOM on long-running server.
  P0-ARCH-1  All module imports hoisted to top of file.
             Previous pattern imported logistic_regression, pca_advanced,
             attribute_charts, statmind_intelligence, hypothesis inside
             route handlers on every request — paid import cost each call,
             hid ImportErrors until runtime, caused misleading 500s.
  P1-STAT-1  /api/v1/health added as alias (required by CI coverage check
             and Dockerfile HEALTHCHECK).
  P2-ARCH-1  control_charts: analyze_control_chart aliased correctly to
             auto_select_and_build (function was renamed in v3 engine).
  P0-STAT-6  Anderson-Darling reimplemented internally (normality.py) —
             scipy.stats.anderson API removed in SciPy 1.19 would hard-break
             the normality engine on the next dependency bump.
  P0-STAT-7  subgroup_size=0 caused ZeroDivisionError → 500 in capability;
             now bounded at API layer (ge=1, le=100) and engine layer.
  P1-SEC-3   Shared limiter (rate_limit.py); strict per-route limits on auth
             endpoints (magic-link 3/min — was 60/min, enough to burn the
             entire Resend daily quota and DoS login for all users).
  P1-SEC-4   Real email validation + length caps; per-email pending-token
             throttle; email-capture dedup (unbounded PII table growth).
  P1-SEC-5   Content-Security-Policy header added.
  P1-VAL-1   alpha query params bounded to (0, 1) on all 6 endpoints.
"""

import os
import json
import uuid
import time
import tempfile
import dataclasses
import re
import html as html_lib
import asyncio
import logging
import threading

import numpy as np
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request, Form
from auth import auth_router
from ppap_generator import ppap_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# ── Statistical engines (hoisted — P0-ARCH-1) ─────────────────────────────────
from file_parser    import parse_any_file
from normality      import analyze_column
from capability     import analyze_capability
from control_charts import auto_select_and_build as analyze_control_chart
from gauge_rr       import analyze_gauge_rr, parse_grr_csv
from recommendations import recommend_next_step
from ai_explainer import explain_result
from capa_rules_engine import (
    run_capa_engine, run_capa_engine_v2,
    get_capa_for_rule, get_all_rules_catalog,
    get_all_rules_catalog_v2, _extract_stats,
)
from pdf_report          import generate_report
from logistic_regression import analyze_logistic, stepwise_regression
from pca_advanced        import analyze_pca, scatter_matrix
from attribute_charts    import build_p_chart, build_np_chart, build_u_chart, build_c_chart
from statmind_intelligence import generate_intelligence_report
from hypothesis          import two_sample_t
from report_cache        import ReportCache

# ── Configuration ─────────────────────────────────────────────────────────────
PORT           = int(os.getenv("PORT", 8010))
ENV            = os.getenv("ENV") or os.getenv("ENVIRONMENT", "development")
IS_PROD        = ENV.lower() in ("production", "prod")
_default_origins = "https://statmind.tech,https://www.statmind.tech" if IS_PROD else "*"
ORIGINS        = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]
MAX_UPLOAD_MB  = int(os.getenv("MAX_UPLOAD_MB", 25))      # P0-SEC-1
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
CACHE_TTL_SEC  = int(os.getenv("REPORT_CACHE_TTL", 3600)) # 1 hour default
CACHE_MAX_ITEMS = int(os.getenv("REPORT_CACHE_MAX", 200))

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="StatMind",
    description="Process Statistics Engine — Universal measurement analysis",
    version="2.0.0",
    docs_url=None if IS_PROD else "/api/docs",
    redoc_url=None if IS_PROD else "/api/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)

# ── Rate limiting ──────────────────────────────────────────────────────────────
# Shared limiter (rate_limit.py) so auth.py and other routers can declare
# per-route limits on the same instance (P1-SEC-3).
from rate_limit import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# P2-UX-2 (2026-07-06 campaign): endpoints reading `await request.json()` raised
# an unhandled JSONDecodeError -> 500 on malformed/empty bodies. One handler
# fixes every such endpoint at once.
from json import JSONDecodeError as _JSONDecodeError
from fastapi.responses import JSONResponse as _JSONResponse

@app.exception_handler(_JSONDecodeError)
async def _bad_json_handler(request, exc):
    return _JSONResponse(status_code=400, content={
        "detail": "Request body must be valid JSON (Content-Type: application/json)."
    })
# SlowAPIMiddleware makes default_limits apply to EVERY route — without it,
# slowapi only enforces limits on handlers that declare a `request: Request`
# param, leaving file-upload endpoints that omit it completely unthrottled.
app.add_middleware(SlowAPIMiddleware)

# ── Database init (deferred, non-fatal) ───────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    try:
        from database import init_db
        init_db()
    except Exception as e:
        logging.warning(f"DB startup skipped: {e}")

# MES router — loaded only when DATABASE_URL is a real external DB
_db_url = os.getenv("DATABASE_URL", "")
if _db_url and _db_url not in ("", "sqlite:///./statmind_dev.db"):
    try:
        from routers import mes
        app.include_router(mes.router)
        logging.info("MES router loaded")
    except Exception as _mes_err:
        logging.warning(f"MES router not loaded: {_mes_err}")

app.include_router(auth_router)
app.include_router(ppap_router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(
        "Unhandled %s on %s %s",
        type(exc).__name__, request.method, request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal error occurred while processing your request. "
                      "Your data was not stored. Please check your input and retry.",
            "type": type(exc).__name__,
        },
    )

# ── Security helpers ───────────────────────────────────────────────────────────
# Allowlist: only the formats parse_any_file actually supports. An allowlist
# is safer than a blocklist — anything not explicitly parseable is rejected
# up front, rather than blocklisting a never-complete set of dangerous types.
_ALLOWED_EXT = {"csv", "tsv", "txt", "xlsx", "xls"}

def _validate_upload(file: UploadFile, content: bytes) -> None:
    """
    Reject dangerous file types and oversized uploads (P0-SEC-1).
    Pass pre-read content bytes so size can be checked without re-reading.
    """
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            400,
            f"File type '.{ext}' is not supported. Allowed: "
            f"{', '.join('.' + e for e in sorted(_ALLOWED_EXT))}.",
        )
    # Light content sniffing: reject files whose bytes look like an executable
    # or script regardless of extension (defends against a renamed binary).
    head = content[:8]
    _BAD_MAGIC = (
        b"MZ",            # Windows PE/exe
        b"\x7fELF",       # Linux ELF
        b"\xca\xfe\xba\xbe",  # Mach-O
        b"PK\x03\x04",    # zip (xlsx is zip-based, so only block for text exts)
    )
    if ext in {"csv", "tsv", "txt"} and any(head.startswith(m) for m in _BAD_MAGIC):
        raise HTTPException(400, "File content does not look like text data.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"File too large ({len(content) // 1024 // 1024} MB). "
            f"Maximum allowed: {MAX_UPLOAD_MB} MB."
        )


def _parse_upload(content: bytes, filename: str):
    """Validate an uploaded file's bytes, then parse to a pandas DataFrame.

    Used by the analysis endpoints that operate directly on a DataFrame
    (weibull, pca, logistic, boxplot, msa/linearity). Routes through
    parse_any_file (which enforces the allowlist + size cap via the caller's
    _validate_upload) and returns the parsed .df. Centralizing this here also
    closes the prior bug where these endpoints used an undefined helper and
    skipped upload validation.
    """
    # Enforce the same size cap the other endpoints use.
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"File too large ({len(content) // 1024 // 1024} MB). "
            f"Maximum allowed: {MAX_UPLOAD_MB} MB."
        )
    ext = (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""
    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            400,
            f"File type '.{ext}' is not supported. Allowed: "
            f"{', '.join('.' + e for e in sorted(_ALLOWED_EXT))}.",
        )
    result = parse_any_file(content, filename)
    return result.df


def _sanitize_text(text: str, max_len: int = 5000) -> str:
    """Sanitize user text — strip HTML and cap length."""
    if not text:
        return ""
    # Strip HTML and cap length. We deliberately do NOT attempt regex-based
    # "prompt-injection filtering" — such filters are trivially bypassed and give
    # false confidence. The real defense is the grounding layer (ai_explainer),
    # which only ever sends the model verified scalar facts, never free user text.
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", text))
    return text[:max_len]


# ── Bounded report cache with TTL eviction (P0-SEC-2) ─────────────────────────

class _ReportCache:
    """
    Thread-safe in-memory report cache with:
      - Per-entry TTL expiry (default 1 hour)
      - Hard cap on number of entries (default 200)
      - LRU-style eviction when cap is reached
      - Background cleanup thread (runs every 5 minutes)

    Replaces the previous unbounded dict `_report_cache: dict = {}` which
    would accumulate file paths indefinitely on a long-running server.
    """

    def __init__(self, ttl: int = CACHE_TTL_SEC, maxsize: int = CACHE_MAX_ITEMS):
        self._store: dict[str, tuple[str, float]] = {}  # id → (path, expires_at)
        self._lock  = threading.Lock()
        self._ttl   = ttl
        self._max   = maxsize
        self._start_cleanup_thread()

    def set(self, report_id: str, path: str) -> None:
        with self._lock:
            self._evict_expired()
            if len(self._store) >= self._max:
                # Remove oldest entry
                oldest = min(self._store.items(), key=lambda kv: kv[1][1])
                self._delete_entry(oldest[0])
            self._store[report_id] = (path, time.monotonic() + self._ttl)

    def get(self, report_id: str) -> str | None:
        with self._lock:
            entry = self._store.get(report_id)
            if entry is None:
                return None
            path, expires_at = entry
            if time.monotonic() > expires_at:
                self._delete_entry(report_id)
                return None
            return path

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            self._delete_entry(k)

    def _delete_entry(self, report_id: str) -> None:
        entry = self._store.pop(report_id, None)
        if entry:
            path = entry[0]
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    def _start_cleanup_thread(self) -> None:
        def _loop():
            while True:
                time.sleep(300)  # every 5 minutes
                try:
                    with self._lock:
                        self._evict_expired()
                except Exception:
                    pass
        t = threading.Thread(target=_loop, daemon=True)
        t.start()


_report_cache = ReportCache(ttl=CACHE_TTL_SEC, maxsize=CACHE_MAX_ITEMS)

# ── JSON helpers ───────────────────────────────────────────────────────────────
class NpEnc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, np.integer):  return int(o)
        if isinstance(o, np.floating): return float(o)
        if isinstance(o, np.ndarray):  return o.tolist()
        if isinstance(o, np.bool_):    return bool(o)
        return super().default(o)


def _json_safe(o):
    """Recursively replace inf/-inf/NaN with None so output is valid JSON."""
    import math as _math
    if isinstance(o, float):
        if _math.isinf(o) or _math.isnan(o): return None
        return o
    if isinstance(o, dict):  return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [_json_safe(v) for v in o]
    return o

def jd(d):   return JSONResponse(content=_json_safe(json.loads(json.dumps(d, cls=NpEnc))))
def jobj(o): return jd(dataclasses.asdict(o))

def _with_next_step(d: dict, analysis_type: str, *, in_control=None, normality_verdict=None) -> dict:
    """Attach a single next-step recommendation to a result dict (in place).
    Safe: never raises into the response."""
    try:
        _min = d.get("min_val")
        _all_positive = (_min is not None and _min > 0)
        ns = recommend_next_step(
            analysis_type,
            verdict=d.get("verdict") or d.get("overall_verdict"),
            in_control=in_control if in_control is not None else d.get("in_control"),
            normality_verdict=normality_verdict,
            all_positive=_all_positive if d.get("min_val") is not None else None,
        )
        if ns is not None:
            d["next_step"] = ns.to_dict()
    except Exception:
        pass
    return d

# ── Security headers middleware ────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["X-XSS-Protection"]        = "1; mode=block"
    response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]      = "geolocation=(), microphone=(), camera=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # P1-SEC-5: CSP. The SPA uses inline scripts/styles, so 'unsafe-inline' is
    # required for now, but this still blocks: injected external scripts from
    # any origin except jsdelivr (Chart.js), plugin/object embeds, form posts
    # to foreign origins, and framing (defense-in-depth with X-Frame-Options).
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    return response

# ── Health endpoints ───────────────────────────────────────────────────────────
def _health_payload() -> dict:
    return {
        "status":    "ok",
        "service":   "StatMind",
        "version":   "2.0.0",
        "release":   os.getenv("RELEASE_SHA", "unknown"),  # Session 6: deploy verifies new code is serving
        "env":       ENV,
        "sessions":  ["normality", "capability", "spc", "grr", "capa", "pdf"],
        "capa_rules": 31,
    }

@app.get("/health")
def health_legacy():
    """Legacy health endpoint — kept for backwards compatibility."""
    return _health_payload()

@app.get("/api/v1/health")
def health():
    """Primary health endpoint (required by CI coverage check + Dockerfile)."""
    return _health_payload()

# ── Column detection ───────────────────────────────────────────────────────────
@app.post("/api/v1/columns")
@limiter.limit("30/minute")
async def get_columns(request: Request, file: UploadFile = File(...)):
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    stats_map = {cs.name: cs for cs in result.column_stats}
    cols = []
    for col in result.numeric_columns:
        d  = result.df[col].dropna().values.astype(float)
        cs = stats_map.get(col)
        cols.append({
            "name":        col,
            "n":           int(len(d)),
            "mean":        round(float(d.mean()), 4)      if len(d)     else 0,
            "std":         round(float(d.std(ddof=1)), 4) if len(d) > 1 else 0,
            "min":         round(float(d.min()), 4)       if len(d)     else 0,
            "max":         round(float(d.max()), 4)       if len(d)     else 0,
            "n_missing":   cs.n_missing   if cs else 0,
            "pct_missing": cs.pct_missing if cs else 0.0,
        })
    return jd({
        "columns":       cols,
        "source_format": result.source_format,
        "metadata":      result.metadata,
        "warnings":      result.warnings,
        "n_rows":        result.n_rows,
    })


@app.post("/api/v1/aaa/columns")
@limiter.limit("30/minute")
async def get_aaa_columns(request: Request, file: UploadFile = File(...)):
    """All columns (numeric + categorical) for Attribute Agreement Analysis."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    return jd({
        "all_columns":     list(result.all_columns),
        "numeric_columns": list(result.numeric_columns),
        "n_rows":          result.n_rows,
    })

# ── Session 1: Normality ───────────────────────────────────────────────────────
@app.post("/api/v1/normality/analyze")
@limiter.limit("30/minute")
async def normality(request: Request, file: UploadFile = File(...), alpha: float = Query(0.05, gt=0.0, lt=1.0)):
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    results, errors = [], []
    for col in result.numeric_columns:
        try:
            _r = dataclasses.asdict(
                analyze_column(result.df[col].dropna().values.astype(float), col, alpha)
            )
            results.append(_with_next_step(_r, "normality"))
        except Exception as e:
            errors.append({"column": col, "error": str(e)})
    return jd({
        "filename":          file.filename,
        "rows":              result.n_rows,
        "columns_analyzed":  len(results),
        "alpha":             alpha,
        "source_format":     result.source_format,
        "metadata":          result.metadata,
        "results":           results,
        "errors":            errors,
    })

# ── Session 2: Capability ──────────────────────────────────────────────────────
@app.post("/api/v1/capability/analyze")
@limiter.limit("20/minute")
async def capability(
    request: Request,
    file: UploadFile = File(...),
    column: str         = Query(...),
    usl: float          = Query(...),
    lsl: float          = Query(...),
    target: float       = Query(None),
    subgroup_size: int  = Query(1, ge=1, le=100),
):
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found. Available: {result.numeric_columns}")
    try:
        cap = await asyncio.to_thread(
            analyze_capability,
            result.df[column].dropna().values.astype(float),
            column, usl, lsl, target, subgroup_size,
        )
        return jd(_with_next_step(dataclasses.asdict(cap), "capability"))
    except ValueError as e:
        raise HTTPException(400, str(e))

# ── Session 3: SPC ─────────────────────────────────────────────────────────────
@app.post("/api/v1/spc/analyze")
async def spc(
    file: UploadFile  = File(...),
    column: str       = Query(...),
    subgroup_size: int = Query(1, ge=1, le=100),
    start_index: int  = Query(None),
    end_index: int    = Query(None),
):
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data = result.df[column].dropna().values.astype(float)
    total_points = len(data)

    if start_index is not None and end_index is not None:
        start_index = max(0, start_index)
        end_index   = min(total_points, end_index)
        data = data[start_index:end_index]

    try:
        # auto_select_and_build() already returns a plain dict of native types.
        # Wrapping it in dataclasses.asdict() raised
        # "asdict() should be called on dataclass instances".
        spc_result = await asyncio.to_thread(
            analyze_control_chart, data, column, subgroup_size
        )
        if dataclasses.is_dataclass(spc_result):
            spc_result = dataclasses.asdict(spc_result)
        spc_result["subrange"] = {
            "start":            start_index,
            "end":              end_index,
            "total_points":     total_points,
            "selected_points":  len(data),
        }
        return jd(_with_next_step(spc_result, "spc"))
    except ValueError as e:
        raise HTTPException(400, str(e))

# ── Session 4: Gauge R&R ───────────────────────────────────────────────────────
@app.post("/api/v1/grr/analyze")
async def grr_analyze(
    file: UploadFile    = File(...),
    tolerance: float    = Query(None),
    method: str         = Query("ANOVA"),
    column: str         = Query(None, max_length=100, description="Measurement column (required if the file has several numeric candidates)"),
):
    c = await file.read()
    _validate_upload(file, c)
    try:
        measurements, parts, operators, col_name = parse_grr_csv(c, file.filename, measurement_col=column)
    except Exception as e:
        raise HTTPException(400, str(e))
    try:
        grr = await asyncio.to_thread(
            analyze_gauge_rr, measurements, parts, operators, col_name, tolerance, method
        )
        return jd(_with_next_step(dataclasses.asdict(grr), "grr"))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/grr/preview")
async def grr_preview(file: UploadFile = File(...), column: str = Query(None, max_length=100)):
    c = await file.read()
    _validate_upload(file, c)
    try:
        measurements, parts, operators, col_name = parse_grr_csv(c, file.filename, measurement_col=column)
    except Exception as e:
        raise HTTPException(400, str(e))
    return jd({
        "n_measurements": len(measurements),
        "n_parts":        len(set(parts)),
        "n_operators":    len(set(operators)),
        "column":         col_name,
        "sample_values":  measurements[:10].tolist(),
    })

# ── Session 5: CAPA ────────────────────────────────────────────────────────────
@app.post("/api/v1/explain")
async def explain(request: Request):
    """Grounded AI explanation of a computed analysis result. The LLM only
    narrates verified numbers; it never recomputes or decides. Degrades
    gracefully on provider rate-limit/unavailability. Privacy: only the
    computed scalar summary is sent to the provider, never raw data."""
    body = await request.json()
    analysis_type = body.get("analysis_type", "")
    result = body.get("result", {})
    question = body.get("question")

    if not analysis_type or not isinstance(result, dict):
        raise HTTPException(400, "analysis_type and result are required.")

    if question and len(str(question)) > 500:
        question = str(question)[:500]

    res = await asyncio.to_thread(
        explain_result, analysis_type, result, question, max_tokens=1500
    )

    if res.ok:
        return jd({"ok": True, "explanation": res.text, "provider": res.provider})

    if res.error == "rate_limited":
        return jd({"ok": False, "reason": "rate_limited",
                   "message": "The AI explainer is busy right now (free-tier "
                              "limit). Please try again in a minute."})
    if res.error == "temporarily_unavailable":
        return jd({"ok": False, "reason": "unavailable",
                   "message": "The AI explainer is temporarily unavailable. "
                              "Please try again shortly."})
    return jd({"ok": False, "reason": "unavailable",
               "message": "AI explanation isn't available for this result "
                          "right now."})


@app.post("/api/v1/capa/generate")
async def capa_generate(request: Request):
    body = await request.json()
    try:
        result = run_capa_engine(
            stats         = body.get("stats", {}),
            process_type  = body.get("process_type", "General"),
            parameter_name= body.get("parameter_name", "Parameter"),
        )
        return jd(result)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/capa/v2/generate")
async def capa_v2_generate(request: Request):
    body = await request.json()
    try:
        result = await asyncio.to_thread(
            run_capa_engine_v2,
            capability_result = body.get("capability_result"),
            spc_result        = body.get("spc_result"),
            normality_result  = body.get("normality_result"),
            grr_result        = body.get("grr_result"),
            process_type      = body.get("process_type", "General"),
            parameter_name    = body.get("parameter_name", "Parameter"),
        )
        return jd(result)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/capa/override")
@app.post("/api/v1/capa/v2/override")
async def capa_override(request: Request):
    body = await request.json()
    try:
        stats = _extract_stats(
            body.get("normality_result"),
            body.get("capability_result"),
            body.get("spc_result"),
            body.get("grr_result"),
        )
        result = get_capa_for_rule(
            body.get("rule_id", ""),
            stats,
            body.get("process_context", body.get("process_type", "General")),
            body.get("parameter_name", "Parameter"),
        )
        return jd(result)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/v1/capa/catalog")
async def capa_catalog():
    return jd(get_all_rules_catalog())

@app.get("/api/v1/capa/processes")
async def capa_processes():
    """Process selector metadata: every process tag in the rule library with
    its rule count, grouped by industry category. Honest counts — thin
    processes show their real numbers rather than hiding them."""
    from capa_process_filter import list_processes
    return jd({"groups": list_processes()})

@app.get("/api/v1/capa/rules")
async def capa_rules_by_process(
    process: str = Query(..., min_length=1, max_length=40),
    include_general: bool = Query(True),
):
    """Hard-filtered rule list for one process tag (e.g. Etch, CMP) — powers
    the re-filter dropdown in the CAPA rules section. Cross-cutting General
    rules are included by default and tagged scope='general'."""
    from capa_process_filter import get_rules_by_process
    rules = get_rules_by_process(process, include_general=include_general)
    n_process = sum(1 for r in rules if r.get("scope") == "process")
    return jd({"process": process, "count": len(rules),
               "process_rule_count": n_process, "rules": rules})

@app.get("/api/v1/capa/v2/catalog")
async def capa_v2_catalog():
    return jd(get_all_rules_catalog_v2())

# ── Session 6: PDF Report ──────────────────────────────────────────────────────
@app.post("/api/v1/report/generate")
async def generate_pdf_report(request: Request):
    body = await request.json()
    report_id = str(uuid.uuid4())[:8]
    tmp_path  = os.path.join(tempfile.gettempdir(), f"statmind_report_{report_id}.pdf")
    meta = body.get("meta", {})
    meta.setdefault("parameter", body.get("parameter_name", "Process Parameter"))
    meta.setdefault("process",   body.get("process_type", "N/A"))
    try:
        await asyncio.to_thread(
            generate_report,
            tmp_path,
            normality_result  = body.get("normality_result"),
            capability_result = body.get("capability_result"),
            spc_result        = body.get("spc_result"),
            grr_result        = body.get("grr_result"),
            capa_result       = body.get("capa_result"),
            meta              = meta,
        )
        _report_cache.set(report_id, tmp_path)   # bounded cache (P0-SEC-2)
        size_kb  = round(os.path.getsize(tmp_path) / 1024)
        sections = sum(1 for k in [
            "normality_result", "capability_result",
            "spc_result", "grr_result", "capa_result",
        ] if body.get(k))
        return jd({
            "success":           True,
            "report_id":         report_id,
            "download_url":      f"/api/v1/report/download/{report_id}",
            "size_kb":           size_kb,
            "sections_included": sections,
        })
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {str(e)}")

@app.post("/api/v1/export/xlsx")
@limiter.limit("10/minute")
async def export_session_xlsx(request: Request):
    """Export a saved session (the frontend's snapshot object) as a formatted
    Excel dashboard. Built entirely in memory and streamed back — nothing is
    written to disk, consistent with the privacy policy."""
    body = await request.json()
    session = body.get("session") or body
    name = re.sub(r"[^A-Za-z0-9 _.\-]", "", str(body.get("name") or "statmind_session")).lstrip(". ")[:60] or "statmind_session"
    try:
        from xlsx_export import build_session_workbook
        buf = await asyncio.to_thread(build_session_workbook, session)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        logging.exception("xlsx export failed")
        raise HTTPException(500, "Excel export failed. Your data was not stored.")
    headers = {"Content-Disposition": f'attachment; filename="{name}.xlsx"'}
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.get("/api/v1/report/download/{report_id}")
async def download_report(report_id: str):
    # Sanitise report_id — alphanumeric + hyphens only
    if not re.match(r"^[a-f0-9\-]{8,36}$", report_id):
        raise HTTPException(400, "Invalid report ID.")
    path = _report_cache.get(report_id)
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Report not found or expired. Please regenerate.")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"statmind_report_{report_id}.pdf",
    )


def _all_cols_response(result):
    return jd({
        "all_columns":     list(result.all_columns),
        "numeric_columns": list(result.numeric_columns),
        "n_rows":          result.n_rows,
    })


@app.post("/api/v1/regression/analyze")
@limiter.limit("30/minute")
async def regression_analyze(request: Request, file: UploadFile = File(...), y_col: str = Query(...), x_cols: str = Query(...), alpha: float = Query(0.05, gt=0.0, lt=1.0)):
    c = await file.read(); _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    xs = [x.strip() for x in x_cols.split(",") if x.strip()]
    for col in [y_col] + xs:
        if col not in result.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    try:
        import regression as R
        y = result.df[y_col].values.astype(float)
        if len(xs) == 1:
            res = await asyncio.to_thread(R.simple_linear_regression, result.df[xs[0]].values.astype(float), y, xs[0], y_col, alpha)
        else:
            res = await asyncio.to_thread(R.multiple_regression, result.df[xs].values.astype(float), y, xs, y_col, alpha)
        return jd(dataclasses.asdict(res) if dataclasses.is_dataclass(res) else res)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/doe/generate")
@limiter.limit("30/minute")
async def doe_generate(request: Request):
    b = await request.json()
    try:
        import doe as D
        res = await asyncio.to_thread(D.generate_design, b["factor_names"], b["factor_levels"], b.get("design_type", "auto"), None)
        return jd(dataclasses.asdict(res) if dataclasses.is_dataclass(res) else res)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/doe/analyze")
@limiter.limit("30/minute")
async def doe_analyze(request: Request):
    b = await request.json()
    try:
        import doe as D
        res = await asyncio.to_thread(D.generate_design, b["factor_names"], b["factor_levels"], b.get("design_type", "auto"), b.get("responses"))
        return jd(dataclasses.asdict(res) if dataclasses.is_dataclass(res) else res)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/multivari/columns")
@limiter.limit("30/minute")
async def multivari_columns(request: Request, file: UploadFile = File(...)):
    c = await file.read(); _validate_upload(file, c)
    try:
        return _all_cols_response(parse_any_file(c, file.filename))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/multivari/analyze")
@limiter.limit("30/minute")
async def multivari_analyze(request: Request, file: UploadFile = File(...), value_col: str = Query(...), part_col: str = Query(...), position_col: str = Query(None), time_col: str = Query(None)):
    c = await file.read(); _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    for col in [value_col, part_col, position_col, time_col]:
        if col and col not in result.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    try:
        import multivari as M
        df = result.df
        res = await asyncio.to_thread(M.analyze_multivari, df[value_col].values.astype(float), df[part_col].values, df[position_col].values if position_col else None, df[time_col].values if time_col else None, value_col)
        return jd(dataclasses.asdict(res) if dataclasses.is_dataclass(res) else res)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/pareto/columns")
@limiter.limit("30/minute")
async def pareto_columns(request: Request, file: UploadFile = File(...)):
    c = await file.read(); _validate_upload(file, c)
    try:
        # Pareto accepts short categorical files (P1-VAL-2): 2+ numeric values
        # qualify a count column, and a category-only event log needs none.
        return _all_cols_response(parse_any_file(c, file.filename, min_numeric=2, require_numeric=False))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/pareto/analyze")
@limiter.limit("30/minute")
async def pareto_analyze(request: Request, file: UploadFile = File(...), category_col: str = Query(...), count_col: str = Query(None), threshold: float = Query(80.0)):
    c = await file.read(); _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename, min_numeric=2, require_numeric=False)
    except Exception as e:
        raise HTTPException(400, str(e))
    for col in [category_col, count_col]:
        if col and col not in result.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    try:
        import pareto as P
        df = result.df
        cats = df[category_col].astype(str).tolist()
        counts = df[count_col].values.astype(float).tolist() if count_col else None
        res = await asyncio.to_thread(P.analyze_pareto, cats, counts, f"{category_col} Pareto", threshold)
        return jd(dataclasses.asdict(res) if dataclasses.is_dataclass(res) else res)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/comparison/analyze")
@limiter.limit("30/minute")
async def comparison_analyze(request: Request):
    b = await request.json()
    try:
        from routers.comparison import compare_datasets
        import numpy as _np
        datasets = [(d["name"], _np.array(d["values"], dtype=float)) for d in b["datasets"]]
        res = await asyncio.to_thread(compare_datasets, datasets, b.get("parameter", "Measurement"), b.get("usl"), b.get("lsl"), b.get("alpha", 0.05))
        return jd(dataclasses.asdict(res) if dataclasses.is_dataclass(res) else res)
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


# ── Regression ─────────────────────────────────────────────────────────────────
@app.post("/api/v1/regression/logistic")
async def logistic_regression_ep(
    file: UploadFile  = File(...),
    response: str     = Query(...),
    predictors: str   = Query(...),
    threshold: float  = Query(0.5),
):
    c = await file.read()
    _validate_upload(file, c)
    try:
        r = await asyncio.to_thread(parse_any_file, c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    pred_cols = [p.strip() for p in predictors.split(",") if p.strip()]
    for col in [response] + pred_cols:
        if col not in r.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    _yraw = r.df[response].dropna()
    _uniq = sorted(set(_yraw.unique().tolist()))
    if len(_uniq) > 2 or not set(_uniq).issubset({0, 1, 0.0, 1.0}):
        raise HTTPException(400,
            f"Logistic regression needs a binary 0/1 response. '{response}' has "
            f"{len(_uniq)} distinct values — for a continuous response, use Linear Regression instead.")
    y = _yraw.values.astype(int)
    X = r.df[pred_cols].dropna().values.astype(float)
    try:
        result = await asyncio.to_thread(analyze_logistic, X, y, response, pred_cols, threshold)
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/regression/stepwise")
async def stepwise_ep(
    file: UploadFile  = File(...),
    response: str     = Query(...),
    predictors: str   = Query(...),
    method: str       = Query("both"),
    criterion: str    = Query("AIC"),
):
    c = await file.read()
    _validate_upload(file, c)
    try:
        r = await asyncio.to_thread(parse_any_file, c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    pred_cols = [p.strip() for p in predictors.split(",") if p.strip()]
    for col in [response] + pred_cols:
        if col not in r.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    _yraw = r.df[response].dropna()
    _uniq = sorted(set(_yraw.unique().tolist()))
    if len(_uniq) > 2 or not set(_uniq).issubset({0, 1, 0.0, 1.0}):
        raise HTTPException(400,
            f"Stepwise (logistic) regression needs a binary 0/1 response. '{response}' has "
            f"{len(_uniq)} distinct values — for a continuous response, use Linear Regression instead.")
    y = _yraw.values.astype(int)
    X = r.df[pred_cols].dropna().values.astype(float)
    try:
        result = await asyncio.to_thread(stepwise_regression, X, y, response, pred_cols, method, criterion)
        d = dataclasses.asdict(result)
        if d.get("final_model") and hasattr(result.final_model, "__dataclass_fields__"):
            d["final_model"] = dataclasses.asdict(result.final_model)
        return jd(d)
    except Exception as e:
        raise HTTPException(400, str(e))

# ── PCA ─────────────────────────────────────────────────────────────────────────
@app.post("/api/v1/pca/analyze")
async def pca_ep(
    file: UploadFile     = File(...),
    columns: str         = Query(...),
    n_components: int    = Query(None),
    scale: bool          = Query(True),
):
    c = await file.read()
    _validate_upload(file, c)
    try:
        r = await asyncio.to_thread(parse_any_file, c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    cols = [col.strip() for col in columns.split(",") if col.strip()]
    for col in cols:
        if col not in r.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    X = r.df[cols].dropna().values.astype(float)
    try:
        result = await asyncio.to_thread(analyze_pca, X, cols, n_components, scale)
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/pca/scatter-matrix")
async def scatter_matrix_ep(
    file: UploadFile = File(...),
    columns: str     = Query(...),
):
    c = await file.read()
    _validate_upload(file, c)
    try:
        r = await asyncio.to_thread(parse_any_file, c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    cols = [col.strip() for col in columns.split(",") if col.strip()]
    X = r.df[cols].dropna().values.astype(float)
    try:
        result = await asyncio.to_thread(scatter_matrix, X, cols)
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

def _require_fields(body: dict, fields: list, chart: str) -> None:
    """P2-UX-1 (2026-07-06 campaign): missing JSON fields previously leaked raw
    KeyErrors to the user ({"detail": "\'subgroup_size\'"}). Name the field."""
    missing = [f for f in fields if f not in body]
    if missing:
        raise HTTPException(
            400, f"Missing required field(s) for {chart}: {', '.join(missing)}. "
                 f"Required: {', '.join(fields)}."
        )

# ── Attribute charts ───────────────────────────────────────────────────────────
@app.post("/api/v1/attribute-charts/p")
async def p_chart_ep(request: Request):
    body = await request.json()
    _require_fields(body, ["defectives", "subgroup_sizes"], "p-chart")
    try:
        d_arr  = np.array(body["defectives"], dtype=float)
        n_arr  = np.array(body["subgroup_sizes"], dtype=float)
        result = await asyncio.to_thread(build_p_chart, d_arr, n_arr, body.get("column", "Defectives"))
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/attribute-charts/np")
async def np_chart_ep(request: Request):
    body = await request.json()
    _require_fields(body, ["defectives", "subgroup_size"], "np-chart")
    try:
        d_arr  = np.array(body["defectives"], dtype=float)
        n      = int(body["subgroup_size"])
        result = await asyncio.to_thread(build_np_chart, d_arr, n, body.get("column", "Defectives"))
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/attribute-charts/u")
async def u_chart_ep(request: Request):
    body = await request.json()
    _require_fields(body, ["defects", "subgroup_sizes"], "u-chart")
    try:
        d_arr  = np.array(body["defects"], dtype=float)
        n_arr  = np.array(body["subgroup_sizes"], dtype=float)
        result = await asyncio.to_thread(build_u_chart, d_arr, n_arr, body.get("column", "Defects"))
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/attribute-charts/c")
async def c_chart_ep(request: Request):
    body = await request.json()
    _require_fields(body, ["defects"], "c-chart")
    try:
        d_arr  = np.array(body["defects"], dtype=float)
        result = await asyncio.to_thread(build_c_chart, d_arr, body.get("column", "Defects"))
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

# ── Intelligence Engine ────────────────────────────────────────────────────────
@app.post("/api/v1/intelligence/analyse")
async def intelligence_analyse(request: Request):
    b = await request.json()
    for key in ["parameter", "process_type", "lot_id", "tool_id"]:
        if key in b and isinstance(b[key], str):
            b[key] = _sanitize_text(b[key], max_len=200)
    try:
        result = await asyncio.to_thread(
            generate_intelligence_report,
            parameter         = b.get("parameter",  "Parameter"),
            process_type      = b.get("process_type", "General"),
            normality_result  = b.get("normality_result"),
            capability_result = b.get("capability_result"),
            spc_result        = b.get("spc_result"),
            grr_result        = b.get("grr_result"),
            capa_result       = b.get("capa_result"),
            lot_id            = b.get("lot_id", ""),
            tool_id           = b.get("tool_id", ""),
        )
        return jd(result)
    except Exception as e:
        logging.error("Intelligence engine error: %s", type(e).__name__)
        raise HTTPException(500, "Intelligence analysis failed. Your data was not stored.")

# ── Phase 1 Extensions ─────────────────────────────────────────────────────────

@app.post("/api/v1/hypothesis/two-sample-t")
async def hyp_two_sample_t(request: Request):
    body = await request.json()
    try:
        a = np.array(body["group_a"], dtype=float)
        b = np.array(body["group_b"], dtype=float)
        result = two_sample_t(
            a, b,
            name_a = body.get("name_a", "Group A"),
            name_b = body.get("name_b", "Group B"),
            alpha  = body.get("alpha", 0.05),
        )
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

# ── Static frontend ────────────────────────────────────────────────────────────
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


def _serve_static_html(filename: str) -> HTMLResponse:
    path = os.path.join(os.path.dirname(__file__), "static", filename)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse(f"<h1>Not found: {filename}</h1>", status_code=404)


@app.get("/", response_class=HTMLResponse)
async def serve_landing():
    return _serve_static_html("landing.html")

@app.get("/app", response_class=HTMLResponse)
async def serve_frontend():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path, encoding="utf-8") as f:
            content = f.read()
        content = content.replace(
            "const API=window.location.origin.includes('localhost')?'http://localhost:8010':'';",
            "const API='';",
        )
        return HTMLResponse(content)
    return HTMLResponse(
        "<h1>StatMind v2.0</h1>"
        "<p>Place index.html in /static/index.html</p>"
        "<p><a href='/api/docs'>API Docs</a></p>"
    )

@app.get("/privacy", response_class=HTMLResponse)
async def serve_privacy():
    return _serve_static_html("privacy.html")

@app.get("/terms", response_class=HTMLResponse)
async def serve_terms():
    """Terms page — returns 404 page instead of blank/crash (P3-UX-2)."""
    return _serve_static_html("terms.html")

# ── Dev runner ─────────────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════════
# SESSION 4 — REAL BACKENDS FOR STUB FEATURES
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. Weibull / Reliability Analysis ─────────────────────────────────────────
@app.post("/api/v1/weibull/analyze")
async def weibull_analyze(file: UploadFile = File(...), column: str = Form(...),
                           censored_col: str = Form(""), confidence: float = Form(0.95)):
    try:
        contents = await file.read()
        df = _parse_upload(contents, file.filename)
        data = pd.to_numeric(df[column], errors="coerce").dropna().values
        data = data[data > 0]
        if len(data) < 3:
            raise HTTPException(400, "Need at least 3 positive failure times for Weibull analysis")

        from scipy.stats import weibull_min
        from scipy.optimize import minimize

        # MLE fit
        shape, loc, scale = weibull_min.fit(data, floc=0)
        beta  = float(shape)   # shape (Weibull modulus)
        eta   = float(scale)   # characteristic life (63.2% failure point)

        # Reliability at key time points
        t_points = [float(np.percentile(data, p)) for p in [10, 25, 50, 75, 90]]
        reliability = [float(np.exp(-(t/eta)**beta)) for t in t_points]

        # B10, B50 life (time at 10%, 50% failure)
        b10 = float(eta * (-np.log(0.90)) ** (1/beta))
        b50 = float(eta * (-np.log(0.50)) ** (1/beta))
        mttf = float(eta * float(__import__('math').gamma(1 + 1/beta)))

        # Verdict
        if beta < 1:
            failure_mode = "Infant mortality / early failures (decreasing hazard rate)"
        elif beta < 1.5:
            failure_mode = "Random failures (near-constant hazard rate)"
        else:
            failure_mode = "Wear-out failures (increasing hazard rate)"

        n = len(data)
        # Probability plot data (median ranks)
        sorted_data = np.sort(data)
        median_ranks = [(i - 0.3) / (n + 0.4) for i in range(1, n + 1)]

        return jd({
            "beta":  round(beta, 4),
            "eta":   round(eta, 4),
            "mttf":  round(mttf, 4),
            "b10_life": round(b10, 4),
            "b50_life": round(b50, 4),
            "failure_mode": failure_mode,
            "sample_size": n,
            "reliability_curve": {
                "times": [round(t, 4) for t in t_points],
                "reliability": [round(r, 4) for r in reliability],
            },
            "probability_plot": {
                "times": [round(float(t), 4) for t in sorted_data],
                "cumulative_failure": [round(r, 4) for r in median_ranks],
            },
            "verdict": f"β={beta:.2f} — {failure_mode}",
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


# ── 2. PCA — Principal Component Analysis ─────────────────────────────────────
@app.post("/api/v1/boxplot/analyze")
async def boxplot_analyze(file: UploadFile = File(...),
                           columns: str = Form(...),
                           group_col: str = Form("")):
    try:
        contents = await file.read()
        df = _parse_upload(contents, file.filename)
        cols = [c.strip() for c in columns.split(",") if c.strip() in df.columns]
        if not cols:
            raise HTTPException(400, "No valid columns specified")

        result = {}
        for col in cols:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(series) < 4:
                continue
            q1, median, q3 = float(np.percentile(series, 25)), float(np.percentile(series, 50)), float(np.percentile(series, 75))
            iqr = q3 - q1
            lower_fence = q1 - 1.5 * iqr
            upper_fence = q3 + 1.5 * iqr
            outliers = series[(series < lower_fence) | (series > upper_fence)].tolist()

            result[col] = {
                "min":    round(float(series.min()), 4),
                "q1":     round(q1, 4),
                "median": round(median, 4),
                "q3":     round(q3, 4),
                "max":    round(float(series.max()), 4),
                "mean":   round(float(series.mean()), 4),
                "std":    round(float(series.std()), 4),
                "iqr":    round(iqr, 4),
                "lower_fence": round(lower_fence, 4),
                "upper_fence": round(upper_fence, 4),
                "outliers": [round(float(o), 4) for o in outliers[:20]],
                "n_outliers": len(outliers),
                "n": len(series),
                "violin_data": series.sample(min(200, len(series)), random_state=42).sort_values().tolist(),
            }

        return jd({"columns": result, "n_columns": len(result)})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


# ── 5. MSA Linearity & Bias ───────────────────────────────────────────────────
@app.post("/api/v1/msa/linearity")
async def msa_linearity(file: UploadFile = File(...),
                         reference_col: str = Form(...),
                         measurement_col: str = Form(...),
                         process_variation: float = Form(1.0)):
    try:
        contents = await file.read()
        df = _parse_upload(contents, file.filename)
        ref  = pd.to_numeric(df[reference_col], errors="coerce")
        meas = pd.to_numeric(df[measurement_col], errors="coerce")
        mask = ref.notna() & meas.notna()
        ref, meas = ref[mask].values, meas[mask].values

        if len(ref) < 5:
            raise HTTPException(400, "Need at least 5 data points for linearity analysis")

        bias = meas - ref
        from scipy import stats

        slope, intercept, r, p, se = stats.linregress(ref, bias)
        mean_bias = float(np.mean(bias))
        bias_pct  = float(mean_bias / process_variation * 100)

        # Linearity = |slope| * process_variation
        linearity = float(abs(slope) * process_variation)
        linearity_pct = float(linearity / process_variation * 100)

        # Per reference value stats
        ref_unique = sorted(set(ref))
        per_ref = {}
        for rv in ref_unique:
            mask2 = ref == rv
            b = bias[mask2]
            per_ref[str(round(rv, 4))] = {
                "mean_bias": round(float(np.mean(b)), 4),
                "std_bias":  round(float(np.std(b)), 4) if len(b) > 1 else 0,
                "n": int(len(b)),
            }

        verdict = "Acceptable" if linearity_pct < 10 and abs(bias_pct) < 10 else "Unacceptable — recalibrate gauge"

        return jd({
            "mean_bias": round(mean_bias, 4),
            "bias_pct_of_pv": round(bias_pct, 2),
            "linearity": round(linearity, 4),
            "linearity_pct_of_pv": round(linearity_pct, 2),
            "regression_slope": round(float(slope), 4),
            "regression_intercept": round(float(intercept), 4),
            "r_squared": round(float(r**2), 4),
            "p_value": round(float(p), 4),
            "n": len(ref),
            "per_reference_value": per_ref,
            "process_variation": process_variation,
            "verdict": verdict,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


if __name__ == "__main__":
    import uvicorn
    print(f"\n  StatMind v2.0  |  http://localhost:{PORT}")
    print(f"  API docs:      http://localhost:{PORT}/api/docs")
    print(f"  Sessions:      1-Normality 2-Capability 3-SPC 4-GRR 5-CAPA 6-PDF\n")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
# ── Phase 2 Extensions ─────────────────────────────────────────────────────────

@app.post("/api/v1/capability/ci")
async def capability_ci(request: Request):
    """Cpk confidence interval calculation for a given Cpk and sample size."""
    b = await request.json()
    try:
        from capability import cpk_confidence_interval
        cpk = float(b["cpk"])
        n   = int(b["n"])
        confidence = float(b.get("confidence", 0.95))
        ci = cpk_confidence_interval(cpk, n, confidence)
        return jd({
            "cpk":        cpk,
            "n":          n,
            "confidence": confidence,
            "ci_lower":   ci.lower,
            "ci_upper":   ci.upper,
        })
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/outliers/analyze")
async def outliers_analyze(
    file: UploadFile = File(...),
    column: str      = Query(...),
    method: str      = Query("grubbs"),
    alpha: float     = Query(0.05, gt=0.0, lt=1.0),
):
    """Outlier detection using Grubbs, Rosner ESD, or Dixon Q test."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data = result.df[column].dropna().values.astype(float)
    try:
        from outliers import detect_outliers
        r = await asyncio.to_thread(detect_outliers, data, column, method, alpha)
        return jd(dataclasses.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/equivalence/analyze")
async def equivalence_analyze(
    file: UploadFile = File(...),
    col_a: str       = Query(...),
    col_b: str       = Query(...),
    delta: float     = Query(None),
    alpha: float     = Query(0.05, gt=0.0, lt=1.0),
):
    """TOST equivalence testing between two columns of an uploaded file.

    The frontend uploads a file and selects two columns (col_a/col_b), so this
    endpoint reads multipart form-data + query params. The previous version
    called request.json() and raised "Expecting value: line 1 column 1 (char 0)".
    """
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    for col in (col_a, col_b):
        if col not in result.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    try:
        from equivalence_test import tost_equivalence
        a     = result.df[col_a].dropna().values.astype(float)
        grp_b = result.df[col_b].dropna().values.astype(float)
        r = await asyncio.to_thread(
            tost_equivalence, a, grp_b,
            float(delta) if delta is not None else None,
            float(alpha), col_a, col_b,
        )
        return jd(dataclasses.asdict(r))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/runchart/analyze")
async def runchart_analyze(
    file: UploadFile = File(...),
    column: str      = Query(...),
):
    """Run chart with runs-above/below-median (Swed-Eisenhart) and trend (Cox-Stuart) tests.

    Returns the nested shape the frontend renders:
      { column, n, median, data, above_median, runs_test{...}, trend_test{...}, overall_verdict }
    The previous version returned only a flat run count, so the UI threw
    "Cannot read properties of undefined (reading 'p')" when reading runs_test.p.
    """
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data = result.df[column].dropna().values.astype(float)
    n    = int(len(data))
    if n < 4:
        raise HTTPException(400, "Need at least 4 data points for a run chart.")
    median = float(np.median(data))

    # ── Runs test (Swed-Eisenhart / Wald-Wolfowitz) about the median ──────────
    # Ignore points exactly on the median (standard convention).
    signs  = [1 if v > median else (0 if v < median else -1) for v in data]
    seq    = [s for s in signs if s != -1]
    n1     = sum(1 for s in seq if s == 1)
    n2     = sum(1 for s in seq if s == 0)
    runs   = 1
    for i in range(1, len(seq)):
        if seq[i] != seq[i - 1]:
            runs += 1
    if len(seq) < 2 or n1 == 0 or n2 == 0:
        runs_p, expected_runs, runs_z = 1.0, float(runs), 0.0
    else:
        N = n1 + n2
        expected_runs = (2.0 * n1 * n2) / N + 1.0
        var_runs = (2.0 * n1 * n2 * (2.0 * n1 * n2 - N)) / (N * N * (N - 1))
        sd_runs  = float(np.sqrt(var_runs)) if var_runs > 0 else 0.0
        if sd_runs == 0:
            runs_z, runs_p = 0.0, 1.0
        else:
            runs_z = (runs - expected_runs) / sd_runs
            from scipy import stats as _stats
            runs_p = float(2.0 * _stats.norm.sf(abs(runs_z)))
    runs_random = runs_p >= 0.05

    # ── Trend test (Cox-Stuart) ───────────────────────────────────────────────
    m       = n // 2
    first   = data[:m]
    second  = data[-m:] if n % 2 == 0 else data[-m:]
    n_plus  = int(np.sum(second > first))
    n_minus = int(np.sum(second < first))
    n_eff   = n_plus + n_minus
    if n_eff == 0:
        trend_p = 1.0
    else:
        from scipy import stats as _stats
        k = min(n_plus, n_minus)
        # two-sided sign test
        trend_p = float(min(1.0, 2.0 * _stats.binom.cdf(k, n_eff, 0.5)))
    trend_random = trend_p >= 0.05

    overall = ("Process appears random — no runs or trend signals"
               if (runs_random and trend_random)
               else "Non-random pattern detected — investigate assignable cause")

    return jd({
        "column":       column,
        "n":            n,
        "median":       round(median, 6),
        "data":         data.tolist(),
        "values":       data.tolist(),
        "above_median": [1 if v > median else 0 for v in data],
        "overall_verdict": overall,
        "runs_test": {
            "runs":     int(runs),
            "expected": round(float(expected_runs), 2),
            "z":        round(float(runs_z), 4),
            "p":        round(float(runs_p), 4),
            "verdict":  "Random" if runs_random else "Non-random (clustering/shift)",
        },
        "trend_test": {
            "n_plus":  n_plus,
            "n_minus": n_minus,
            "p":       round(float(trend_p), 4),
            "verdict": "No trend" if trend_random else "Trend detected",
        },
    })


# ══════════════════════════════════════════════════════════════════════════════
#  Previously-missing endpoints (frontend called these; backend had no route,
#  producing "Not Found" / stuck "Running…"). Wired to existing engine modules.
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/v1/transformation/analyze")
@app.post("/api/v1/data/transform")
async def transformation_analyze(
    file: UploadFile = File(...),
    column: str      = Query(...),
    usl: float       = Query(None),
    lsl: float       = Query(None),
):
    """Auto Box-Cox / Johnson transformation + non-normal capability."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data = result.df[column].dropna().values.astype(float)
    try:
        from transformation import auto_transform
        r = await asyncio.to_thread(
            auto_transform, data, column,
            float(usl) if usl is not None else None,
            float(lsl) if lsl is not None else None,
        )
        return jd(dataclasses.asdict(r) if dataclasses.is_dataclass(r) else r)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/sixpack/analyze")
async def sixpack_analyze(
    file: UploadFile = File(...),
    column: str      = Query(...),
    usl: float       = Query(...),
    lsl: float       = Query(...),
    target: float    = Query(None),
):
    """Capability Sixpack — 6 panels (histogram, prob plot, I-MR, capability, run chart, summary)."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data = result.df[column].dropna().values.astype(float)
    try:
        from sixpack import build_sixpack
        r = await asyncio.to_thread(
            build_sixpack, data, column, float(usl), float(lsl),
            float(target) if target is not None else None,
        )
        return jd(dataclasses.asdict(r) if dataclasses.is_dataclass(r) else r)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/tolerance/analyze")
async def tolerance_analyze(
    file: UploadFile   = File(...),
    column: str        = Query(...),
    coverage: float    = Query(0.99),
    confidence: float  = Query(0.95),
    interval_type: str = Query("two_sided"),
    usl: float         = Query(None),
    lsl: float         = Query(None),
):
    """Statistical tolerance interval (ASTM E2810 / ISO 16269-6)."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data = result.df[column].dropna().values.astype(float)
    try:
        from tolerance_interval import tolerance_interval
        r = await asyncio.to_thread(
            tolerance_interval, data, column,
            float(coverage), float(confidence), interval_type,
            float(usl) if usl is not None else None,
            float(lsl) if lsl is not None else None,
        )
        return jd(dataclasses.asdict(r) if dataclasses.is_dataclass(r) else r)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/hypothesis/from-file")
async def hypothesis_from_file(
    file: UploadFile = File(...),
    test: str        = Query(...),
    columns: str     = Query(...),
    alpha: float     = Query(0.05, gt=0.0, lt=1.0),
):
    """Run a hypothesis test on selected columns of an uploaded file.

    test ∈ {two_t, paired_t, anova, mann_whitney, kruskal, variance}
    columns: comma-separated; 2 columns for two-group tests, 2+ for ANOVA/Kruskal.
    """
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    cols = [col.strip() for col in columns.split(",") if col.strip()]
    for col in cols:
        if col not in result.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    if len(cols) < 2:
        raise HTTPException(400, "Select at least 2 columns.")

    def _col(name):
        return result.df[name].dropna().values.astype(float)

    try:
        import hypothesis as H
        if test in ("two_t", "two_sample_t"):
            r = H.two_sample_t(_col(cols[0]), _col(cols[1]), cols[0], cols[1], alpha)
        elif test == "paired_t":
            # paired_t needs aligned rows — drop rows missing either column
            sub = result.df[[cols[0], cols[1]]].dropna()
            r = H.paired_t(sub[cols[0]].values.astype(float),
                           sub[cols[1]].values.astype(float), cols[0], cols[1], alpha)
        elif test == "mann_whitney":
            r = H.mann_whitney(_col(cols[0]), _col(cols[1]), cols[0], cols[1], alpha)
        elif test == "anova":
            groups = [_col(c) for c in cols]
            r = H.one_way_anova(groups, cols, alpha)
        elif test == "kruskal":
            groups = [_col(c) for c in cols]
            r = H.kruskal_wallis(groups, cols, alpha)
        elif test == "variance":
            groups = [_col(c) for c in cols]
            r = H.variance_test(groups, cols, alpha)
        else:
            raise HTTPException(400, f"Unknown test type '{test}'.")
        return jd(dataclasses.asdict(r) if dataclasses.is_dataclass(r) else r)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/aaa/analyze")
async def aaa_analyze(
    file: UploadFile     = File(...),
    decision_col: str    = Query(...),
    sample_col: str      = Query(...),
    appraiser_col: str   = Query(...),
    replicate_col: str   = Query(None),
    reference_col: str   = Query(None),
):
    """Attribute Agreement Analysis — Fleiss' kappa + per-appraiser agreement (AIAG MSA)."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    df = result.df
    for col in [decision_col, sample_col, appraiser_col]:
        if col not in df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    for col in [replicate_col, reference_col]:
        if col and col not in df.columns:
            raise HTTPException(404, f"Column '{col}' not found")

    sub = df.dropna(subset=[decision_col, sample_col, appraiser_col])
    decisions  = sub[decision_col].astype(str).values
    sample_ids = sub[sample_col].astype(str).values
    appraisers = sub[appraiser_col].astype(str).values
    if replicate_col:
        replicates = sub[replicate_col].astype(str).values
    else:
        # Synthesize replicate ids per (sample, appraiser) group.
        from collections import defaultdict
        counter = defaultdict(int)
        replicates = []
        for s, a in zip(sample_ids, appraisers):
            counter[(s, a)] += 1
            replicates.append(str(counter[(s, a)]))
        replicates = np.array(replicates)
    reference = sub[reference_col].astype(str).values if reference_col else None

    try:
        from routers.attribute_agreement import analyze_aaa
        r = await asyncio.to_thread(
            analyze_aaa, decisions, sample_ids, appraisers, replicates, reference,
        )
        return jd(dataclasses.asdict(r) if dataclasses.is_dataclass(r) else r)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/cusum/analyze")
async def cusum_analyze(
    file: UploadFile = File(...),
    column: str      = Query(...),
    k: float         = Query(0.5),
    h: float         = Query(4.0),
    lam: float       = Query(0.2),
    L: float         = Query(3.0),
    target: float    = Query(None),
):
    """CUSUM + EWMA charts for detecting small sustained process shifts.

    Returns nested {cusum:{...}, ewma:{...}} — the frontend reads r.cusum.* and
    r.ewma.*, so the previous flat payload left both charts empty.
    """
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data    = result.df[column].dropna().values.astype(float)
    n       = int(len(data))
    if n < 2:
        raise HTTPException(400, "Need at least 2 data points.")
    mu      = float(target) if target is not None else float(np.mean(data))
    sigma   = float(np.std(data, ddof=1))
    if sigma == 0:
        raise HTTPException(400, "Standard deviation is zero — CUSUM/EWMA undefined.")

    # ── CUSUM ─────────────────────────────────────────────────────────────────
    cusum_pos, cusum_neg = [0.0], [0.0]
    cusum_signals = []
    for i, x in enumerate(data):
        zi = (x - mu) / sigma
        cp = max(0.0, cusum_pos[-1] + zi - k)
        cn = max(0.0, cusum_neg[-1] - zi - k)
        cusum_pos.append(cp)
        cusum_neg.append(cn)
        if cp > h or cn > h:
            cusum_signals.append({"index": i, "value": float(x),
                                  "cusum_pos": round(cp, 4), "cusum_neg": round(cn, 4)})
    cusum_pos = cusum_pos[1:]
    cusum_neg = cusum_neg[1:]

    # ── EWMA ──────────────────────────────────────────────────────────────────
    ewma_vals = []
    z_prev    = mu
    ewma_signals = []
    ucl_list, lcl_list = [], []
    for i, x in enumerate(data):
        z = lam * x + (1 - lam) * z_prev
        ewma_vals.append(z)
        z_prev = z
        # time-varying control limits
        var_factor = (lam / (2 - lam)) * (1 - (1 - lam) ** (2 * (i + 1)))
        limit = L * sigma * float(np.sqrt(var_factor))
        ucl_i = mu + limit
        lcl_i = mu - limit
        ucl_list.append(ucl_i)
        lcl_list.append(lcl_i)
        if z > ucl_i or z < lcl_i:
            ewma_signals.append({"index": i, "value": float(x), "ewma": round(z, 4)})
    # steady-state limits for the simple horizontal-line rendering in the UI
    ss_limit = L * sigma * float(np.sqrt(lam / (2 - lam)))

    return jd({
        "column":     column,
        "n":          n,
        "target":     round(mu, 6),
        "sigma":      round(sigma, 6),
        "cusum": {
            "k":          k,
            "h":          h,
            "cusum_pos":  [round(v, 4) for v in cusum_pos],
            "cusum_neg":  [round(v, 4) for v in cusum_neg],
            "signals":    cusum_signals,
            "n_alarms":   len(cusum_signals),
        },
        "ewma": {
            "lambda":       lam,
            "L":            L,
            "ewma_values":  [round(v, 4) for v in ewma_vals],
            "ucl":          round(mu + ss_limit, 6),
            "lcl":          round(mu - ss_limit, 6),
            "ucl_series":   [round(v, 6) for v in ucl_list],
            "lcl_series":   [round(v, 6) for v in lcl_list],
            "center_line":  round(mu, 6),
            "signals":      ewma_signals,
            "n_alarms":     len(ewma_signals),
        },
        "in_control": (len(cusum_signals) + len(ewma_signals)) == 0,
    })


@app.post("/api/v1/correlation/matrix")
async def correlation_matrix(
    file: UploadFile  = File(...),
    columns: str      = Query(None),
    method: str       = Query("pearson"),
):
    """Correlation matrix with significance p-values.

    `columns` is optional — when omitted, all numeric columns are used (the
    frontend does not send it). Returns matrices both as nested arrays
    (r_matrix/p_matrix) and as objects keyed by column name
    (correlation_matrix/p_values), which is what the UI reads.
    """
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))

    if columns:
        cols = [col.strip() for col in columns.split(",") if col.strip()]
        for col in cols:
            if col not in result.df.columns:
                raise HTTPException(404, f"Column '{col}' not found")
    else:
        # Auto-select numeric columns with at least some variation.
        numeric = result.df.select_dtypes(include=[np.number])
        cols = [c for c in numeric.columns if numeric[c].dropna().nunique() > 1]

    if len(cols) < 2:
        raise HTTPException(400, "Need at least 2 numeric columns for a correlation matrix.")

    df  = result.df[cols].dropna()
    if len(df) < 3:
        raise HTTPException(400, "Need at least 3 complete rows across the selected columns.")

    from scipy import stats as _stats
    mat, pmat = [], []
    corr_obj, p_obj = {}, {}
    for c1 in cols:
        row_r, row_p = [], []
        corr_obj[c1], p_obj[c1] = {}, {}
        for c2 in cols:
            if c1 == c2:
                r, p = 1.0, 0.0
            elif method == "spearman":
                r, p = _stats.spearmanr(df[c1], df[c2])
            else:
                r, p = _stats.pearsonr(df[c1], df[c2])
            r, p = round(float(r), 4), round(float(p), 4)
            row_r.append(r); row_p.append(p)
            corr_obj[c1][c2] = r
            p_obj[c1][c2]    = p
        mat.append(row_r); pmat.append(row_p)

    return jd({
        "columns": cols,
        "method": method,
        "n": int(len(df)),
        "r_matrix": mat,
        "p_matrix": pmat,
        "correlation_matrix": corr_obj,
        "p_values": p_obj,
    })


@app.post("/api/v1/sample-size/calculate")
async def sample_size_calculate(request: Request):
    """Sample size calculation for capability studies, hypothesis tests, and control charts."""
    b = await request.json()
    try:
        from scipy import stats as _stats
        study_type = b.get("study_type", "capability")
        if study_type == "capability":
            cpk_target = float(b.get("cpk_target", 1.33))
            confidence = float(b.get("confidence", 0.95))
            precision  = float(b.get("precision",  0.10))
            z = float(_stats.norm.ppf((1 + confidence) / 2))
            n = int(np.ceil((z / precision) ** 2 * (1 / (9 * cpk_target ** 2) + 0.5)))
            return jd({"study_type": study_type, "n": max(n, 30),
                        "cpk_target": cpk_target, "confidence": confidence, "precision": precision})
        elif study_type == "two_sample_t":
            delta  = float(b.get("delta", 1.0))
            sigma  = float(b.get("sigma", 1.0))
            alpha  = float(b.get("alpha", 0.05))
            power  = float(b.get("power", 0.80))
            z_a    = float(_stats.norm.ppf(1 - alpha / 2))
            z_b    = float(_stats.norm.ppf(power))
            n      = int(np.ceil(2 * ((z_a + z_b) * sigma / delta) ** 2))
            return jd({"study_type": study_type, "n_per_group": max(n, 2),
                        "delta": delta, "sigma": sigma, "alpha": alpha, "power": power})
        else:
            raise HTTPException(400, f"Unknown study_type: {study_type}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/hypothesis/two-way-anova")
async def two_way_anova(
    file: UploadFile   = File(...),
    response: str      = Query(...),
    factor_a: str      = Query(...),
    factor_b: str      = Query(...),
    alpha: float       = Query(0.05, gt=0.0, lt=1.0),
):
    """Two-way ANOVA with interaction term."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    for col in [response, factor_a, factor_b]:
        if col not in result.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    try:
        import statsmodels.formula.api as smf
        df = result.df[[response, factor_a, factor_b]].dropna().copy()
        df[factor_a] = df[factor_a].astype(str)
        df[factor_b] = df[factor_b].astype(str)
        formula = f"Q('{response}') ~ C(Q('{factor_a}')) + C(Q('{factor_b}')) + C(Q('{factor_a}')):C(Q('{factor_b}'))"
        model   = smf.ols(formula, data=df).fit()
        import statsmodels.stats.anova as anova_lm
        table   = anova_lm.anova_lm(model, typ=2)
        rows = []
        for idx, row in table.iterrows():
            src = str(idx)
            # Convert raw patsy/statsmodels formula terms to friendly labels.
            if src == "Residual":
                label = "Residual"
            elif ":" in src:
                label = f"{factor_a} × {factor_b}"
            elif factor_a in src:
                label = factor_a
            elif factor_b in src:
                label = factor_b
            else:
                label = src
            rows.append({
                "source":   label,
                "ss":       round(float(row.get("sum_sq", 0)), 4),
                "df":       round(float(row.get("df", 0)), 1),
                "ms":       round(float(row.get("sum_sq", 0) / max(row.get("df", 1), 1)), 4),
                "F":        round(float(row.get("F", 0)), 4) if not np.isnan(row.get("F", float("nan"))) else None,
                "p_value":  round(float(row.get("PR(>F)", 1)), 4) if not np.isnan(row.get("PR(>F)", float("nan"))) else None,
                "significant": float(row.get("PR(>F)", 1)) < alpha if not np.isnan(row.get("PR(>F)", float("nan"))) else False,
            })
        return jd({"response": response, "factor_a": factor_a, "factor_b": factor_b,
                   "alpha": alpha, "anova_table": rows, "r_squared": round(float(model.rsquared), 4)})
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/rsm/design")
async def rsm_design(request: Request):
    """Generate a Central Composite Design (CCD) or Box-Behnken design matrix."""
    b = await request.json()
    try:
        factors     = b.get("factors", [])
        design_type = b.get("design_type", "ccd")
        n_factors   = len(factors)
        if n_factors < 2:
            raise HTTPException(400, "RSM requires at least 2 factors.")
        if design_type == "ccd":
            from itertools import product as _prod
            factorial_runs = list(_prod([-1, 1], repeat=n_factors))
            alpha_val      = float(n_factors ** 0.5)
            axial_runs     = []
            for i in range(n_factors):
                row_p = [0.0] * n_factors; row_p[i] =  alpha_val; axial_runs.append(row_p)
                row_n = [0.0] * n_factors; row_n[i] = -alpha_val; axial_runs.append(row_n)
            center_runs = [[0.0] * n_factors] * 4
            all_runs    = [list(r) for r in factorial_runs] + axial_runs + center_runs
        else:
            all_runs = [[0.0] * n_factors] * (n_factors * (n_factors - 1) * 2 + 1)

        design_matrix = []
        for i, run in enumerate(all_runs):
            row = {"run": i + 1}
            for j, f in enumerate(factors):
                lo   = float(f.get("low",  -1))
                hi   = float(f.get("high",  1))
                mid  = (lo + hi) / 2
                half = (hi - lo) / 2
                row[f["name"]] = round(mid + run[j] * half / max(alpha_val if design_type == "ccd" else 1, 1), 4)
            design_matrix.append(row)

        return jd({"design_type": design_type, "n_factors": n_factors,
                   "n_runs": len(design_matrix), "factors": factors,
                   "design_matrix": design_matrix})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/rsm/analyze")
async def rsm_analyze(request: Request):
    """Fit a second-order response surface model and return coefficients + contour data."""
    b = await request.json()
    try:
        runs       = b.get("runs", [])
        response   = b.get("response", "y")
        factor_names = b.get("factors", [])
        if not runs or not factor_names:
            raise HTTPException(400, "Provide 'runs' (list of dicts) and 'factors' (list of names).")
        import pandas as _pd
        df  = _pd.DataFrame(runs)
        y   = df[response].values.astype(float)
        X_df = df[factor_names]
        import statsmodels.formula.api as smf
        terms   = " + ".join([f"Q('{f}')" for f in factor_names])
        sq_terms= " + ".join([f"I(Q('{f}')**2)" for f in factor_names])
        inter   = " + ".join([f"Q('{factor_names[i]}')*Q('{factor_names[j]}')"
                              for i in range(len(factor_names))
                              for j in range(i+1, len(factor_names))])
        formula = f"Q('{response}') ~ {terms} + {sq_terms}" + (f" + {inter}" if inter else "")
        model   = smf.ols(formula, data=df).fit()
        coeffs  = {str(k): round(float(v), 6) for k, v in model.params.items()}
        return jd({
            "response":   response,
            "factors":    factor_names,
            "n_runs":     len(runs),
            "r_squared":  round(float(model.rsquared), 4),
            "r_squared_adj": round(float(model.rsquared_adj), 4),
            "coefficients": coeffs,
            "p_values":   {str(k): round(float(v), 4) for k, v in model.pvalues.items()},
            "verdict":    "Good fit (R² ≥ 0.80)" if model.rsquared >= 0.80 else "Poor fit — consider more runs or different factor ranges",
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))
 
@app.post("/api/v1/email/capture") 
async def email_capture(request: Request): 
    b = await request.json() 
    email = b.get("email", "").strip() 
    if not email or "@" not in email: 
        raise HTTPException(400, "Valid email required.") 
    return jd({"success": True, "message": "Email captured.", "email": email}) 
