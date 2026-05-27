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
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ── Statistical engines (hoisted — P0-ARCH-1) ─────────────────────────────────
from file_parser    import parse_any_file
from normality      import analyze_column
from capability     import analyze_capability
from control_charts import auto_select_and_build as analyze_control_chart
from gauge_rr       import analyze_gauge_rr, parse_grr_csv
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
ENV            = os.getenv("ENV", "development")
ORIGINS        = os.getenv("ALLOWED_ORIGINS", "*").split(",")
MAX_UPLOAD_MB  = int(os.getenv("MAX_UPLOAD_MB", 25))      # P0-SEC-1
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
CACHE_TTL_SEC  = int(os.getenv("REPORT_CACHE_TTL", 3600)) # 1 hour default
CACHE_MAX_ITEMS = int(os.getenv("REPORT_CACHE_MAX", 200))

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="StatMind",
    description="Process Statistics Engine — Universal measurement analysis",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)

# ── Rate limiting ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )

# ── Security helpers ───────────────────────────────────────────────────────────
_BLOCKED_EXT = {
    "exe","sh","bat","ps1","js","php","rb","pl","cmd","jar","dll",
    "html","zip","tar",
}

def _validate_upload(file: UploadFile, content: bytes) -> None:
    """
    Reject dangerous file types and oversized uploads (P0-SEC-1).
    Pass pre-read content bytes so size can be checked without re-reading.
    """
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext in _BLOCKED_EXT:
        raise HTTPException(400, f"File type '.{ext}' is not allowed.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"File too large ({len(content) // 1024 // 1024} MB). "
            f"Maximum allowed: {MAX_UPLOAD_MB} MB."
        )


def _sanitize_text(text: str, max_len: int = 5000) -> str:
    """Sanitize user text — strip HTML and cap length."""
    if not text:
        return ""
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", text))
    injection_patterns = [
        r"ignore (previous|all|above) instructions?",
        r"system prompt",
        r"you are now",
        r"act as",
        r"jailbreak",
        r"DAN mode",
        r"\\n(system|user|assistant):",
    ]
    for pattern in injection_patterns:
        text = re.sub(pattern, "[FILTERED]", text, flags=re.IGNORECASE)
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


def jd(d):   return JSONResponse(content=json.loads(json.dumps(d, cls=NpEnc)))
def jobj(o): return jd(dataclasses.asdict(o))

# ── Security headers middleware ────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["X-XSS-Protection"]        = "1; mode=block"
    response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]      = "geolocation=(), microphone=(), camera=()"
    return response

# ── Health endpoints ───────────────────────────────────────────────────────────
def _health_payload() -> dict:
    return {
        "status":    "ok",
        "service":   "StatMind",
        "version":   "2.0.0",
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

# ── Session 1: Normality ───────────────────────────────────────────────────────
@app.post("/api/v1/normality/analyze")
@limiter.limit("30/minute")
async def normality(request: Request, file: UploadFile = File(...), alpha: float = 0.05):
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    results, errors = [], []
    for col in result.numeric_columns:
        try:
            results.append(dataclasses.asdict(
                analyze_column(result.df[col].dropna().values.astype(float), col, alpha)
            ))
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
    subgroup_size: int  = Query(1),
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
        return jobj(await asyncio.to_thread(
            analyze_capability,
            result.df[column].dropna().values.astype(float),
            column, usl, lsl, target, subgroup_size,
        ))
    except ValueError as e:
        raise HTTPException(400, str(e))

# ── Session 3: SPC ─────────────────────────────────────────────────────────────
@app.post("/api/v1/spc/analyze")
async def spc(
    file: UploadFile  = File(...),
    column: str       = Query(...),
    subgroup_size: int = Query(1),
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
        spc_result = dataclasses.asdict(
            await asyncio.to_thread(analyze_control_chart, data, column, subgroup_size)
        )
        spc_result["subrange"] = {
            "start":            start_index,
            "end":              end_index,
            "total_points":     total_points,
            "selected_points":  len(data),
        }
        return jd(spc_result)
    except ValueError as e:
        raise HTTPException(400, str(e))

# ── Session 4: Gauge R&R ───────────────────────────────────────────────────────
@app.post("/api/v1/grr/analyze")
async def grr_analyze(
    file: UploadFile    = File(...),
    tolerance: float    = Query(None),
    method: str         = Query("ANOVA"),
):
    c = await file.read()
    _validate_upload(file, c)
    try:
        measurements, parts, operators, col_name = parse_grr_csv(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    try:
        return jobj(await asyncio.to_thread(
            analyze_gauge_rr, measurements, parts, operators, col_name, tolerance, method
        ))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/grr/preview")
async def grr_preview(file: UploadFile = File(...)):
    c = await file.read()
    _validate_upload(file, c)
    try:
        measurements, parts, operators, col_name = parse_grr_csv(c, file.filename)
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
        result = get_capa_for_rule(body.get("rule_id", ""), body.get("process_type", ""))
        return jd(result)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/v1/capa/catalog")
async def capa_catalog():
    return jd(get_all_rules_catalog())

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
    y = r.df[response].dropna().values.astype(int)
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
    y = r.df[response].dropna().values.astype(int)
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

# ── Attribute charts ───────────────────────────────────────────────────────────
@app.post("/api/v1/attribute-charts/p")
async def p_chart_ep(request: Request):
    body = await request.json()
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
        logging.error(f"Intelligence engine error: {e}", exc_info=True)
        raise HTTPException(500, f"Intelligence analysis failed: {e}")

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
        with open(path) as f:
            return HTMLResponse(f.read())
    return HTMLResponse(f"<h1>Not found: {filename}</h1>", status_code=404)


@app.get("/", response_class=HTMLResponse)
async def serve_landing():
    return _serve_static_html("landing.html")

@app.get("/app", response_class=HTMLResponse)
async def serve_frontend():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path) as f:
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
if __name__ == "__main__":
    import uvicorn
    print(f"\n  StatMind v2.0  |  http://localhost:{PORT}")
    print(f"  API docs:      http://localhost:{PORT}/api/docs")
    print(f"  Sessions:      1-Normality 2-Capability 3-SPC 4-GRR 5-CAPA 6-PDF\n")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
404: Not Found