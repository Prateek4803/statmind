"""
StatMind v2.0 — Final Production Entry Point
All refinements: R1 (universal parser) + R2 (expanded CAPA) + R3 (SPC subrange)
Run: python main.py  OR  uvicorn main:app --port 8010
"""

import os, json, uuid, tempfile, dataclasses
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# ── Engines ───────────────────────────────────────────────────────────────────
from file_parser    import parse_any_file               # R1: universal parser
from normality      import analyze_column
from capability     import analyze_capability
from control_charts import analyze_control_chart
from gauge_rr       import analyze_gauge_rr, parse_grr_csv
from capa_rules_engine import (                         # R2: expanded CAPA
    run_capa_engine, run_capa_engine_v2,
    get_capa_for_rule, get_all_rules_catalog,
    get_all_rules_catalog_v2, _extract_stats,
)
from pdf_report import generate_report

# ── App ───────────────────────────────────────────────────────────────────────
PORT    = int(os.getenv("PORT", 8010))
ENV     = os.getenv("ENV", "development")
ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app = FastAPI(
    title="StatMind",
    description="Process Statistics Engine — Universal measurement analysis",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)
app.add_middleware(CORSMiddleware,
    allow_origins=ORIGINS, allow_methods=["*"], allow_headers=["*"])

_report_cache: dict = {}

# ── Helpers ───────────────────────────────────────────────────────────────────
class NpEnc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, np.integer):  return int(o)
        if isinstance(o, np.floating): return float(o)
        if isinstance(o, np.ndarray):  return o.tolist()
        if isinstance(o, np.bool_):    return bool(o)
        return super().default(o)

def jd(d):   return JSONResponse(content=json.loads(json.dumps(d,  cls=NpEnc)))
def jobj(o): return jd(dataclasses.asdict(o))

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok", "service": "StatMind",
        "version": "2.0.0", "env": ENV,
        "sessions": ["normality","capability","spc","grr","capa","pdf"],
        "capa_rules": 31,
    }

# ── Shared: column detection ──────────────────────────────────────────────────
@app.post("/api/v1/columns")
async def get_columns(file: UploadFile = File(...)):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    cols = [
        {"name": col,
         "n":    int(len(d := result.df[col].dropna().values.astype(float))),
         "mean": round(float(d.mean()), 4),
         "std":  round(float(d.std(ddof=1)), 4),
         "min":  round(float(d.min()), 4),
         "max":  round(float(d.max()), 4)}
        for col in result.numeric_columns
    ]
    return jd({
        "columns": cols,
        "source_format": result.source_format,
        "metadata": result.metadata,
        "warnings": result.warnings,
    })

# ── Session 1: Normality ──────────────────────────────────────────────────────
@app.post("/api/v1/normality/analyze")
async def normality(file: UploadFile = File(...), alpha: float = 0.05):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    results, errors = [], []
    for col in result.numeric_columns:
        try:
            results.append(dataclasses.asdict(
                analyze_column(result.df[col].dropna().values.astype(float), col, alpha)))
        except Exception as e:
            errors.append({"column": col, "error": str(e)})
    return jd({
        "filename": file.filename, "rows": result.n_rows,
        "columns_analyzed": len(results), "alpha": alpha,
        "source_format": result.source_format,
        "metadata": result.metadata,
        "results": results, "errors": errors,
    })

# ── Session 2: Capability ─────────────────────────────────────────────────────
@app.post("/api/v1/capability/analyze")
async def capability(
    file: UploadFile = File(...),
    column: str = Query(...), usl: float = Query(...), lsl: float = Query(...),
    target: float = Query(None), subgroup_size: int = Query(1),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found. Available: {result.numeric_columns}")
    try:
        return jobj(analyze_capability(
            result.df[column].dropna().values.astype(float),
            column, usl, lsl, target, subgroup_size))
    except ValueError as e:
        raise HTTPException(400, str(e))

# ── Session 3: SPC + subrange (R3) ───────────────────────────────────────────
@app.post("/api/v1/spc/analyze")
async def spc(
    file: UploadFile = File(...),
    column: str = Query(...),
    subgroup_size: int = Query(1),
    start_index: int = Query(None),   # R3: subrange start (0-based)
    end_index:   int = Query(None),   # R3: subrange end (exclusive)
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data = result.df[column].dropna().values.astype(float)
    total_points = len(data)

    # Apply subrange if specified
    if start_index is not None and end_index is not None:
        start_index = max(0, start_index)
        end_index   = min(total_points, end_index)
        data = data[start_index:end_index]

    try:
        spc_result = dataclasses.asdict(analyze_control_chart(data, column, subgroup_size))
        spc_result["subrange"] = {
            "start":           start_index,
            "end":             end_index,
            "total_points":    total_points,
            "selected_points": len(data),
        }
        return jd(spc_result)
    except ValueError as e:
        raise HTTPException(400, str(e))

# ── Session 4: Gauge R&R ──────────────────────────────────────────────────────
@app.post("/api/v1/grr/analyze")
async def grr_analyze(
    file: UploadFile = File(...),
    tolerance: float = Query(None),
    method: str = Query("ANOVA"),
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

# ── Session 5: CAPA (v1 + v2) ────────────────────────────────────────────────
@app.post("/api/v1/capa/generate")
async def capa_generate(request: Request):
    body = await request.json()
    try:
        result = run_capa_engine(**{
            k: body.get(k) for k in [
                "normality_result","capability_result","spc_result",
                "grr_result","process_context","parameter_name","process_type",
            ]
        })
        return jd({"success": True, **result})
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/v1/capa/v2/generate")
async def capa_generate_v2(request: Request):
    """R2 expanded engine — 31 rules, multi-industry."""
    body = await request.json()
    try:
        result = run_capa_engine_v2(
            normality_result  = body.get("normality_result"),
            capability_result = body.get("capability_result"),
            spc_result        = body.get("spc_result"),
            grr_result        = body.get("grr_result"),
            process_context   = body.get("process_context", ""),
            parameter_name    = body.get("parameter_name", ""),
            process_type      = body.get("process_type", ""),
        )
        return jd({"success": True, **result})
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/v1/capa/override")
@app.post("/api/v1/capa/v2/override")
async def capa_override(request: Request):
    body = await request.json()
    rule_id = body.get("rule_id")
    if not rule_id:
        raise HTTPException(400, "rule_id required")
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

@app.get("/api/v1/capa/v2/catalog")
async def capa_catalog_v2():
    return jd({"rules": get_all_rules_catalog_v2()})

# ── Session 6: PDF Report ─────────────────────────────────────────────────────
@app.post("/api/v1/report/generate")
async def generate_pdf_report(request: Request):
    body = await request.json()
    report_id = str(uuid.uuid4())[:8]
    tmp_path  = os.path.join(tempfile.gettempdir(), f"statmind_report_{report_id}.pdf")
    meta = body.get("meta", {})
    meta.setdefault("parameter", body.get("parameter_name", "Process Parameter"))
    meta.setdefault("process",   body.get("process_type", "N/A"))
    try:
        generate_report(
            tmp_path,
            normality_result  = body.get("normality_result"),
            capability_result = body.get("capability_result"),
            spc_result        = body.get("spc_result"),
            grr_result        = body.get("grr_result"),
            capa_result       = body.get("capa_result"),
            meta              = meta,
        )
        _report_cache[report_id] = tmp_path
        size_kb  = round(os.path.getsize(tmp_path) / 1024)
        sections = sum(1 for k in [
            "normality_result","capability_result",
            "spc_result","grr_result","capa_result",
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
        raise HTTPException(404, "Report not found. Please regenerate.")
    return FileResponse(
        path, media_type="application/pdf",
        filename=f"statmind_report_{report_id}.pdf",
    )

# ── Static frontend ───────────────────────────────────────────────────────────
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        with open(html_path) as f:
            content = f.read()
        # Make API calls relative in production
        content = content.replace(
            "const API=window.location.origin.includes('localhost')?'http://localhost:8010':'';",
            "const API='';"
        )
        return HTMLResponse(content)
    return HTMLResponse(
        "<h1>StatMind v2.0</h1>"
        "<p>Place statmind_r3.html in /static/index.html</p>"
        "<p><a href='/api/docs'>API Docs</a></p>"
    )

# ── Dev runner ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"\n  StatMind v2.0  |  http://localhost:{PORT}")
    print(f"  API docs:      http://localhost:{PORT}/api/docs")
    print(f"  Sessions:      1-Normality 2-Capability 3-SPC 4-GRR 5-CAPA 6-PDF\n")
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)


# ══ Phase 1 Extensions ════════════════════════════════════════════════════════

# ── E1: Hypothesis Testing ────────────────────────────────────────────────────
@app.post("/api/v1/hypothesis/two-sample-t")
async def hyp_two_sample_t(request: Request):
    body = await request.json()
    try:
        from hypothesis import two_sample_t
        import dataclasses
        a = np.array(body["group_a"], dtype=float)
        b = np.array(body["group_b"], dtype=float)
        result = two_sample_t(a, b,
            name_a=body.get("name_a","Group A"),
            name_b=body.get("name_b","Group B"),
            alpha=body.get("alpha",0.05),
            equal_var=body.get("equal_var",False))
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/hypothesis/paired-t")
async def hyp_paired_t(request: Request):
    body = await request.json()
    try:
        from hypothesis import paired_t
        import dataclasses
        a = np.array(body["group_a"], dtype=float)
        b = np.array(body["group_b"], dtype=float)
        result = paired_t(a, b,
            name_a=body.get("name_a","Before"),
            name_b=body.get("name_b","After"),
            alpha=body.get("alpha",0.05))
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/hypothesis/one-way-anova")
async def hyp_anova(request: Request):
    body = await request.json()
    try:
        from hypothesis import one_way_anova
        import dataclasses
        groups = [np.array(g, dtype=float) for g in body["groups"]]
        names  = body.get("names", [f"Group {i+1}" for i in range(len(groups))])
        result = one_way_anova(groups, names, alpha=body.get("alpha",0.05))
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/hypothesis/mann-whitney")
async def hyp_mann_whitney(request: Request):
    body = await request.json()
    try:
        from hypothesis import mann_whitney
        import dataclasses
        a = np.array(body["group_a"], dtype=float)
        b = np.array(body["group_b"], dtype=float)
        result = mann_whitney(a, b,
            name_a=body.get("name_a","Group A"),
            name_b=body.get("name_b","Group B"),
            alpha=body.get("alpha",0.05))
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/hypothesis/kruskal-wallis")
async def hyp_kruskal(request: Request):
    body = await request.json()
    try:
        from hypothesis import kruskal_wallis
        import dataclasses
        groups = [np.array(g, dtype=float) for g in body["groups"]]
        names  = body.get("names", [f"Group {i+1}" for i in range(len(groups))])
        result = kruskal_wallis(groups, names, alpha=body.get("alpha",0.05))
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/hypothesis/variance-test")
async def hyp_variance(request: Request):
    body = await request.json()
    try:
        from hypothesis import variance_test
        import dataclasses
        groups = [np.array(g, dtype=float) for g in body["groups"]]
        names  = body.get("names", [f"Group {i+1}" for i in range(len(groups))])
        result = variance_test(groups, names, alpha=body.get("alpha",0.05))
        return jd(dataclasses.asdict(result))
    except Exception as e:
        raise HTTPException(400, str(e))

# Run hypothesis test from uploaded file columns
@app.post("/api/v1/hypothesis/from-file")
async def hyp_from_file(
    file: UploadFile = File(...),
    test: str = Query(...),          # two_t | paired_t | anova | mann_whitney | kruskal | variance
    columns: str = Query(...),       # comma-separated column names
    alpha: float = Query(0.05),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))

    col_list = [col.strip() for col in columns.split(",")]
    missing  = [col for col in col_list if col not in result.df.columns]
    if missing:
        raise HTTPException(404, f"Columns not found: {missing}. Available: {result.numeric_columns}")

    groups = [result.df[col].dropna().values.astype(float) for col in col_list]
    names  = col_list

    import dataclasses as dc
    try:
        from hypothesis import two_sample_t, paired_t, one_way_anova, mann_whitney, kruskal_wallis, variance_test
        if test == "two_t" and len(groups) >= 2:
            res = two_sample_t(groups[0], groups[1], names[0], names[1], alpha)
        elif test == "paired_t" and len(groups) >= 2:
            res = paired_t(groups[0], groups[1], names[0], names[1], alpha)
        elif test == "anova":
            res = one_way_anova(groups, names, alpha)
        elif test == "mann_whitney" and len(groups) >= 2:
            res = mann_whitney(groups[0], groups[1], names[0], names[1], alpha)
        elif test == "kruskal":
            res = kruskal_wallis(groups, names, alpha)
        elif test == "variance":
            res = variance_test(groups, names, alpha)
        else:
            raise HTTPException(400, f"Unknown test '{test}' or insufficient columns")
        return jd(dc.asdict(res))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))

# ── E2: Pareto Chart ──────────────────────────────────────────────────────────
@app.post("/api/v1/pareto/analyze")
async def pareto_analyze(
    file: UploadFile = File(...),
    category_col: str = Query(...),
    count_col: str = Query(None),
    threshold: float = Query(80.0),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    import dataclasses as dc
    from pareto import pareto_from_dataframe
    try:
        pr = pareto_from_dataframe(result.df, category_col, count_col,
                                   title=f"Pareto — {category_col}", threshold=threshold)
        return jd(dc.asdict(pr))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/pareto/columns")
async def pareto_columns(file: UploadFile = File(...)):
    """Return all columns including non-numeric (for category column selection)."""
    c = await file.read()
    try:
        from file_parser import parse_any_file as paf
        import pandas as pd, io
        # Parse raw to get all columns including text
        try:
            raw_bytes = c
            fname = file.filename.lower()
            if fname.endswith(('.xlsx','.xls')):
                df = pd.read_excel(io.BytesIO(raw_bytes))
            else:
                sample = raw_bytes[:2048].decode('utf-8', errors='replace')
                sep = '\t' if '\t' in sample else ';' if ';' in sample else ','
                df = pd.read_csv(io.BytesIO(raw_bytes), sep=sep, on_bad_lines='skip')
        except Exception:
            df = pd.DataFrame()
        all_cols = df.columns.tolist()
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        return jd({"all_columns": all_cols, "numeric_columns": num_cols, "rows": len(df)})
    except Exception as e:
        raise HTTPException(400, str(e))

# ── E3: Capability Sixpack ────────────────────────────────────────────────────
@app.post("/api/v1/sixpack/analyze")
async def sixpack_analyze(
    file: UploadFile = File(...),
    column: str = Query(...),
    usl: float = Query(...),
    lsl: float = Query(...),
    target: float = Query(None),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    import dataclasses as dc
    from sixpack import build_sixpack
    try:
        sp = build_sixpack(result.df[column].dropna().values.astype(float),
                           column, usl, lsl, target)
        return jd(dc.asdict(sp))
    except ValueError as e:
        raise HTTPException(400, str(e))

# ── E4: Regression ────────────────────────────────────────────────────────────
@app.post("/api/v1/regression/analyze")
async def regression_analyze(
    file: UploadFile = File(...),
    y_col: str = Query(...),
    x_cols: str = Query(...),   # comma-separated
    alpha: float = Query(0.05),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    x_list = [col.strip() for col in x_cols.split(",")]
    missing = [col for col in [y_col] + x_list if col not in result.df.columns]
    if missing:
        raise HTTPException(404, f"Columns not found: {missing}")
    import dataclasses as dc
    from regression import simple_linear_regression, multiple_regression
    try:
        y_data = result.df[y_col].values.astype(float)
        if len(x_list) == 1:
            x_data = result.df[x_list[0]].values.astype(float)
            reg = simple_linear_regression(x_data, y_data, x_list[0], y_col, alpha)
        else:
            X = result.df[x_list].values.astype(float)
            reg = multiple_regression(X, y_data, x_list, y_col, alpha)
        return jd(dc.asdict(reg))
    except Exception as e:
        raise HTTPException(400, str(e))
