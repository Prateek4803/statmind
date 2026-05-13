"""
StatMind — Production Entry Point
Serves both the FastAPI backend AND the static frontend from one process.
Run locally:  python main.py
Deploy:       gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
              OR: uvicorn main:app --port 8010
"""

import os
import json
import uuid
import tempfile
import dataclasses
import numpy as np

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# ── Import all StatMind engines ───────────────────────────────────────────────
from normality import analyze_column, parse_uploaded_file
from capability import analyze_capability
from control_charts import analyze_control_chart
from gauge_rr import analyze_gauge_rr, parse_grr_csv
from capa_rules_engine import run_capa_engine, get_capa_for_rule, get_all_rules_catalog
from pdf_report import generate_report

# ── App setup ─────────────────────────────────────────────────────────────────
PORT = int(os.getenv("PORT", 8010))
ENV  = os.getenv("ENV", "development")
ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app = FastAPI(
    title="StatMind",
    description="Process Statistics Engine for Semiconductor Manufacturing",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

_report_cache: dict = {}

# ── JSON encoder ──────────────────────────────────────────────────────────────
class NpEnc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, np.bool_): return bool(o)
        return super().default(o)

def jd(d):
    return JSONResponse(content=json.loads(json.dumps(d, cls=NpEnc)))

def jobj(obj):
    return jd(dataclasses.asdict(obj))

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "service": "StatMind", "version": "1.0.0", "env": ENV}

# ── Session 1: Normality ──────────────────────────────────────────────────────
@app.post("/api/v1/columns")
async def get_columns(file: UploadFile = File(...)):
    c = await file.read()
    try:
        df = parse_uploaded_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    cols = []
    for col in df.columns:
        d = df[col].dropna().values.astype(float)
        cols.append({
            "name": col, "n": int(len(d)),
            "mean": round(float(d.mean()), 4),
            "std":  round(float(d.std(ddof=1)), 4),
            "min":  round(float(d.min()), 4),
            "max":  round(float(d.max()), 4),
        })
    return jd({"columns": cols})


@app.post("/api/v1/normality/analyze")
async def normality(file: UploadFile = File(...), alpha: float = 0.05):
    c = await file.read()
    try:
        df = parse_uploaded_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    results, errors = [], []
    for col in df.columns:
        try:
            results.append(dataclasses.asdict(
                analyze_column(df[col].dropna().values.astype(float), col, alpha)))
        except Exception as e:
            errors.append({"column": col, "error": str(e)})
    return jd({"filename": file.filename, "rows": len(df),
                "columns_analyzed": len(results), "alpha": alpha,
                "results": results, "errors": errors})


# ── Session 2: Capability ─────────────────────────────────────────────────────
@app.post("/api/v1/capability/analyze")
async def capability(
    file: UploadFile = File(...),
    column: str = Query(...), usl: float = Query(...), lsl: float = Query(...),
    target: float = Query(None), subgroup_size: int = Query(1),
):
    c = await file.read()
    try:
        df = parse_uploaded_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    try:
        return jobj(analyze_capability(
            df[column].dropna().values.astype(float), column, usl, lsl, target, subgroup_size))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Session 3: SPC ────────────────────────────────────────────────────────────
@app.post("/api/v1/spc/analyze")
async def spc(
    file: UploadFile = File(...),
    column: str = Query(...), subgroup_size: int = Query(1),
):
    c = await file.read()
    try:
        df = parse_uploaded_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    try:
        return jobj(analyze_control_chart(
            df[column].dropna().values.astype(float), column, subgroup_size))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ── Session 4: GRR ────────────────────────────────────────────────────────────
@app.post("/api/v1/grr/analyze")
async def grr_analyze(
    file: UploadFile = File(...),
    tolerance: float = Query(None), method: str = Query("ANOVA"),
):
    c = await file.read()
    try:
        measurements, parts, operators, col_name = parse_grr_csv(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    try:
        return jobj(analyze_gauge_rr(measurements, parts, operators, col_name, tolerance, method))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/grr/preview")
async def grr_preview(file: UploadFile = File(...)):
    c = await file.read()
    try:
        measurements, parts, operators, col_name = parse_grr_csv(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    up = list(set(str(p) for p in parts))
    uo = list(set(str(o) for o in operators))
    return jd({
        "column": col_name, "n_total": len(measurements),
        "n_parts": len(up), "n_operators": len(uo),
        "n_replicates": len(measurements) // (len(up) * len(uo)),
        "parts": sorted(up), "operators": sorted(uo),
        "mean": round(float(np.mean(measurements)), 4),
        "std":  round(float(np.std(measurements, ddof=1)), 4),
    })


# ── Session 5: CAPA Engine ────────────────────────────────────────────────────
@app.post("/api/v1/capa/generate")
async def capa_generate(request: Request):
    body = await request.json()
    try:
        result = run_capa_engine(
            normality_result=body.get("normality_result"),
            capability_result=body.get("capability_result"),
            spc_result=body.get("spc_result"),
            grr_result=body.get("grr_result"),
            process_context=body.get("process_context", ""),
            parameter_name=body.get("parameter_name", ""),
            process_type=body.get("process_type", ""),
        )
        return jd({"success": True, **result})
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/v1/capa/override")
async def capa_override(request: Request):
    body = await request.json()
    rule_id = body.get("rule_id")
    if not rule_id:
        raise HTTPException(400, "rule_id required")
    from capa_rules_engine import _extract_stats
    stats = _extract_stats(
        body.get("normality_result"), body.get("capability_result"),
        body.get("spc_result"), body.get("grr_result"),
    )
    result = get_capa_for_rule(
        rule_id, stats,
        body.get("process_context", ""),
        body.get("parameter_name", ""),
    )
    return jd({"success": True, "primary_capa": result})


@app.get("/api/v1/capa/catalog")
async def capa_catalog():
    return jd({"rules": get_all_rules_catalog()})


# ── Session 6: PDF Report ─────────────────────────────────────────────────────
@app.post("/api/v1/report/generate")
async def generate_pdf_report(request: Request):
    body = await request.json()
    report_id = str(uuid.uuid4())[:8]
    tmp_path = os.path.join(tempfile.gettempdir(), f"statmind_report_{report_id}.pdf")
    meta = body.get("meta", {})
    meta.setdefault("parameter", body.get("parameter_name", "Process Parameter"))
    meta.setdefault("process", body.get("process_type", "N/A"))
    try:
        generate_report(
            tmp_path,
            normality_result=body.get("normality_result"),
            capability_result=body.get("capability_result"),
            spc_result=body.get("spc_result"),
            grr_result=body.get("grr_result"),
            capa_result=body.get("capa_result"),
            meta=meta,
        )
        _report_cache[report_id] = tmp_path
        size_kb = round(os.path.getsize(tmp_path) / 1024)
        sections = sum(1 for k in [
            "normality_result", "capability_result",
            "spc_result", "grr_result", "capa_result",
        ] if body.get(k))
        return jd({
            "success": True, "report_id": report_id,
            "download_url": f"/api/v1/report/download/{report_id}",
            "size_kb": size_kb, "sections_included": sections,
        })
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {str(e)}")


@app.get("/api/v1/report/download/{report_id}")
async def download_report(report_id: str):
    path = _report_cache.get(report_id)
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Report not found or expired. Please regenerate.")
    return FileResponse(
        path, media_type="application/pdf",
        filename=f"statmind_report_{report_id}.pdf",
        headers={"Content-Disposition": f'attachment; filename="statmind_report_{report_id}.pdf"'},
    )


# ── Static frontend (Session 7: self-contained deployment) ───────────────────
# Serves statmind_s6.html at / when running in production
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the StatMind frontend."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path) as f:
            content = f.read()
        # Rewrite API calls to use relative paths
        content = content.replace("http://localhost:8010", "")
        return HTMLResponse(content)
    return HTMLResponse("<h1>StatMind API running. Place statmind_s6.html in /static/index.html</h1>")


# ── Dev runner ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"\n  StatMind v1.0.0  |  http://localhost:{PORT}")
    print(f"  API docs:        http://localhost:{PORT}/api/docs\n")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
