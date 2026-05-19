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


# ══ Phase 2 Extensions ════════════════════════════════════════════════════════

# ── E5: Box-Cox Transformation ────────────────────────────────────────────────
@app.post("/api/v1/transformation/analyze")
async def transform_analyze(
    file: UploadFile = File(...),
    column: str = Query(...),
    usl: float = Query(None), lsl: float = Query(None),
    alpha: float = Query(0.05),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    import dataclasses as dc
    from transformation import auto_transform
    try:
        r = auto_transform(result.df[column].dropna().values.astype(float),
                           column, usl, lsl, alpha)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))


# ── E6: Multi-Vari Chart ──────────────────────────────────────────────────────
@app.post("/api/v1/multivari/analyze")
async def multivari_analyze(
    file: UploadFile = File(...),
    value_col: str = Query(...),
    part_col: str = Query(...),
    position_col: str = Query(None),
    time_col: str = Query(None),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))

    # For non-numeric columns, re-read as full DataFrame
    import pandas as pd, io
    try:
        raw = c
        fname = file.filename.lower()
        if fname.endswith(('.xlsx','.xls')):
            df_full = pd.read_excel(io.BytesIO(raw))
        else:
            sample = raw[:2048].decode('utf-8', errors='replace')
            sep = '\t' if '\t' in sample else ';' if ';' in sample else ','
            df_full = pd.read_csv(io.BytesIO(raw), sep=sep, on_bad_lines='skip')
    except Exception:
        df_full = result.df

    if value_col not in df_full.columns:
        raise HTTPException(404, f"Column '{value_col}' not found")
    if part_col not in df_full.columns:
        raise HTTPException(404, f"Part column '{part_col}' not found")

    import dataclasses as dc
    from multivari import analyze_multivari
    try:
        vals  = df_full[value_col].values.astype(float)
        parts = df_full[part_col].values.astype(str)
        positions   = df_full[position_col].values.astype(str) if position_col and position_col in df_full.columns else None
        time_periods = df_full[time_col].values.astype(str) if time_col and time_col in df_full.columns else None
        r = analyze_multivari(vals, parts, positions, time_periods, value_col)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/multivari/columns")
async def multivari_columns(file: UploadFile = File(...)):
    """Return all columns including text for column selection."""
    c = await file.read()
    import pandas as pd, io
    try:
        raw = c
        fname = file.filename.lower()
        if fname.endswith(('.xlsx','.xls')):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            sample = raw[:2048].decode('utf-8', errors='replace')
            sep = '\t' if '\t' in sample else ';' if ';' in sample else ','
            df = pd.read_csv(io.BytesIO(raw), sep=sep, on_bad_lines='skip')
        all_cols = df.columns.tolist()
        num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        return jd({"all_columns": all_cols, "numeric_columns": num_cols, "rows": len(df)})
    except Exception as e:
        raise HTTPException(400, str(e))


# ── E7: DOE ───────────────────────────────────────────────────────────────────
@app.post("/api/v1/doe/generate")
async def doe_generate(request: Request):
    """Generate DOE run matrix (no responses yet)."""
    body = await request.json()
    import dataclasses as dc
    from doe import generate_design
    try:
        factor_names  = body["factor_names"]
        factor_levels = body["factor_levels"]
        design_type   = body.get("design_type", "auto")
        responses     = body.get("responses", None)
        r = generate_design(factor_names, factor_levels, design_type, responses)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/doe/analyze")
async def doe_analyze(request: Request):
    """Analyze DOE with response data."""
    body = await request.json()
    import dataclasses as dc
    from doe import generate_design
    try:
        factor_names  = body["factor_names"]
        factor_levels = body["factor_levels"]
        design_type   = body.get("design_type", "auto")
        responses     = body["responses"]
        if len(responses) == 0:
            raise ValueError("No response data provided.")
        r = generate_design(factor_names, factor_levels, design_type, responses)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))


# ── E8: Tolerance Intervals ───────────────────────────────────────────────────
@app.post("/api/v1/tolerance/analyze")
async def tolerance_analyze(
    file: UploadFile = File(...),
    column: str = Query(...),
    coverage: float = Query(0.99),
    confidence: float = Query(0.95),
    interval_type: str = Query("two_sided"),
    usl: float = Query(None),
    lsl: float = Query(None),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    import dataclasses as dc
    from tolerance_interval import tolerance_interval
    try:
        r = tolerance_interval(result.df[column].dropna().values.astype(float),
                               column, coverage, confidence, interval_type, usl, lsl)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))


# ── E9: Attribute Agreement Analysis ─────────────────────────────────────────
@app.post("/api/v1/aaa/analyze")
async def aaa_analyze(
    file: UploadFile = File(...),
    decision_col: str = Query(...),
    sample_col: str = Query(...),
    appraiser_col: str = Query(...),
    replicate_col: str = Query(None),
    reference_col: str = Query(None),
):
    c = await file.read()
    import pandas as pd, io
    try:
        raw = c
        fname = file.filename.lower()
        if fname.endswith(('.xlsx','.xls')):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            sample = raw[:2048].decode('utf-8', errors='replace')
            sep = '\t' if '\t' in sample else ';' if ';' in sample else ','
            df = pd.read_csv(io.BytesIO(raw), sep=sep, on_bad_lines='skip')
    except Exception as e:
        raise HTTPException(400, str(e))

    for col in [decision_col, sample_col, appraiser_col]:
        if col not in df.columns:
            raise HTTPException(404, f"Column '{col}' not found. Available: {df.columns.tolist()}")

    import dataclasses as dc
    from attribute_agreement import analyze_aaa
    try:
        decisions   = df[decision_col].values.astype(str)
        samples     = df[sample_col].values.astype(str)
        appraisers  = df[appraiser_col].values.astype(str)
        replicates  = df[replicate_col].values.astype(str) if replicate_col and replicate_col in df.columns else np.ones(len(df), dtype=str)
        reference   = df[reference_col].values.astype(str) if reference_col and reference_col in df.columns else None
        r = analyze_aaa(decisions, samples, appraisers, replicates, reference)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/aaa/columns")
async def aaa_columns(file: UploadFile = File(...)):
    c = await file.read()
    import pandas as pd, io
    try:
        raw = c
        fname = file.filename.lower()
        if fname.endswith(('.xlsx','.xls')):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            sample = raw[:2048].decode('utf-8', errors='replace')
            sep = '\t' if '\t' in sample else ';' if ';' in sample else ','
            df = pd.read_csv(io.BytesIO(raw), sep=sep, on_bad_lines='skip')
        return jd({"all_columns": df.columns.tolist(),
                   "numeric_columns": df.select_dtypes(include=[np.number]).columns.tolist(),
                   "rows": len(df)})
    except Exception as e:
        raise HTTPException(400, str(e))


# ══ Phase 3 Extensions ════════════════════════════════════════════════════════

# ── E10: Multi-Dataset Comparison ────────────────────────────────────────────
@app.post("/api/v1/comparison/analyze")
async def comparison_analyze(request: Request):
    """
    Body: { datasets: [{name, values}], parameter, usl, lsl, alpha }
    Or upload via multipart with dataset_names query param.
    """
    body = await request.json()
    import dataclasses as dc
    from comparison import compare_datasets
    try:
        raw_ds = body.get("datasets", [])
        datasets = [(d["name"], np.array(d["values"], dtype=float)) for d in raw_ds]
        r = compare_datasets(
            datasets,
            parameter=body.get("parameter", "Measurement"),
            usl=body.get("usl"), lsl=body.get("lsl"),
            alpha=body.get("alpha", 0.05),
        )
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/comparison/from-files")
async def comparison_from_files(
    files: list[UploadFile] = File(...),
    names: str = Query(...),          # comma-separated dataset names
    column: str = Query(...),         # which column to compare
    usl: float = Query(None),
    lsl: float = Query(None),
):
    """Upload multiple files, compare the same column across them."""
    import dataclasses as dc
    from comparison import compare_datasets
    name_list = [n.strip() for n in names.split(",")]
    datasets = []
    for i, f in enumerate(files):
        c = await f.read()
        try:
            result = parse_any_file(c, f.filename)
        except Exception as e:
            raise HTTPException(400, f"File {f.filename}: {e}")
        if column not in result.df.columns:
            raise HTTPException(404, f"Column '{column}' not in {f.filename}. Available: {result.numeric_columns}")
        dname = name_list[i] if i < len(name_list) else f.filename
        datasets.append((dname, result.df[column].dropna().values.astype(float)))
    try:
        r = compare_datasets(datasets, parameter=column, usl=usl, lsl=lsl)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))


# ── E11: Live Data Stream ─────────────────────────────────────────────────────
@app.post("/api/v1/stream/create")
async def stream_create(request: Request):
    body = await request.json()
    import dataclasses as dc
    from livestream import create_stream
    try:
        r = create_stream(
            stream_id=body["stream_id"],
            parameter=body.get("parameter", body["stream_id"]),
            usl=body.get("usl"), lsl=body.get("lsl"),
        )
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/stream/{stream_id}/add")
async def stream_add(stream_id: str, request: Request):
    body = await request.json()
    import dataclasses as dc
    from livestream import add_measurement
    try:
        r = add_measurement(stream_id, float(body["value"]),
                            body.get("timestamp"))
        return jd(dc.asdict(r))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/stream/{stream_id}/batch")
async def stream_batch(stream_id: str, request: Request):
    body = await request.json()
    import dataclasses as dc
    from livestream import add_batch
    try:
        r = add_batch(stream_id, body["values"], body.get("timestamps"))
        return jd(dc.asdict(r))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/v1/stream/{stream_id}/status")
async def stream_status(stream_id: str):
    import dataclasses as dc
    from livestream import get_stream_status
    try:
        return jd(dc.asdict(get_stream_status(stream_id)))
    except KeyError as e:
        raise HTTPException(404, str(e))

@app.get("/api/v1/stream/list")
async def stream_list():
    import dataclasses as dc
    from livestream import list_streams
    return jd({"streams": [dc.asdict(s) for s in list_streams()]})

@app.delete("/api/v1/stream/{stream_id}")
async def stream_delete(stream_id: str):
    from livestream import delete_stream
    return jd({"deleted": delete_stream(stream_id)})


# ── E12: Process Dashboard ────────────────────────────────────────────────────
@app.post("/api/v1/dashboard/build")
async def dashboard_build(request: Request):
    """
    Body: { title, sessions: [{name, capability, spc, grr, normality}] }
    Accepts the result dicts from any previous sessions.
    """
    body = await request.json()
    import dataclasses as dc
    from dashboard import build_dashboard
    try:
        r = build_dashboard(
            session_results=body.get("sessions", []),
            title=body.get("title", "StatMind Process Dashboard"),
        )
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))


# ══ New Phase 1 (N1-N8) ═══════════════════════════════════════════════════════

@app.post("/api/v1/cusum/analyze")
async def cusum_analyze(file: UploadFile=File(...), column: str=Query(...),
    k: float=Query(0.5), h: float=Query(5.0)):
    c=await file.read()
    try: r=parse_any_file(c,file.filename)
    except Exception as e: raise HTTPException(400,str(e))
    if column not in r.df.columns: raise HTTPException(404,f"Column '{column}' not found")
    import dataclasses as dc
    from cusum_ewma import tabular_cusum
    try: return jd(dc.asdict(tabular_cusum(r.df[column].dropna().values.astype(float),column,k=k,h=h)))
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/api/v1/ewma/analyze")
async def ewma_analyze(file: UploadFile=File(...), column: str=Query(...),
    lam: float=Query(0.2), L: float=Query(3.0)):
    c=await file.read()
    try: r=parse_any_file(c,file.filename)
    except Exception as e: raise HTTPException(400,str(e))
    if column not in r.df.columns: raise HTTPException(404,f"Column '{column}' not found")
    import dataclasses as dc
    from cusum_ewma import ewma_chart
    try: return jd(dc.asdict(ewma_chart(r.df[column].dropna().values.astype(float),column,lam=lam,L=L)))
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/api/v1/sample-size/capability")
async def ss_capability(request: Request):
    b=await request.json()
    import dataclasses as dc
    from sample_size import sample_size_capability
    return jd(dc.asdict(sample_size_capability(b.get("target_cpk",1.33),b.get("confidence",0.95),b.get("precision",0.10))))

@app.post("/api/v1/sample-size/ttest")
async def ss_ttest(request: Request):
    b=await request.json()
    import dataclasses as dc
    from sample_size import sample_size_ttest
    return jd(dc.asdict(sample_size_ttest(b.get("effect_size",0.5),b.get("alpha",0.05),b.get("power",0.80),b.get("two_tailed",True),b.get("two_sample",True))))

@app.post("/api/v1/sample-size/grr")
async def ss_grr(request: Request):
    b=await request.json()
    import dataclasses as dc
    from sample_size import sample_size_grr
    return jd(dc.asdict(sample_size_grr(b.get("target_grr_pct",10.0),b.get("n_operators",3),b.get("n_replicates",2))))

@app.post("/api/v1/sample-size/attribute")
async def ss_attribute(request: Request):
    b=await request.json()
    import dataclasses as dc
    from sample_size import sample_size_attribute
    return jd(dc.asdict(sample_size_attribute(b.get("lot_size",1000),b.get("aql",1.0),b.get("inspection_level","II"))))

@app.post("/api/v1/sample-size/spc")
async def ss_spc(request: Request):
    b=await request.json()
    import dataclasses as dc
    from sample_size import sample_size_spc
    return jd(dc.asdict(sample_size_spc(b.get("shift_sigma",1.0),b.get("alpha",0.0027),b.get("power",0.80),b.get("chart_type","Shewhart"))))

@app.post("/api/v1/correlation/analyze")
async def correlation_analyze(file: UploadFile=File(...), alpha: float=Query(0.05), min_r: float=Query(0.3)):
    c=await file.read()
    try: r=parse_any_file(c,file.filename)
    except Exception as e: raise HTTPException(400,str(e))
    import dataclasses as dc
    from correlation import correlation_matrix
    try: return jd(dc.asdict(correlation_matrix(r.df,alpha=alpha,min_r=min_r)))
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/api/v1/nonnormal-capability/analyze")
async def nonnormal_cap(file: UploadFile=File(...), column: str=Query(...),
    usl: float=Query(None), lsl: float=Query(None)):
    c=await file.read()
    try: r=parse_any_file(c,file.filename)
    except Exception as e: raise HTTPException(400,str(e))
    if column not in r.df.columns: raise HTTPException(404,f"Column '{column}' not found")
    import dataclasses as dc
    from nonnormal_capability import nonnormal_capability
    try: return jd(dc.asdict(nonnormal_capability(r.df[column].dropna().values.astype(float),column,usl,lsl)))
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/api/v1/uncertainty/calculate")
async def uncertainty_calc(request: Request):
    b=await request.json()
    import dataclasses as dc
    from uncertainty import calculate_uncertainty, UncertaintyComponent
    try:
        r=calculate_uncertainty(b.get("measurand","Measurement"),b.get("unit",""),
            b.get("mean_value",0.0),b.get("type_a_data"),b.get("type_b_inputs",[]),b.get("k",2.0))
        return jd(dc.asdict(r))
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/api/v1/outliers/detect")
async def outliers_detect(file: UploadFile=File(...), column: str=Query(...),
    alpha: float=Query(0.05), usl: float=Query(None), lsl: float=Query(None)):
    c=await file.read()
    try: r=parse_any_file(c,file.filename)
    except Exception as e: raise HTTPException(400,str(e))
    if column not in r.df.columns: raise HTTPException(404,f"Column '{column}' not found")
    import dataclasses as dc
    from outliers import detect_outliers
    try: return jd(dc.asdict(detect_outliers(r.df[column].dropna().values.astype(float),column,alpha,5,usl,lsl)))
    except Exception as e: raise HTTPException(400,str(e))

@app.post("/api/v1/capa/v2/generate-subrange")
async def capa_subrange(request: Request):
    b=await request.json()
    import dataclasses as dc
    from capa_rules_engine import run_capa_engine_subrange
    try:
        r=run_capa_engine_subrange(b.get("normality_result"),b.get("capability_result"),
            b.get("spc_result"),b.get("grr_result"),
            b.get("process_context",""),b.get("parameter_name",""),b.get("process_type",""),
            b.get("subrange_start"),b.get("subrange_end"),b.get("total_points"))
        return jd({"success":True,**r})
    except Exception as e: raise HTTPException(500,str(e))


# ══ New Phase 2 (N9–N15) ══════════════════════════════════════════════════════

# ── N9: DMAIC Project Tracker ─────────────────────────────────────────────────
@app.post("/api/v1/dmaic/create")
async def dmaic_create(request: Request):
    b = await request.json()
    import dataclasses as dc
    from dmaic import create_project
    try:
        r = create_project(b.get("title","New Project"), b.get("process",""),
            b.get("parameter",""), b.get("problem_statement",""),
            b.get("goal",""), b.get("team",""), b.get("target_date",""))
        return jd(dc.asdict(r))
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/api/v1/dmaic/{project_id}/update")
async def dmaic_update(project_id: str, request: Request):
    b = await request.json()
    import dataclasses as dc
    from dmaic import update_phase
    try:
        r = update_phase(project_id, b.get("phase_name","Define"),
            b.get("status"), b.get("completion_pct"), b.get("notes"),
            b.get("tool"), b.get("analysis_summary"))
        return jd(dc.asdict(r))
    except KeyError as e: raise HTTPException(404, str(e))
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/v1/dmaic/list")
async def dmaic_list():
    import dataclasses as dc
    from dmaic import list_projects
    return jd({"projects": [dc.asdict(p) for p in list_projects()]})

@app.get("/api/v1/dmaic/{project_id}")
async def dmaic_get(project_id: str):
    import dataclasses as dc
    from dmaic import get_project
    try: return jd(dc.asdict(get_project(project_id)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.delete("/api/v1/dmaic/{project_id}")
async def dmaic_delete(project_id: str):
    from dmaic import delete_project
    return jd({"deleted": delete_project(project_id)})


# ── N10: Weibull / Reliability ────────────────────────────────────────────────
@app.post("/api/v1/weibull/analyze")
async def weibull_analyze(
    file: UploadFile = File(...),
    column: str = Query(...),
    censored_col: str = Query(None),
):
    c = await file.read()
    try: r = parse_any_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    if column not in r.df.columns: raise HTTPException(404, f"Column '{column}' not found")
    import dataclasses as dc
    from weibull import weibull_analysis
    try:
        data = r.df[column].dropna().values.astype(float)
        censored = r.df[censored_col].values.astype(bool) if censored_col and censored_col in r.df.columns else None
        return jd(dc.asdict(weibull_analysis(data, column, censored)))
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/api/v1/weibull/from-list")
async def weibull_from_list(request: Request):
    b = await request.json()
    import dataclasses as dc, numpy as np
    from weibull import weibull_analysis
    try:
        times = np.array(b["times"], dtype=float)
        censored = np.array(b["censored"], dtype=bool) if b.get("censored") else None
        return jd(dc.asdict(weibull_analysis(times, b.get("column","Failure Time"), censored)))
    except Exception as e: raise HTTPException(400, str(e))


# ── N11: PFMEA ───────────────────────────────────────────────────────────────
@app.post("/api/v1/pfmea/create")
async def pfmea_create(request: Request):
    b = await request.json()
    from pfmea import create_pfmea
    return jd(create_pfmea(b.get("title","PFMEA"), b.get("process","")))

@app.post("/api/v1/pfmea/{fmea_id}/add-entry")
async def pfmea_add(fmea_id: str, request: Request):
    b = await request.json()
    import dataclasses as dc
    from pfmea import add_entry
    try: return jd(dc.asdict(add_entry(fmea_id, b)))
    except KeyError as e: raise HTTPException(404, str(e))
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/v1/pfmea/{fmea_id}/report")
async def pfmea_report(fmea_id: str):
    import dataclasses as dc
    from pfmea import build_report
    try: return jd(dc.asdict(build_report(fmea_id)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/pfmea/list")
async def pfmea_list():
    from pfmea import list_pfmeas
    return jd({"pfmeas": list_pfmeas()})


# ── N12: Column Calculator ────────────────────────────────────────────────────
@app.post("/api/v1/column-calc/calculate")
async def col_calc(
    file: UploadFile = File(...),
    formula: str = Query(...),
    new_col_name: str = Query("Calculated"),
):
    c = await file.read()
    try: r = parse_any_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    import dataclasses as dc
    from column_calc import calculate_column
    try: return jd(dc.asdict(calculate_column(r.df, formula, new_col_name)))
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/v1/column-calc/templates")
async def col_calc_templates():
    from column_calc import FORMULA_TEMPLATES
    return jd({"templates": FORMULA_TEMPLATES})


# ── N13: Time Series ──────────────────────────────────────────────────────────
@app.post("/api/v1/timeseries/analyze")
async def timeseries_analyze(
    file: UploadFile = File(...),
    column: str = Query(...),
    period: int = Query(None),
    n_forecast: int = Query(10),
):
    c = await file.read()
    try: r = parse_any_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    if column not in r.df.columns: raise HTTPException(404, f"Column '{column}' not found")
    import dataclasses as dc
    from timeseries import analyze_timeseries
    try:
        return jd(dc.asdict(analyze_timeseries(
            r.df[column].dropna().values.astype(float), column, period, n_forecast)))
    except Exception as e: raise HTTPException(400, str(e))


# ── N14: Graph Builder (dynamic chart config endpoint) ───────────────────────
@app.post("/api/v1/graph-builder/build")
async def graph_builder(
    file: UploadFile = File(...),
    x_col: str = Query(...),
    y_col: str = Query(None),
    color_col: str = Query(None),
    chart_type: str = Query("scatter"),  # scatter/bar/line/histogram/box
):
    c = await file.read()
    try: r = parse_any_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    df = r.df
    try:
        import pandas as pd
        result = {"chart_type": chart_type, "x_col": x_col, "y_col": y_col,
                  "color_col": color_col, "n": len(df)}
        if chart_type == "histogram":
            col_data = df[x_col].dropna().values.astype(float)
            counts, edges = np.histogram(col_data, bins=min(30, len(col_data)//2))
            result["data"] = {"bin_centers": [float((edges[i]+edges[i+1])/2) for i in range(len(edges)-1)],
                              "counts": counts.tolist()}
        elif chart_type in ("scatter", "line") and y_col:
            mask = df[x_col].notna() & df[y_col].notna()
            result["data"] = {"x": df[x_col][mask].tolist(), "y": df[y_col][mask].tolist()}
            if color_col and color_col in df.columns:
                result["data"]["color"] = df[color_col][mask].tolist()
        elif chart_type == "bar":
            if df[x_col].dtype == object:
                vc = df[x_col].value_counts()
                result["data"] = {"categories": vc.index.tolist(), "values": vc.values.tolist()}
            elif y_col:
                grouped = df.groupby(x_col)[y_col].mean()
                result["data"] = {"categories": [str(k) for k in grouped.index.tolist()],
                                  "values": grouped.values.tolist()}
        elif chart_type == "box":
            if y_col and color_col and color_col in df.columns:
                groups = {}
                for grp, sub in df.groupby(color_col):
                    vals = sub[y_col].dropna().values.astype(float)
                    q1,med,q3 = np.percentile(vals,[25,50,75])
                    iqr = q3-q1
                    groups[str(grp)] = {"q1":float(q1),"median":float(med),"q3":float(q3),
                        "whisker_lo":float(max(vals[vals>=q1-1.5*iqr].min(),vals.min())),
                        "whisker_hi":float(min(vals[vals<=q3+1.5*iqr].max(),vals.max())),
                        "mean":float(np.mean(vals)),"n":len(vals)}
                result["data"] = groups
            elif y_col:
                vals = df[y_col].dropna().values.astype(float)
                q1,med,q3 = np.percentile(vals,[25,50,75])
                result["data"] = {"q1":float(q1),"median":float(med),"q3":float(q3),"mean":float(np.mean(vals))}
        return jd(result)
    except Exception as e: raise HTTPException(400, str(e))


# ── N15: Load expanded CAPA rules ─────────────────────────────────────────────
@app.get("/api/v1/capa/expanded-rules")
async def capa_expanded_rules():
    import dataclasses as dc
    try:
        from capa_database_expanded import EXPANDED_RULES
        return jd({"count": len(EXPANDED_RULES),
                   "rules": [{"id":r.rule_id,"process":r.process,"pattern":r.fault_pattern,
                               "severity":r.severity} for r in EXPANDED_RULES]})
    except Exception as e: raise HTTPException(500, str(e))


# ══ New Phase 3 (N16–N20) ════════════════════════════════════════════════════

# ── N16: AI Natural Language Query ───────────────────────────────────────────
@app.post("/api/v1/ai/query")
async def ai_query_endpoint(
    file: UploadFile = File(...),
    query: str = Query(...),
    column: str = Query(None),
    usl: float = Query(None),
    lsl: float = Query(None),
    process_type: str = Query(""),
):
    """
    Natural language query endpoint.
    "Is Chamber A different from Chamber B?" → auto-runs correct test.
    """
    c = await file.read()
    try:
        parsed = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    import dataclasses as dc
    from ai_query import route_query
    try:
        df_numeric = parsed.df.select_dtypes(include=[np.number])
        if df_numeric.empty:
            raise HTTPException(400, "No numeric columns found in file.")
        r = route_query(query, df_numeric, column, usl, lsl, process_type)
        return jd({
            "query": r.query,
            "analysis_type": r.analysis_type,
            "intent": {
                "category": r.intent.category,
                "confidence": r.intent.confidence,
                "parameters_mentioned": r.intent.parameters_mentioned,
                "test_recommended": r.intent.test_recommended,
                "reasoning": r.intent.reasoning,
            },
            "answer": r.answer,
            "key_finding": r.key_finding,
            "recommendation": r.recommendation,
            "follow_ups": r.follow_ups,
            "chart_hint": r.chart_hint,
            "result": r.result,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/v1/ai/classify")
async def ai_classify_intent(request: Request):
    """Classify a query intent without running the analysis."""
    b = await request.json()
    import dataclasses as dc
    from ai_query import classify_intent
    intent = classify_intent(b.get("query",""), b.get("columns",[]))
    return jd(dc.asdict(intent))


# ── N17: AI Report Narrative ──────────────────────────────────────────────────
@app.post("/api/v1/ai/narrative")
async def ai_narrative_endpoint(request: Request):
    """
    Generate a written plain-English narrative from analysis results.
    POST: { parameter, process_type, normality_result, capability_result,
             spc_result, grr_result, capa_result }
    """
    b = await request.json()
    import dataclasses as dc
    from ai_narrative import generate_narrative
    try:
        r = generate_narrative(
            parameter=b.get("parameter",""),
            process_type=b.get("process_type",""),
            normality_result=b.get("normality_result"),
            capability_result=b.get("capability_result"),
            spc_result=b.get("spc_result"),
            grr_result=b.get("grr_result"),
            capa_result=b.get("capa_result"),
        )
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(500, str(e))


# ── N18: Shareable Analysis Links ─────────────────────────────────────────────
@app.post("/api/v1/share/encode")
async def share_encode(request: Request):
    """Encode analysis results into a shareable URL token."""
    b = await request.json()
    import dataclasses as dc
    from share_link import encode_results
    try:
        r = encode_results(
            results=b.get("results", {}),
            parameter=b.get("parameter",""),
            base_url=b.get("base_url","https://statmind-production.up.railway.app"),
        )
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.get("/api/v1/share/decode")
async def share_decode(token: str = Query(...)):
    """Decode a share token back to summary data."""
    from share_link import decode_share_token
    try:
        data = decode_share_token(token)
        return jd({"success": True, "data": data})
    except Exception as e:
        raise HTTPException(400, str(e))


# ── N19: MES Integration / Webhook Alerts ─────────────────────────────────────
# In-memory webhook registry
_webhooks: dict = {}
_alert_log: list = []

@app.post("/api/v1/mes/webhook/register")
async def mes_register_webhook(request: Request):
    """Register a webhook URL for SPC alarm notifications."""
    b = await request.json()
    wid = f"wh-{len(_webhooks)+1:04d}"
    _webhooks[wid] = {
        "id": wid,
        "url": b.get("url",""),
        "stream_id": b.get("stream_id","*"),
        "alarm_types": b.get("alarm_types",["WE1","WE4"]),
        "registered_at": __import__("datetime").datetime.now().isoformat(),
    }
    return jd({"webhook_id": wid, "status": "registered", **_webhooks[wid]})

@app.post("/api/v1/mes/ingest")
async def mes_ingest(request: Request):
    """
    MES data ingestion endpoint.
    POST: { stream_id, measurements: [{value, timestamp, equipment_id}] }
    Returns: SPC status + any alarms triggered.
    """
    b = await request.json()
    sid = b.get("stream_id","mes_default")
    measurements = b.get("measurements",[])
    if not measurements:
        raise HTTPException(400, "No measurements provided.")
    import dataclasses as dc
    from livestream import create_stream, add_batch, get_stream_status
    try:
        if sid not in __import__("livestream")._streams:
            create_stream(sid, b.get("parameter",sid),
                         b.get("usl"), b.get("lsl"))
        values = [float(m["value"]) for m in measurements]
        timestamps = [m.get("timestamp") for m in measurements]
        status = add_batch(sid, values, timestamps)
        # Log any alarms
        if status.alert_message:
            _alert_log.append({
                "stream_id": sid,
                "alert": status.alert_message,
                "timestamp": __import__("datetime").datetime.now().isoformat(),
                "last_value": status.last_value,
            })
        return jd({
            "stream_id": sid,
            "n_ingested": len(values),
            "in_control": status.in_control,
            "total_alarms": status.total_alarms_window,
            "alert_message": status.alert_message,
            "cpk": status.cpk,
            "mean": status.mean,
            "ucl": status.ucl, "cl": status.cl, "lcl": status.lcl,
        })
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/api/v1/mes/alert-log")
async def mes_alert_log(limit: int = Query(50)):
    """Return recent SPC alert log for MES consumption."""
    return jd({"alerts": _alert_log[-limit:], "total": len(_alert_log)})

@app.get("/api/v1/mes/webhooks")
async def mes_webhooks():
    return jd({"webhooks": list(_webhooks.values())})


# ── N20: Accessibility Configuration ──────────────────────────────────────────
@app.get("/api/v1/accessibility/config")
async def accessibility_config(
    mode: str = Query("default"),
    font_size: str = Query("default"),
    reduce_motion: bool = Query(False),
    platform: str = Query("windows"),
):
    """Return CSS variable overrides and chart colors for a given accessibility mode."""
    import dataclasses as dc
    from accessibility import get_accessibility_config, get_keyboard_shortcuts
    cfg = get_accessibility_config(mode, font_size, reduce_motion)
    shortcuts = get_keyboard_shortcuts(platform)
    return jd({
        **dc.asdict(cfg),
        "keyboard_shortcuts": shortcuts,
        "available_modes": ["default","deuteranopia","protanopia","high_contrast","print"],
        "available_font_sizes": ["small","default","large","xlarge"],
    })


# ══ Sprint 1 & 2: DOE Full UI, Tolerance Stack-Up, Fishbone, Control Plan, MSA Linearity ═══

# ── P1-A: DOE Full Interactive (reuses existing /doe routes, adds run matrix endpoint) ─────
@app.get("/api/v1/doe/designs")
async def doe_designs():
    """Return all available DOE design types with n_runs for given n_factors."""
    return jd({"designs": [
        {"type":"full","label":"Full Factorial","description":"All combinations. Best for ≤4 factors.","runs_formula":"2^k"},
        {"type":"half","label":"Half Fraction (2^k-1)","description":"Half the runs. Good for 5–6 factors. Resolution V.","runs_formula":"2^(k-1)"},
        {"type":"quarter","label":"Quarter Fraction (2^k-2)","description":"Quarter the runs. For 7–8 factors. Resolution IV.","runs_formula":"2^(k-2)"},
        {"type":"auto","label":"Auto-select","description":"StatMind picks the best design for your number of factors.","runs_formula":"auto"},
        {"type":"plackett_burman","label":"Plackett-Burman","description":"Screening design. Up to 11 factors in 12 runs.","runs_formula":"12 or 20"},
    ]})

@app.post("/api/v1/doe/preview")
async def doe_preview(request: Request):
    """Preview run matrix before committing."""
    b = await request.json()
    import dataclasses as dc
    from doe import generate_design
    try:
        r = generate_design(b["factor_names"], b["factor_levels"], b.get("design_type","auto"))
        return jd({"n_runs": r.n_runs, "design_type": r.design_type,
                   "generator": r.generator, "run_matrix": r.chart_data["run_matrix"],
                   "factor_names": r.factor_names})
    except Exception as e: raise HTTPException(400, str(e))


# ── P1-B: Tolerance Stack-Up ────────────────────────────────────────────────
@app.post("/api/v1/tolerance-stackup/analyze")
async def stackup_analyze(request: Request):
    b = await request.json()
    import dataclasses as dc
    from tolerance_stackup import analyze_stackup
    try:
        r = analyze_stackup(
            title=b.get("title","Tolerance Stack-Up"),
            dimensions=b.get("dimensions",[]),
            min_gap=b.get("min_gap"),
            max_gap=b.get("max_gap"),
            sigma_level=b.get("sigma_level",3.0),
        )
        return jd(dc.asdict(r))
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/v1/tolerance-stackup/templates")
async def stackup_templates():
    return jd({"templates": [
        {"name":"Shaft-Hole Fit","description":"Classic clearance fit","dimensions":[
            {"name":"Hole_ID","nominal":25.0,"plus_tol":0.021,"minus_tol":0.000,"direction":1},
            {"name":"Shaft_OD","nominal":24.980,"plus_tol":0.000,"minus_tol":0.013,"direction":-1}],"min_gap":0.007,"max_gap":0.041},
        {"name":"3-Part Linear Stack","description":"Three parts in a linear assembly","dimensions":[
            {"name":"Part_A","nominal":20.0,"plus_tol":0.05,"minus_tol":0.05,"direction":1},
            {"name":"Part_B","nominal":15.0,"plus_tol":0.03,"minus_tol":0.03,"direction":1},
            {"name":"Housing","nominal":35.5,"plus_tol":0.05,"minus_tol":0.05,"direction":-1}],"min_gap":0.1,"max_gap":0.6},
    ]})


# ── P1-C: Fishbone Diagram ──────────────────────────────────────────────────
@app.post("/api/v1/fishbone/create")
async def fishbone_create(request: Request):
    b = await request.json()
    from fishbone import create_diagram, diagram_to_dict
    try:
        d = create_diagram(b.get("title","Fishbone"), b.get("effect","Problem"), b.get("process",""))
        return jd(diagram_to_dict(d))
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/api/v1/fishbone/{diagram_id}/add-cause")
async def fishbone_add(diagram_id: str, request: Request):
    b = await request.json()
    from fishbone import add_cause, diagram_to_dict
    try:
        d = add_cause(diagram_id, b["branch"], b["cause"],
                      b.get("sub_causes",[]), b.get("severity","medium"), b.get("from_capa",False))
        return jd(diagram_to_dict(d))
    except KeyError as e: raise HTTPException(404, str(e))
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/api/v1/fishbone/{diagram_id}/populate-from-capa")
async def fishbone_from_capa(diagram_id: str, request: Request):
    b = await request.json()
    from fishbone import populate_from_capa, diagram_to_dict
    try:
        d = populate_from_capa(diagram_id, b.get("capa_result",{}))
        return jd(diagram_to_dict(d))
    except KeyError as e: raise HTTPException(404, str(e))
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/v1/fishbone/{diagram_id}")
async def fishbone_get(diagram_id: str):
    from fishbone import get_diagram, diagram_to_dict
    try: return jd(diagram_to_dict(get_diagram(diagram_id)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/fishbone/list")
async def fishbone_list():
    from fishbone import list_diagrams, diagram_to_dict
    return jd({"diagrams": [diagram_to_dict(d) for d in list_diagrams()]})

@app.delete("/api/v1/fishbone/{diagram_id}")
async def fishbone_delete(diagram_id: str):
    from fishbone import delete_diagram
    return jd({"deleted": delete_diagram(diagram_id)})


# ── P2-A: Control Plan ───────────────────────────────────────────────────────
@app.post("/api/v1/control-plan/create")
async def cp_create(request: Request):
    b = await request.json()
    from control_plan import create_plan
    import dataclasses as dc
    p = create_plan(b.get("part_name",""), b.get("part_number",""),
                    b.get("revision","A"), b.get("process_type","Production"),
                    b.get("team",""), b.get("supplier",""), b.get("plant",""))
    return jd(dc.asdict(p))

@app.post("/api/v1/control-plan/{plan_id}/add-entry")
async def cp_add(plan_id: str, request: Request):
    b = await request.json()
    from control_plan import add_entry
    import dataclasses as dc
    try:
        p = add_entry(plan_id, b)
        return jd(dc.asdict(p))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/control-plan/{plan_id}/summary")
async def cp_summary(plan_id: str):
    from control_plan import get_plan, export_summary
    try: return jd(export_summary(get_plan(plan_id)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/control-plan/list")
async def cp_list():
    from control_plan import list_plans
    import dataclasses as dc
    return jd({"plans": [dc.asdict(p) for p in list_plans()]})


# ── P2-C: MSA Linearity & Bias ───────────────────────────────────────────────
@app.post("/api/v1/msa-linearity/analyze")
async def msa_lin_analyze(request: Request):
    b = await request.json()
    import dataclasses as dc
    from msa_linearity import analyze_linearity_bias
    try:
        r = analyze_linearity_bias(
            reference_values=b["reference_values"],
            measurements=b["measurements"],
            gauge_name=b.get("gauge_name","Gauge"),
            process_variation=b.get("process_variation"),
            alpha=b.get("alpha",0.05),
        )
        return jd(dc.asdict(r))
    except Exception as e: raise HTTPException(400, str(e))


# ══ Gap-fill sessions: 8D, Supplier Scorecard, CoPQ, Equivalence, Cpk Trend ═══

# ── 8D Problem Solving ────────────────────────────────────────────────────────
@app.post("/api/v1/8d/create")
async def eightd_create(request: Request):
    b = await request.json()
    from eight_d import create_8d, report_to_dict
    r = create_8d(b.get("title","8D Report"), b.get("part_number",""), b.get("customer",""), b.get("team_members",[]))
    return jd(report_to_dict(r))

@app.post("/api/v1/8d/{report_id}/update")
async def eightd_update(report_id: str, request: Request):
    b = await request.json()
    from eight_d import update_8d, report_to_dict
    try: return jd(report_to_dict(update_8d(report_id, b)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/8d/{report_id}")
async def eightd_get(report_id: str):
    from eight_d import get_8d, report_to_dict
    try: return jd(report_to_dict(get_8d(report_id)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/8d/list")
async def eightd_list():
    from eight_d import list_8d, report_to_dict
    return jd({"reports": [report_to_dict(r) for r in list_8d()]})

@app.delete("/api/v1/8d/{report_id}")
async def eightd_delete(report_id: str):
    from eight_d import delete_8d
    return jd({"deleted": delete_8d(report_id)})


# ── Supplier Scorecard ────────────────────────────────────────────────────────
@app.post("/api/v1/supplier/create")
async def supplier_create(request: Request):
    b = await request.json()
    from supplier_scorecard import create_scorecard, scorecard_to_dict
    try:
        s = create_scorecard(
            b.get("supplier_name",""), b.get("commodity",""), b.get("site_location",""),
            b.get("tier","Tier 1"), float(b.get("incoming_ppm",0)),
            float(b.get("cpk_avg",0)), float(b.get("grr_pct",0)),
            float(b.get("on_time_delivery_pct",100)), int(b.get("open_corrective_actions",0))
        )
        return jd(scorecard_to_dict(s))
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/api/v1/supplier/{supplier_id}/update-kpis")
async def supplier_update(supplier_id: str, request: Request):
    b = await request.json()
    from supplier_scorecard import update_kpis, scorecard_to_dict
    try: return jd(scorecard_to_dict(update_kpis(supplier_id, b)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.post("/api/v1/supplier/{supplier_id}/add-audit")
async def supplier_audit(supplier_id: str, request: Request):
    b = await request.json()
    from supplier_scorecard import add_audit, scorecard_to_dict
    try: return jd(scorecard_to_dict(add_audit(supplier_id, b)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/supplier/list")
async def supplier_list():
    from supplier_scorecard import list_scorecards, rank_suppliers, scorecard_to_dict
    return jd({"suppliers": [scorecard_to_dict(s) for s in rank_suppliers()]})

@app.get("/api/v1/supplier/{supplier_id}")
async def supplier_get(supplier_id: str):
    from supplier_scorecard import get_scorecard, scorecard_to_dict
    try: return jd(scorecard_to_dict(get_scorecard(supplier_id)))
    except KeyError as e: raise HTTPException(404, str(e))


# ── CoPQ Calculator ──────────────────────────────────────────────────────────
@app.post("/api/v1/copq/calculate")
async def copq_calc(request: Request):
    b = await request.json()
    import dataclasses as dc
    from copq import calculate_copq
    try:
        r = calculate_copq(
            process_name=b.get("process_name","Process"),
            annual_production=int(b.get("annual_production",100000)),
            unit_cost=float(b.get("unit_cost",10)),
            cpk_current=float(b.get("cpk_current",1.0)),
            cpk_target=float(b.get("cpk_target",1.33)),
            scrap_cost_per_unit=b.get("scrap_cost_per_unit"),
            rework_cost_per_unit=b.get("rework_cost_per_unit"),
            warranty_cost_per_unit=b.get("warranty_cost_per_unit"),
            inspection_cost_per_unit=b.get("inspection_cost_per_unit"),
            improvement_investment=float(b.get("improvement_investment",0)),
        )
        return jd(dc.asdict(r))
    except Exception as e: raise HTTPException(400, str(e))


# ── Equivalence Testing (TOST) ────────────────────────────────────────────────
@app.post("/api/v1/equivalence/analyze")
async def equiv_analyze(
    file: UploadFile = File(...),
    col_a: str = Query(...),
    col_b: str = Query(...),
    delta_pct: float = Query(5.0),
    alpha: float = Query(0.05),
    usl: float = Query(None),
    lsl: float = Query(None),
):
    c = await file.read()
    try: r = parse_any_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    if col_a not in r.df.columns or col_b not in r.df.columns:
        raise HTTPException(404, f"Columns not found. Available: {r.numeric_columns}")
    import dataclasses as dc
    from equivalence_test import tost_equivalence
    try:
        delta_abs = (delta_pct / 100.0) * abs(float(r.df[col_a].mean()))
        res = tost_equivalence(r.df[col_a].dropna().values.astype(float),
                               r.df[col_b].dropna().values.astype(float),
                               delta=delta_abs, alpha=alpha,
                               name_a=col_a, name_b=col_b)
        return jd(dc.asdict(res))
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/api/v1/equivalence/from-lists")
async def equiv_from_lists(request: Request):
    b = await request.json()
    import dataclasses as dc
    from equivalence_test import tost_equivalence
    try:
        mean_a = float(np.mean(b["data_a"]))
        delta_abs = (b.get("delta_pct", 5.0) / 100.0) * abs(mean_a)
        res = tost_equivalence(np.array(b["data_a"]), np.array(b["data_b"]),
                               delta=delta_abs, alpha=b.get("alpha",0.05),
                               name_a=b.get("name_a","A"), name_b=b.get("name_b","B"))
        return jd(dc.asdict(res))
    except Exception as e: raise HTTPException(400, str(e))


# ── Cpk Trend Tracker ─────────────────────────────────────────────────────────
@app.post("/api/v1/cpk-trend/add-study")
async def cpk_trend_add(request: Request):
    b = await request.json()
    from cpk_trend import add_cpk_study
    try:
        return jd(add_cpk_study(
            parameter=b.get("parameter",""),
            cpk=b.get("cpk"), cp=b.get("cp"), n=b.get("n"),
            mean=b.get("mean"), std=b.get("std"),
            usl=b.get("usl"), lsl=b.get("lsl"),
            date=b.get("date"), notes=b.get("notes","")
        ))
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/api/v1/cpk-trend/add-study-from-file")
async def cpk_trend_from_file(
    file: UploadFile = File(...),
    column: str = Query(...),
    usl: float = Query(None),
    lsl: float = Query(None),
    date: str = Query(None),
    notes: str = Query(""),
):
    c = await file.read()
    try: r = parse_any_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    if column not in r.df.columns: raise HTTPException(404, f"Column not found")
    from cpk_trend import add_cpk_study
    try:
        return jd(add_cpk_study(column, r.df[column].dropna().values.astype(float),
                                usl=usl, lsl=lsl, date=date, notes=notes))
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/v1/cpk-trend/{parameter}")
async def cpk_trend_get(parameter: str, cpk_target: float = Query(1.33)):
    import dataclasses as dc
    from cpk_trend import get_cpk_trend
    try: return jd(dc.asdict(get_cpk_trend(parameter, cpk_target)))
    except ValueError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/cpk-trend/list")
async def cpk_trend_list():
    from cpk_trend import list_parameters
    return jd({"parameters": list_parameters()})


# ══ Gap-fill 2: NPI, IQC/AQL, FAI, NCR, FRACAS, PCN, Reliability Prediction ══

# ── NPI Quality Gate Tracker ──────────────────────────────────────────────────
@app.post("/api/v1/npi/create")
async def npi_create(request: Request):
    b = await request.json()
    from npi_tracker import create_npi, npi_to_dict
    return jd(npi_to_dict(create_npi(b.get("product_name",""), b.get("part_number",""),
        b.get("program",""), b.get("team",""), b.get("target_mp_date",""))))

@app.post("/api/v1/npi/{project_id}/update-gate")
async def npi_update(project_id: str, request: Request):
    b = await request.json()
    from npi_tracker import update_gate, npi_to_dict
    try: return jd(npi_to_dict(update_gate(project_id,
        b.get("phase_name",""), b.get("gate_text",""), b.get("status","Passed"),
        b.get("evidence",""), b.get("owner",""), b.get("target_date",""),
        b.get("cpk"), b.get("grr"), b.get("notes",""))))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/npi/{project_id}")
async def npi_get(project_id: str):
    from npi_tracker import get_npi, npi_to_dict
    try: return jd(npi_to_dict(get_npi(project_id)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/npi/list")
async def npi_list():
    from npi_tracker import list_npi, npi_to_dict
    return jd({"projects": [npi_to_dict(p) for p in list_npi()]})

@app.get("/api/v1/npi/phase-gates")
async def npi_phase_gates():
    from npi_tracker import PHASE_GATES, PHASE_NAMES
    return jd({"phases": PHASE_NAMES, "gates": PHASE_GATES})


# ── IQC / AQL Sampling Plan ──────────────────────────────────────────────────
@app.post("/api/v1/iqc/sampling-plan")
async def iqc_plan(request: Request):
    b = await request.json()
    import dataclasses as dc
    from iqc_sampling import generate_sampling_plan
    try:
        return jd(dc.asdict(generate_sampling_plan(
            lot_size=int(b.get("lot_size", 500)),
            aql=float(b.get("aql", 1.0)),
            inspection_level=b.get("inspection_level", "II"),
            defects_found=b.get("defects_found"),
            usl=b.get("usl"), lsl=b.get("lsl"),
            sample_data=b.get("sample_data"),
        )))
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/v1/iqc/aql-levels")
async def iqc_aql_levels():
    from iqc_sampling import AQL_LEVELS
    return jd({"aql_levels": AQL_LEVELS,
                "inspection_levels": ["I", "II", "III"],
                "standard": "ANSI/ASQ Z1.4 (Attribute) + Z1.9 (Variable)"})


# ── First Article Inspection (FAI) ───────────────────────────────────────────
@app.post("/api/v1/fai/create")
async def fai_create(request: Request):
    b = await request.json()
    from fai_report import create_fai, fai_to_dict
    return jd(fai_to_dict(create_fai(b.get("part_name",""), b.get("part_number",""),
        b.get("revision","A"), b.get("supplier",""), b.get("customer",""),
        b.get("report_type","Full FAI"))))

@app.post("/api/v1/fai/{report_id}/add-measurement")
async def fai_add(report_id: str, request: Request):
    b = await request.json()
    from fai_report import add_measurement, fai_to_dict
    try: return jd(fai_to_dict(add_measurement(report_id, b)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/fai/{report_id}")
async def fai_get(report_id: str):
    from fai_report import get_fai, fai_to_dict
    try: return jd(fai_to_dict(get_fai(report_id)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/fai/list")
async def fai_list():
    from fai_report import list_fai, fai_to_dict
    return jd({"reports": [fai_to_dict(r) for r in list_fai()]})


# ── NCR / MRB Tracker ─────────────────────────────────────────────────────────
@app.post("/api/v1/ncr/create")
async def ncr_create(request: Request):
    b = await request.json()
    from ncr_tracker import create_ncr, ncr_to_dict
    return jd(ncr_to_dict(create_ncr(b.get("title",""), b.get("part_number",""),
        b.get("lot_number",""), int(b.get("qty_affected",1)), int(b.get("qty_nc",1)),
        b.get("detection_point","IQC"), b.get("priority","Major"),
        b.get("description",""))))

@app.post("/api/v1/ncr/{ncr_id}/update")
async def ncr_update(ncr_id: str, request: Request):
    b = await request.json()
    from ncr_tracker import update_ncr, ncr_to_dict
    try: return jd(ncr_to_dict(update_ncr(ncr_id, b)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/ncr/summary")
async def ncr_summary_ep():
    from ncr_tracker import ncr_summary
    return jd(ncr_summary())

@app.get("/api/v1/ncr/list")
async def ncr_list(status: str = None):
    from ncr_tracker import list_ncrs, ncr_to_dict
    return jd({"ncrs": [ncr_to_dict(r) for r in list_ncrs(status)]})


# ── FRACAS ────────────────────────────────────────────────────────────────────
@app.post("/api/v1/fracas/log-failure")
async def fracas_log(request: Request):
    b = await request.json()
    import dataclasses as dc
    from fracas import log_failure, failure_to_dict
    try:
        f = log_failure(b.get("product",""), b.get("failure_mode","Unknown"),
            float(b.get("age_hours",0)), b.get("serial_number",""),
            b.get("failure_description",""), b.get("category","Unknown"),
            b.get("component",""), b.get("customer_impact","Functional"),
            float(b.get("warranty_cost",0)))
        return jd(failure_to_dict(f))
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/v1/fracas/{product}/analyze")
async def fracas_analyze(product: str, units_fielded: int = 1000,
                          observation_hours: float = 8760, target_hours: float = 1000):
    import dataclasses as dc
    from fracas import analyze_fracas
    try: return jd(dc.asdict(analyze_fracas(product, units_fielded, observation_hours, target_hours)))
    except ValueError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/fracas/products")
async def fracas_products():
    from fracas import list_products
    return jd({"products": list_products()})


# ── PCN Tracker ───────────────────────────────────────────────────────────────
@app.post("/api/v1/pcn/create")
async def pcn_create(request: Request):
    b = await request.json()
    from pcn_tracker import create_pcn, pcn_to_dict
    return jd(pcn_to_dict(create_pcn(b.get("supplier",""), b.get("part_number",""),
        b.get("change_description",""), b.get("change_category","Process"),
        b.get("impact","Major"), b.get("effective_date",""))))

@app.post("/api/v1/pcn/{pcn_id}/update")
async def pcn_update(pcn_id: str, request: Request):
    b = await request.json()
    from pcn_tracker import update_pcn, pcn_to_dict
    try: return jd(pcn_to_dict(update_pcn(pcn_id, b)))
    except KeyError as e: raise HTTPException(404, str(e))

@app.get("/api/v1/pcn/summary")
async def pcn_summary_ep():
    from pcn_tracker import pcn_summary
    return jd(pcn_summary())

@app.get("/api/v1/pcn/list")
async def pcn_list():
    from pcn_tracker import list_pcns, pcn_to_dict
    return jd({"pcns": [pcn_to_dict(r) for r in list_pcns()]})


# ── Reliability Prediction (FIT / MTBF / Bathtub) ────────────────────────────
@app.post("/api/v1/reliability/predict")
async def rel_predict(request: Request):
    b = await request.json()
    import dataclasses as dc
    from reliability_pred import predict_reliability
    try:
        r = predict_reliability(
            system_name=b.get("system_name","System"),
            component_list=b.get("components",[]),
            environment=b.get("environment","Ground Fixed"),
            target_hours=float(b.get("target_hours",8760)),
        )
        return jd(dc.asdict(r))
    except Exception as e: raise HTTPException(400, str(e))

@app.get("/api/v1/reliability/categories")
async def rel_categories():
    from reliability_pred import list_categories, ENVIRONMENT_FACTORS
    return jd({"categories": list_categories(), "environments": list(ENVIRONMENT_FACTORS.keys())})

"""
StatMind — Additions patch
Paste this at the END of main.py (before the if __name__ == "__main__" block)
"""

# ══ NEW ENDPOINTS — Cpk CI, Hidden Engines, RSM, Run Chart, Two-Way ANOVA ════

# ── Cpk Confidence Intervals (chi-squared / Bissell 1990) ────────────────────
@app.post("/api/v1/capability/ci")
async def capability_ci(request: Request):
    body = await request.json()
    from scipy import stats as _stats
    import math
    n   = max(int(body.get("n", 30)), 3)
    cp  = float(body.get("cp",  1.0))
    cpk = float(body.get("cpk", 1.0))
    pp  = float(body.get("pp",  1.0))
    ppk = float(body.get("ppk", 1.0))
    alpha = 0.05
    chi2_lo = _stats.chi2.ppf(alpha/2,   n-1)
    chi2_hi = _stats.chi2.ppf(1-alpha/2, n-1)
    cp_ci_lo  = round(cp  * math.sqrt((n-1)/chi2_hi), 4)
    cp_ci_hi  = round(cp  * math.sqrt((n-1)/chi2_lo), 4)
    cpk_se    = math.sqrt(max(cpk**2/(9*n) + 1/(2*(n-1)), 1e-9))
    cpk_ci_lo = round(cpk - 1.96*cpk_se, 4)
    cpk_ci_hi = round(cpk + 1.96*cpk_se, 4)
    pp_ci_lo  = round(pp  * math.sqrt((n-1)/chi2_hi), 4)
    pp_ci_hi  = round(pp  * math.sqrt((n-1)/chi2_lo), 4)
    ppk_se    = math.sqrt(max(ppk**2/(9*n) + 1/(2*(n-1)), 1e-9))
    ppk_ci_lo = round(ppk - 1.96*ppk_se, 4)
    ppk_ci_hi = round(ppk + 1.96*ppk_se, 4)
    supplier_qualified = cpk_ci_lo >= 1.33
    meets_threshold    = cpk >= 1.33
    return jd({
        "n": n, "confidence": "95%",
        "cp":  {"estimate": cp,  "ci_lo": cp_ci_lo,  "ci_hi": cp_ci_hi},
        "cpk": {"estimate": cpk, "ci_lo": cpk_ci_lo, "ci_hi": cpk_ci_hi,
                "supplier_qualified": supplier_qualified},
        "pp":  {"estimate": pp,  "ci_lo": pp_ci_lo,  "ci_hi": pp_ci_hi},
        "ppk": {"estimate": ppk, "ci_lo": ppk_ci_lo, "ci_hi": ppk_ci_hi},
        "interpretation": (
            "✅ Lower Cpk CI ≥ 1.33 — SUPPLIER QUALIFIED (Apple/AIAG standard)" if supplier_qualified else
            f"⚠️ Cpk={cpk:.3f} ≥ 1.33 but lower 95% CI = {cpk_ci_lo:.3f} < 1.33 — more samples needed for qualification" if meets_threshold else
            f"❌ Cpk={cpk:.3f} < 1.33 — process not capable"
        )
    })

# ── CUSUM/EWMA (surface existing engine) ──────────────────────────────────────
@app.post("/api/v1/cusum/analyze")
async def cusum_analyze(
    file: UploadFile = File(...),
    column: str = Query(...),
    k: float = Query(0.5),
    h: float = Query(5.0),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    import dataclasses as dc
    try:
        from cusum_ewma import analyze_cusum_ewma
        data = result.df[column].dropna().values.astype(float)
        r = analyze_cusum_ewma(data, column, k=k, h=h)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/ewma/analyze")
async def ewma_analyze(
    file: UploadFile = File(...),
    column: str = Query(...),
    lam: float = Query(0.2),
    L: float = Query(3.0),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    import dataclasses as dc
    try:
        from cusum_ewma import analyze_cusum_ewma
        data = result.df[column].dropna().values.astype(float)
        r = analyze_cusum_ewma(data, column, k=0.5, h=5.0, lam=lam, L=L)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

# ── Correlation Matrix (surface existing engine) ──────────────────────────────
@app.post("/api/v1/correlation/matrix")
async def correlation_matrix(
    file: UploadFile = File(...),
    method: str = Query("pearson"),
    alpha: float = Query(0.05),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    import dataclasses as dc
    try:
        from correlation import correlation_matrix as _corr_matrix
        r = _corr_matrix(result.df[result.numeric_columns], alpha=alpha)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

# ── Equivalence Test / TOST (surface existing engine) ────────────────────────
@app.post("/api/v1/equivalence/analyze")
async def equivalence_analyze(
    file: UploadFile = File(...),
    col_a: str = Query(...),
    col_b: str = Query(...),
    delta: float = Query(0.05),
    alpha: float = Query(0.05),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    import dataclasses as dc
    try:
        from equivalence_test import tost_equivalence
        a = result.df[col_a].dropna().values.astype(float)
        b = result.df[col_b].dropna().values.astype(float)
        r = tost_equivalence(a, b, delta=delta, alpha=alpha,
                             name_a=col_a, name_b=col_b)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

# ── Outlier Detection (surface existing engine) ───────────────────────────────
@app.post("/api/v1/outliers/analyze")
async def outliers_analyze(
    file: UploadFile = File(...),
    column: str = Query(...),
    method: str = Query("all"),
    alpha: float = Query(0.05),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    import dataclasses as dc
    try:
        from outliers import detect_outliers
        data = result.df[column].dropna().values.astype(float)
        r = detect_outliers(data, column, method=method, alpha=alpha)
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

# ── Sample Size Calculator (surface existing engine) ──────────────────────────
@app.post("/api/v1/sample-size/calculate")
async def sample_size_calc(request: Request):
    body = await request.json()
    import dataclasses as dc
    try:
        from sample_size import calculate_sample_size
        r = calculate_sample_size(
            study_type = body.get("study_type", "capability"),
            **{k: v for k, v in body.items() if k != "study_type"}
        )
        return jd(dc.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))

# ── Two-Way ANOVA ─────────────────────────────────────────────────────────────
@app.post("/api/v1/hypothesis/two-way-anova")
async def two_way_anova(request: Request):
    body = await request.json()
    import pandas as pd
    import numpy as np
    from scipy import stats
    import itertools
    try:
        data   = body["data"]       # list of values
        factor_a = body["factor_a"] # list of level labels for factor A
        factor_b = body["factor_b"] # list of level labels for factor B
        name_a = body.get("name_a", "Factor A")
        name_b = body.get("name_b", "Factor B")
        response_name = body.get("response", "Response")
        alpha  = body.get("alpha", 0.05)

        df = pd.DataFrame({"response": data, "A": factor_a, "B": factor_b})
        levels_a = sorted(df["A"].unique())
        levels_b = sorted(df["B"].unique())

        # Grand mean
        grand_mean = df["response"].mean()
        n_total    = len(df)

        # Cell means
        cell_means = df.groupby(["A","B"])["response"].mean()
        means_a    = df.groupby("A")["response"].mean()
        means_b    = df.groupby("B")["response"].mean()
        n_a        = len(levels_a)
        n_b        = len(levels_b)
        n_rep      = n_total // (n_a * n_b)

        # SS calculations
        ss_a   = n_b * n_rep * sum((means_a[la] - grand_mean)**2 for la in levels_a)
        ss_b   = n_a * n_rep * sum((means_b[lb] - grand_mean)**2 for lb in levels_b)
        ss_ab  = n_rep * sum((cell_means.get((la,lb), grand_mean) - means_a[la] - means_b[lb] + grand_mean)**2
                             for la in levels_a for lb in levels_b)
        ss_err = sum((row["response"] - cell_means.get((row["A"],row["B"]), grand_mean))**2
                     for _, row in df.iterrows())
        ss_tot = sum((v - grand_mean)**2 for v in df["response"])

        df_a   = n_a - 1
        df_b   = n_b - 1
        df_ab  = df_a * df_b
        df_err = n_total - n_a * n_b
        df_tot = n_total - 1

        ms_a   = ss_a / df_a   if df_a   > 0 else 0
        ms_b   = ss_b / df_b   if df_b   > 0 else 0
        ms_ab  = ss_ab / df_ab  if df_ab  > 0 else 0
        ms_err = ss_err / df_err if df_err > 0 else 1e-9

        f_a  = ms_a  / ms_err
        f_b  = ms_b  / ms_err
        f_ab = ms_ab / ms_err

        p_a  = 1 - stats.f.cdf(f_a,  df_a,  df_err)
        p_b  = 1 - stats.f.cdf(f_b,  df_b,  df_err)
        p_ab = 1 - stats.f.cdf(f_ab, df_ab, df_err)

        return jd({
            "success": True,
            "response": response_name,
            "factor_a": name_a,
            "factor_b": name_b,
            "n_total": n_total,
            "grand_mean": round(grand_mean, 4),
            "anova_table": [
                {"source": name_a,          "ss": round(ss_a,4),  "df": df_a,  "ms": round(ms_a,4),  "f": round(f_a,4),  "p": round(p_a,5),  "significant": p_a<alpha},
                {"source": name_b,          "ss": round(ss_b,4),  "df": df_b,  "ms": round(ms_b,4),  "f": round(f_b,4),  "p": round(p_b,5),  "significant": p_b<alpha},
                {"source": f"{name_a}×{name_b}", "ss": round(ss_ab,4),"df": df_ab, "ms": round(ms_ab,4),"f": round(f_ab,4),"p": round(p_ab,5),"significant": p_ab<alpha},
                {"source": "Error",         "ss": round(ss_err,4),"df": df_err,"ms": round(ms_err,4),"f": None,          "p": None,           "significant": False},
                {"source": "Total",         "ss": round(ss_tot,4),"df": df_tot,"ms": None,            "f": None,          "p": None,           "significant": False},
            ],
            "cell_means": {f"{la}|{lb}": round(float(cell_means.get((la,lb),0)),4)
                           for la in levels_a for lb in levels_b},
            "levels_a": levels_a,
            "levels_b": levels_b,
            "interaction_significant": p_ab < alpha,
            "conclusion": (
                f"Significant interaction between {name_a} and {name_b} (p={p_ab:.4f}) — "
                "interpret main effects with caution." if p_ab < alpha else
                f"No significant interaction. {name_a}: {'significant' if p_a<alpha else 'not significant'} (p={p_a:.4f}). "
                f"{name_b}: {'significant' if p_b<alpha else 'not significant'} (p={p_b:.4f})."
            )
        })
    except Exception as e:
        raise HTTPException(400, str(e))

# ── Run Chart ─────────────────────────────────────────────────────────────────
@app.post("/api/v1/runchart/analyze")
async def runchart_analyze(
    file: UploadFile = File(...),
    column: str = Query(...),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    from scipy import stats
    import math
    data = result.df[column].dropna().values.astype(float)
    n = len(data)
    median = float(np.median(data))
    mean   = float(np.mean(data))

    # Runs test (Swed-Eisenhart): count runs above/below median
    above = [1 if x > median else 0 for x in data if x != median]
    n_above = sum(above)
    n_below = len(above) - n_above
    runs = 1 + sum(1 for i in range(1, len(above)) if above[i] != above[i-1])

    # Expected runs and variance
    n_tot = n_above + n_below
    if n_tot > 1:
        runs_expected = (2*n_above*n_below / n_tot) + 1
        runs_var = (2*n_above*n_below*(2*n_above*n_below - n_tot)) / (n_tot**2 * (n_tot-1)) if n_tot > 2 else 1
        z_runs = (runs - runs_expected) / max(math.sqrt(runs_var), 1e-9)
        p_runs = 2 * (1 - stats.norm.cdf(abs(z_runs)))
        runs_verdict = "Non-random pattern detected" if p_runs < 0.05 else "Random (no pattern detected)"
    else:
        runs_expected = runs_var = z_runs = 0
        p_runs = 1.0
        runs_verdict = "Insufficient data"

    # Cox-Stuart trend test
    m = n // 2
    pairs = [(data[i], data[i+m]) for i in range(m)]
    n_plus  = sum(1 for a,b in pairs if b > a)
    n_minus = sum(1 for a,b in pairs if b < a)
    n_ties  = m - n_plus - n_minus
    n_eff   = n_plus + n_minus
    p_trend = 2 * stats.binom.cdf(min(n_plus, n_minus), n_eff, 0.5) if n_eff > 0 else 1.0
    trend_verdict = "Significant trend detected" if p_trend < 0.05 else "No significant trend"

    return jd({
        "column": column, "n": n,
        "median": round(median, 4), "mean": round(mean, 4),
        "data": [round(float(x), 4) for x in data],
        "runs_test": {
            "runs": runs, "expected": round(runs_expected, 2),
            "z": round(z_runs, 3), "p": round(p_runs, 4),
            "verdict": runs_verdict
        },
        "trend_test": {
            "n_plus": n_plus, "n_minus": n_minus,
            "p": round(p_trend, 4), "verdict": trend_verdict
        },
        "overall_verdict": (
            "Non-random" if p_runs < 0.05 or p_trend < 0.05 else "Random — process appears stable"
        )
    })

# ── RSM — Response Surface Methodology ───────────────────────────────────────
@app.post("/api/v1/rsm/design")
async def rsm_design(request: Request):
    """Generate Central Composite Design (CCD) or Box-Behnken matrix."""
    body = await request.json()
    import itertools, math
    factor_names  = body.get("factor_names", ["X1","X2"])
    factor_levels = body.get("factor_levels", {})  # {name: [lo, hi]}
    design_type   = body.get("design_type", "ccd")  # ccd | bbd
    center_points = body.get("center_points", 3)
    alpha_val     = body.get("alpha", 1.414)  # axial distance (sqrt(2) for CCD)
    k = len(factor_names)

    runs = []
    if design_type == "ccd":
        # Factorial portion: all ±1 combinations
        factorial = list(itertools.product([-1,1], repeat=k))
        for combo in factorial:
            run = {"run_type": "factorial"}
            for i,name in enumerate(factor_names): run[name] = combo[i]
            runs.append(run)
        # Axial points: each factor at ±alpha, others at 0
        for i,name in enumerate(factor_names):
            for sign in [-1,1]:
                run = {"run_type": "axial"}
                for j,n2 in enumerate(factor_names): run[n2] = round(sign * alpha_val, 4) if j==i else 0.0
                runs.append(run)
        # Center points
        for _ in range(center_points):
            run = {"run_type": "center"}
            for name in factor_names: run[name] = 0.0
            runs.append(run)
    elif design_type == "bbd" and k == 3:
        # Box-Behnken for 3 factors
        bbd_combos = [(1,1,0),(-1,1,0),(1,-1,0),(-1,-1,0),
                      (1,0,1),(-1,0,1),(1,0,-1),(-1,0,-1),
                      (0,1,1),(0,-1,1),(0,1,-1),(0,-1,-1)]
        for combo in bbd_combos:
            run = {"run_type": "bbd"}
            for i,name in enumerate(factor_names): run[name] = float(combo[i])
            runs.append(run)
        for _ in range(center_points):
            run = {"run_type": "center"}
            for name in factor_names: run[name] = 0.0
            runs.append(run)

    # Add run number and decode coded to actual values
    coded_to_actual = {}
    for name in factor_names:
        lo = float(factor_levels.get(name, [-1,1])[0])
        hi = float(factor_levels.get(name, [-1,1])[1])
        coded_to_actual[name] = {"lo": lo, "hi": hi, "center": (lo+hi)/2, "half_range": (hi-lo)/2}

    for i, run in enumerate(runs):
        run["run"] = i+1
        run["response"] = None
        for name in factor_names:
            c2a = coded_to_actual[name]
            coded = run[name]
            run[f"{name}_actual"] = round(c2a["center"] + coded * c2a["half_range"], 4)

    return jd({
        "design_type": design_type.upper(),
        "k": k,
        "n_runs": len(runs),
        "center_points": center_points,
        "alpha": alpha_val,
        "factor_names": factor_names,
        "factor_levels": factor_levels,
        "run_matrix": runs,
        "model_terms": (
            ["intercept"] + factor_names +
            [f"{a}²" for a in factor_names] +
            [f"{a}×{b}" for i,a in enumerate(factor_names) for b in factor_names[i+1:]]
        )
    })

@app.post("/api/v1/rsm/analyze")
async def rsm_analyze(request: Request):
    """Fit RSM quadratic model and find optimum."""
    body = await request.json()
    import numpy as np
    from scipy import stats, optimize
    try:
        factor_names = body["factor_names"]
        run_matrix   = body["run_matrix"]
        responses    = body["responses"]
        goal         = body.get("goal", "maximize")  # maximize | minimize | target
        target_val   = body.get("target_value", None)
        k = len(factor_names)

        X_coded = np.array([[row.get(n, 0) for n in factor_names] for row in run_matrix], dtype=float)
        y = np.array(responses, dtype=float)

        # Build model matrix: [1, x1, x2, ..., x1², x2², ..., x1x2, ...]
        n_runs = len(y)
        cols = [np.ones(n_runs)]
        for i in range(k): cols.append(X_coded[:,i])
        for i in range(k): cols.append(X_coded[:,i]**2)
        for i in range(k):
            for j in range(i+1,k): cols.append(X_coded[:,i]*X_coded[:,j])
        X_model = np.column_stack(cols)

        # OLS fit
        try:
            beta, residuals, rank, sv = np.linalg.lstsq(X_model, y, rcond=None)
        except Exception:
            raise ValueError("Matrix is singular — ensure all responses are entered")

        y_pred = X_model @ beta
        ss_res = np.sum((y - y_pred)**2)
        ss_tot = np.sum((y - y.mean())**2)
        r2     = 1 - ss_res/ss_tot if ss_tot > 0 else 0
        n_params = X_model.shape[1]
        r2_adj = 1 - (1-r2)*(n_runs-1)/(max(n_runs-n_params,1))
        rmse   = np.sqrt(ss_res/max(n_runs-n_params,1))

        # Find optimum via optimization in coded space [-alpha, alpha]
        alpha_limit = max(body.get("alpha", 1.414), 1.0)
        def objective(x_coded):
            xv = np.concatenate([[1], x_coded,
                                  x_coded**2,
                                  [x_coded[i]*x_coded[j] for i in range(k) for j in range(i+1,k)]])
            pred = float(xv @ beta)
            if goal == "minimize": return pred
            if goal == "maximize": return -pred
            return (pred - target_val)**2

        from scipy.optimize import minimize
        best_obj = np.inf
        best_result = None
        for _ in range(20):
            x0 = np.random.uniform(-1, 1, k)
            res = minimize(objective, x0, method='L-BFGS-B',
                           bounds=[(-alpha_limit, alpha_limit)]*k)
            if res.fun < best_obj:
                best_obj = res.fun
                best_result = res

        optimal_coded  = best_result.x.tolist() if best_result else [0]*k
        optimal_actual = {}
        factor_levels  = body.get("factor_levels", {})
        for i, name in enumerate(factor_names):
            lo = float(factor_levels.get(name, [-1,1])[0])
            hi = float(factor_levels.get(name, [-1,1])[1])
            center = (lo+hi)/2; half_range = (hi-lo)/2
            optimal_actual[name] = round(center + optimal_coded[i]*half_range, 4)

        optimal_response_coded = [1.0] + optimal_coded + [c**2 for c in optimal_coded]
        for i in range(k):
            for j in range(i+1,k): optimal_response_coded.append(optimal_coded[i]*optimal_coded[j])
        optimal_response = float(np.array(optimal_response_coded) @ beta)

        # Contour data for first 2 factors (grid scan)
        contour_data = None
        if k >= 2:
            grid_n = 20
            x1_grid = np.linspace(-1,1,grid_n)
            x2_grid = np.linspace(-1,1,grid_n)
            Z = np.zeros((grid_n,grid_n))
            for i,x1 in enumerate(x1_grid):
                for j,x2 in enumerate(x2_grid):
                    xv_row = np.concatenate([[1],[x1,x2]+[0]*(k-2),
                                             [x1**2,x2**2]+[0]*(k-2),
                                             [x1*x2]+[0]*(k*(k-1)//2-1)])[:n_params]
                    xv_row_full = np.ones(n_params)
                    xv_row_full[0]=1; xv_row_full[1]=x1; xv_row_full[2]=x2
                    if k>=2 and n_params>2+k: xv_row_full[1+k]=x1**2; xv_row_full[2+k]=x2**2
                    Z[i,j] = float(xv_row_full @ beta)
            contour_data = {
                "x1": [round(float(x),4) for x in x1_grid],
                "x2": [round(float(x),4) for x in x2_grid],
                "z":  [[round(float(v),4) for v in row] for row in Z],
                "factor1": factor_names[0],
                "factor2": factor_names[1] if k>1 else factor_names[0],
            }

        term_names = (["Intercept"] + factor_names +
                      [f"{n}²" for n in factor_names] +
                      [f"{factor_names[i]}×{factor_names[j]}" for i in range(k) for j in range(i+1,k)])

        return jd({
            "success": True,
            "model": {
                "r_squared": round(r2,4), "r_squared_adj": round(r2_adj,4),
                "rmse": round(rmse,4), "n_runs": n_runs, "n_params": n_params,
                "terms": [{"name": nm, "coeff": round(float(b),4)}
                          for nm,b in zip(term_names, beta)],
            },
            "goal": goal,
            "optimal_coded": [round(float(c),4) for c in optimal_coded],
            "optimal_settings": optimal_actual,
            "predicted_optimum": round(optimal_response, 4),
            "y_actual": [round(float(v),4) for v in y],
            "y_predicted": [round(float(v),4) for v in y_pred],
            "contour_data": contour_data,
        })
    except Exception as e:
        raise HTTPException(400, str(e))

# ── Probability Plot data (for normality visualization) ───────────────────────
@app.post("/api/v1/normality/probplot")
async def normality_probplot(
    file: UploadFile = File(...),
    column: str = Query(...),
    distribution: str = Query("norm"),
):
    c = await file.read()
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    from scipy import stats
    data = result.df[column].dropna().values.astype(float)
    n = len(data)
    sorted_data = np.sort(data)
    # Blom plotting positions
    probs = (np.arange(1,n+1) - 0.375) / (n + 0.25)
    if distribution == "norm":
        theoretical = stats.norm.ppf(probs)
        dist_name = "Normal"
    elif distribution == "lognorm":
        theoretical = stats.norm.ppf(probs)
        sorted_data = np.log(sorted_data[sorted_data>0])
        dist_name = "Lognormal"
    else:
        theoretical = stats.norm.ppf(probs)
        dist_name = "Normal"

    # Fit line
    slope, intercept, r, p, se = stats.linregress(theoretical, sorted_data)

    return jd({
        "column": column, "n": n,
        "distribution": dist_name,
        "theoretical_quantiles": [round(float(x),4) for x in theoretical],
        "sample_quantiles": [round(float(x),4) for x in sorted_data],
        "fit_line": {
            "slope": round(float(slope),4),
            "intercept": round(float(intercept),4),
            "r_squared": round(float(r**2),4),
        },
        "percentiles": [round(float(p*100),1) for p in probs],
    })
import dataclasses
import itertools
import math
from typing import Optional

# ── Structured JSON error handling ───────────────────────────────────────────
# Add this near the top of main.py (after app = FastAPI()):
#
# from fastapi import Request
# from fastapi.responses import JSONResponse
#
# @app.exception_handler(Exception)
# async def global_exception_handler(request: Request, exc: Exception):
#     import logging
#     logging.error(f"Unhandled exception: {exc}", exc_info=True)
#     return JSONResponse(
#         status_code=500,
#         content={"detail": str(exc), "type": type(exc).__name__},
#     )


# ══ PASTE FROM HERE INTO BOTTOM OF main.py ═══════════════════════════════════

# ── Cpk Confidence Intervals (chi-squared/Bissell 1990) ─────────────────────
@app.post("/api/v1/capability/ci")
async def capability_ci(request: Request):
    """
    Compute 95% confidence intervals for Cp, Cpk, Pp, Ppk.

    Uses chi-squared method for Cp/Pp and Bissell (1990) approximation
    for Cpk/Ppk.  The lower Cpk CI is the key number for supplier
    qualification — Apple/AIAG require lower CI ≥ 1.33.
    """
    body = await request.json()
    from scipy import stats as _stats

    n   = max(int(body.get("n",   30)), 3)
    cp  = float(body.get("cp",  1.0))
    cpk = float(body.get("cpk", 1.0))
    pp  = float(body.get("pp",  1.0))
    ppk = float(body.get("ppk", 1.0))
    alpha = 0.05

    chi2_lo = _stats.chi2.ppf(alpha / 2,       n - 1)
    chi2_hi = _stats.chi2.ppf(1 - alpha / 2,   n - 1)

    # Cp / Pp: chi-squared CI
    cp_ci_lo  = round(cp  * math.sqrt((n - 1) / chi2_hi), 4)
    cp_ci_hi  = round(cp  * math.sqrt((n - 1) / chi2_lo), 4)
    pp_ci_lo  = round(pp  * math.sqrt((n - 1) / chi2_hi), 4)
    pp_ci_hi  = round(pp  * math.sqrt((n - 1) / chi2_lo), 4)

    # Cpk / Ppk: Bissell (1990) approximation
    cpk_se    = math.sqrt(max(cpk ** 2 / (9 * n) + 1 / (2 * (n - 1)), 1e-9))
    cpk_ci_lo = round(cpk - 1.96 * cpk_se, 4)
    cpk_ci_hi = round(cpk + 1.96 * cpk_se, 4)
    ppk_se    = math.sqrt(max(ppk ** 2 / (9 * n) + 1 / (2 * (n - 1)), 1e-9))
    ppk_ci_lo = round(ppk - 1.96 * ppk_se, 4)
    ppk_ci_hi = round(ppk + 1.96 * ppk_se, 4)

    supplier_qualified = cpk_ci_lo >= 1.33
    meets_threshold    = cpk >= 1.33

    if supplier_qualified:
        interpretation = (
            "✅ Lower Cpk CI ≥ 1.33 — SUPPLIER QUALIFIED (Apple/AIAG standard)"
        )
    elif meets_threshold:
        interpretation = (
            f"⚠️ Cpk={cpk:.3f} ≥ 1.33 but lower 95% CI = {cpk_ci_lo:.3f} < 1.33 "
            "— insufficient statistical evidence of capability. Increase sample size."
        )
    else:
        interpretation = (
            f"❌ Cpk={cpk:.3f} < 1.33 — process is not capable at the 1.33 threshold."
        )

    return jd({
        "n":             n,
        "confidence":    "95%",
        "cp":  {"estimate": cp,  "ci_lo": cp_ci_lo,  "ci_hi": cp_ci_hi},
        "cpk": {
            "estimate":          cpk,
            "ci_lo":             cpk_ci_lo,
            "ci_hi":             cpk_ci_hi,
            "supplier_qualified": supplier_qualified,
        },
        "pp":  {"estimate": pp,  "ci_lo": pp_ci_lo,  "ci_hi": pp_ci_hi},
        "ppk": {"estimate": ppk, "ci_lo": ppk_ci_lo, "ci_hi": ppk_ci_hi},
        "interpretation": interpretation,
    })


# ── Outlier Detection ─────────────────────────────────────────────────────────
@app.post("/api/v1/outliers/analyze")
async def outliers_analyze(
    file:   UploadFile = File(...),
    column: str        = Query(...),
    method: str        = Query("all"),
    alpha:  float      = Query(0.05),
):
    content = await file.read()
    try:
        result = parse_any_file(content, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found. "
                                 f"Available: {result.numeric_columns}")
    try:
        from outliers import detect_outliers
        data = result.df[column].dropna().values.astype(float)
        r    = detect_outliers(data, column, method=method, alpha=alpha)
        return jd(dataclasses.asdict(r))
    except ImportError:
        raise HTTPException(500, "outliers.py not found on server")
    except Exception as e:
        raise HTTPException(400, str(e))


# ── TOST Equivalence Test ─────────────────────────────────────────────────────
@app.post("/api/v1/equivalence/analyze")
async def equivalence_analyze(
    file:  UploadFile = File(...),
    col_a: str        = Query(...),
    col_b: str        = Query(...),
    delta: float      = Query(None),
    alpha: float      = Query(0.05),
):
    content = await file.read()
    try:
        result = parse_any_file(content, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    for col in (col_a, col_b):
        if col not in result.df.columns:
            raise HTTPException(404, f"Column '{col}' not found.")
    try:
        from equivalence_test import tost_equivalence
        a = result.df[col_a].dropna().values.astype(float)
        b = result.df[col_b].dropna().values.astype(float)
        r = tost_equivalence(a, b, delta=delta, alpha=alpha,
                             name_a=col_a, name_b=col_b)
        return jd(dataclasses.asdict(r))
    except ImportError:
        raise HTTPException(500, "equivalence_test.py not found on server")
    except Exception as e:
        raise HTTPException(400, str(e))


# ── Run Chart ─────────────────────────────────────────────────────────────────
@app.post("/api/v1/runchart/analyze")
async def runchart_analyze(
    file:   UploadFile = File(...),
    column: str        = Query(...),
):
    content = await file.read()
    try:
        result = parse_any_file(content, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found.")
    from scipy import stats as _stats

    data   = result.df[column].dropna().values.astype(float)
    n      = len(data)
    median = float(np.median(data))
    mean   = float(data.mean())

    # Swed-Eisenhart runs test (above/below median)
    above    = [1 if x > median else 0 for x in data if x != median]
    n_above  = sum(above)
    n_below  = len(above) - n_above
    n_tot    = n_above + n_below
    runs     = 1 + sum(1 for i in range(1, len(above)) if above[i] != above[i - 1]) if above else 0

    if n_tot > 1:
        runs_exp = 2 * n_above * n_below / n_tot + 1
        runs_var = (2 * n_above * n_below * (2 * n_above * n_below - n_tot)
                    / (n_tot ** 2 * (n_tot - 1))) if n_tot > 2 else 1.0
        z_runs   = (runs - runs_exp) / max(math.sqrt(runs_var), 1e-9)
        p_runs   = float(2 * (1 - _stats.norm.cdf(abs(z_runs))))
    else:
        runs_exp = runs_var = z_runs = 0.0
        p_runs   = 1.0

    runs_verdict = "Non-random pattern detected" if p_runs < 0.05 else "Random — no pattern detected"

    # Cox-Stuart trend test
    m       = n // 2
    pairs   = [(data[i], data[i + m]) for i in range(m)]
    n_plus  = sum(1 for a, b in pairs if b > a)
    n_minus = sum(1 for a, b in pairs if b < a)
    n_eff   = n_plus + n_minus
    p_trend = float(2 * _stats.binom.cdf(min(n_plus, n_minus), n_eff, 0.5)) if n_eff > 0 else 1.0
    trend_verdict = "Significant trend detected" if p_trend < 0.05 else "No significant trend"

    return jd({
        "column": column, "n": n, "median": round(median, 4), "mean": round(mean, 4),
        "data":   [round(float(x), 4) for x in data],
        "runs_test": {
            "runs": runs, "expected": round(runs_exp, 2),
            "z": round(z_runs, 3), "p": round(p_runs, 4), "verdict": runs_verdict,
        },
        "trend_test": {
            "n_plus": n_plus, "n_minus": n_minus,
            "p": round(p_trend, 4), "verdict": trend_verdict,
        },
        "overall_verdict": (
            "Non-random" if p_runs < 0.05 or p_trend < 0.05
            else "Random — process appears stable"
        ),
    })


# ── CUSUM / EWMA ──────────────────────────────────────────────────────────────
@app.post("/api/v1/cusum/analyze")
async def cusum_analyze(
    file:   UploadFile = File(...),
    column: str        = Query(...),
    k:      float      = Query(0.5),
    h:      float      = Query(5.0),
    lam:    float      = Query(0.2),
    L:      float      = Query(3.0),
):
    content = await file.read()
    try:
        result = parse_any_file(content, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found.")

    data   = result.df[column].dropna().values.astype(float)
    n      = len(data)
    mean   = float(data.mean())
    std    = float(data.std(ddof=1)) if n > 1 else 1.0

    # CUSUM
    cusum_pos = [0.0]
    cusum_neg = [0.0]
    for x in data:
        z = (x - mean) / std
        cusum_pos.append(max(0.0, cusum_pos[-1] + z - k))
        cusum_neg.append(min(0.0, cusum_neg[-1] + z + k))
    cusum_pos = cusum_pos[1:]
    cusum_neg = cusum_neg[1:]
    cusum_signals = [i for i, (p, q) in enumerate(zip(cusum_pos, cusum_neg))
                     if p > h or abs(q) > h]

    # EWMA
    cl  = mean
    ucl = mean + L * std * math.sqrt(lam / (2 - lam))
    lcl = mean - L * std * math.sqrt(lam / (2 - lam))
    ewma_vals = [mean]
    for x in data:
        ewma_vals.append(lam * x + (1 - lam) * ewma_vals[-1])
    ewma_vals = ewma_vals[1:]
    ewma_signals = [i for i, e in enumerate(ewma_vals) if e > ucl or e < lcl]

    return jd({
        "column": column, "n": n, "mean": round(mean, 4), "std": round(std, 4),
        "cusum": {
            "k": k, "h": h,
            "cusum_pos": [round(float(v), 4) for v in cusum_pos],
            "cusum_neg": [round(float(v), 4) for v in cusum_neg],
            "signals":   cusum_signals,
        },
        "ewma": {
            "lambda": lam, "L": L,
            "center_line": round(cl, 4),
            "ucl": round(ucl, 4), "lcl": round(lcl, 4),
            "ewma_values": [round(float(v), 4) for v in ewma_vals],
            "signals":     ewma_signals,
        },
    })


# ── Correlation Matrix ────────────────────────────────────────────────────────
@app.post("/api/v1/correlation/matrix")
async def correlation_matrix(
    file:   UploadFile = File(...),
    method: str        = Query("pearson"),
    alpha:  float      = Query(0.05),
):
    content = await file.read()
    try:
        result = parse_any_file(content, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    from scipy import stats as _stats

    cols = result.numeric_columns
    df   = result.df[cols].dropna()
    n    = len(df)

    corr_matrix: dict = {}
    pval_matrix: dict = {}
    for c1 in cols:
        corr_matrix[c1] = {}
        pval_matrix[c1] = {}
        for c2 in cols:
            if c1 == c2:
                corr_matrix[c1][c2] = 1.0
                pval_matrix[c1][c2] = 0.0
            else:
                if method == "spearman":
                    r, p = _stats.spearmanr(df[c1], df[c2])
                else:
                    r, p = _stats.pearsonr(df[c1], df[c2])
                corr_matrix[c1][c2] = round(float(r), 4)
                pval_matrix[c1][c2] = round(float(p), 5)

    return jd({
        "columns":           cols,
        "method":            method.capitalize(),
        "n":                 n,
        "correlation_matrix": corr_matrix,
        "p_values":          pval_matrix,
    })


# ── Sample Size Calculator ────────────────────────────────────────────────────
@app.post("/api/v1/sample-size/calculate")
async def sample_size_calculate(request: Request):
    body = await request.json()
    from scipy import stats as _stats

    study_type  = body.get("study_type",    "capability")
    cpk_base    = float(body.get("cpk_baseline", 1.33))
    cpk_shift   = float(body.get("cpk_shift",    0.20))
    power_val   = float(body.get("power",        0.90))
    alpha_val   = float(body.get("alpha",        0.05))

    # Cpk detection: Bissell variance of Cpk → approximate sample size
    z_a = float(_stats.norm.ppf(1 - alpha_val / 2))
    z_b = float(_stats.norm.ppf(power_val))
    n_approx = math.ceil(
        (z_a + z_b) ** 2 * (1 + 9 * cpk_base ** 2) / (9 * cpk_shift ** 2)
    )
    n_approx = max(n_approx, 5)

    # Power curve
    ns     = list(range(5, min(n_approx * 3, 501), 5))
    powers = []
    for ni in ns:
        se  = math.sqrt(max(cpk_base ** 2 / (9 * ni) + 1 / (2 * (ni - 1)), 1e-9))
        z_e = abs(cpk_shift) / se
        pow_val = float(_stats.norm.cdf(z_e - z_a) + _stats.norm.cdf(-z_e - z_a))
        powers.append(round(min(max(pow_val, 0.0), 1.0), 4))

    return jd({
        "study_type":      study_type,
        "required_n":      n_approx,
        "cpk_baseline":    cpk_base,
        "cpk_shift":       cpk_shift,
        "power":           power_val,
        "alpha":           alpha_val,
        "power_curve":     {"n": ns, "power": powers},
        "interpretation": (
            f"Need n={n_approx} measurements to detect a Cpk shift from "
            f"{cpk_base} to {cpk_base - cpk_shift:.2f} with "
            f"{round(power_val * 100)}% power at α={alpha_val}."
        ),
    })


# ── Two-Way ANOVA ─────────────────────────────────────────────────────────────
@app.post("/api/v1/hypothesis/two-way-anova")
async def two_way_anova(request: Request):
    body = await request.json()
    import pandas as _pd
    from scipy import stats as _stats

    try:
        response_vals = [float(v) for v in body["data"]]
        factor_a      = [str(v) for v in body["factor_a"]]
        factor_b      = [str(v) for v in body["factor_b"]]
        name_a        = str(body.get("name_a",    "Factor A"))
        name_b        = str(body.get("name_b",    "Factor B"))
        resp_name     = str(body.get("response",  "Response"))
        alpha_val     = float(body.get("alpha",   0.05))
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(422, f"Invalid request body: {e}")

    df       = _pd.DataFrame({"y": response_vals, "A": factor_a, "B": factor_b})
    levels_a = sorted(df["A"].unique())
    levels_b = sorted(df["B"].unique())
    n_a, n_b = len(levels_a), len(levels_b)
    N        = len(df)
    grand    = float(df["y"].mean())

    means_a    = df.groupby("A")["y"].mean()
    means_b    = df.groupby("B")["y"].mean()
    cell_means = df.groupby(["A", "B"])["y"].mean()
    n_rep      = N // max(n_a * n_b, 1)

    ss_a   = n_b * n_rep * sum((means_a[la] - grand) ** 2 for la in levels_a)
    ss_b   = n_a * n_rep * sum((means_b[lb] - grand) ** 2 for lb in levels_b)
    ss_ab  = n_rep * sum(
        (cell_means.get((la, lb), grand) - means_a[la] - means_b[lb] + grand) ** 2
        for la in levels_a for lb in levels_b
    )
    ss_err = sum(
        (row["y"] - cell_means.get((row["A"], row["B"]), grand)) ** 2
        for _, row in df.iterrows()
    )
    ss_tot = sum((v - grand) ** 2 for v in df["y"])

    df_a, df_b, df_ab = n_a - 1, n_b - 1, (n_a - 1) * (n_b - 1)
    df_err = N - n_a * n_b

    ms_a   = ss_a   / df_a   if df_a   > 0 else 0.0
    ms_b   = ss_b   / df_b   if df_b   > 0 else 0.0
    ms_ab  = ss_ab  / df_ab  if df_ab  > 0 else 0.0
    ms_err = ss_err / max(df_err, 1)

    f_a  = ms_a  / ms_err
    f_b  = ms_b  / ms_err
    f_ab = ms_ab / ms_err

    p_a  = float(1 - _stats.f.cdf(f_a,  df_a,  df_err))
    p_b  = float(1 - _stats.f.cdf(f_b,  df_b,  df_err))
    p_ab = float(1 - _stats.f.cdf(f_ab, df_ab, df_err))

    def fmt(v): return round(float(v), 4)

    return jd({
        "success":     True,
        "response":    resp_name,
        "factor_a":    name_a,
        "factor_b":    name_b,
        "n_total":     N,
        "grand_mean":  fmt(grand),
        "anova_table": [
            {"source": name_a,              "ss": fmt(ss_a),  "df": df_a,  "ms": fmt(ms_a),  "f": fmt(f_a),  "p": fmt(p_a),  "significant": p_a  < alpha_val},
            {"source": name_b,              "ss": fmt(ss_b),  "df": df_b,  "ms": fmt(ms_b),  "f": fmt(f_b),  "p": fmt(p_b),  "significant": p_b  < alpha_val},
            {"source": f"{name_a}×{name_b}","ss": fmt(ss_ab), "df": df_ab, "ms": fmt(ms_ab), "f": fmt(f_ab), "p": fmt(p_ab), "significant": p_ab < alpha_val},
            {"source": "Error",             "ss": fmt(ss_err),"df": df_err,"ms": fmt(ms_err),"f": None,       "p": None,      "significant": False},
            {"source": "Total",             "ss": fmt(ss_tot),"df": N - 1, "ms": None,        "f": None,       "p": None,      "significant": False},
        ],
        "interaction_significant": p_ab < alpha_val,
        "conclusion": (
            f"Significant interaction between {name_a} and {name_b} "
            f"(p={p_ab:.4f}) — interpret main effects with caution."
            if p_ab < alpha_val else
            f"No significant interaction. "
            f"{name_a}: {'significant' if p_a < alpha_val else 'not significant'} "
            f"(p={p_a:.4f}). "
            f"{name_b}: {'significant' if p_b < alpha_val else 'not significant'} "
            f"(p={p_b:.4f})."
        ),
    })


# ── RSM — Response Surface Methodology ───────────────────────────────────────
@app.post("/api/v1/rsm/design")
async def rsm_design(request: Request):
    """Generate a Central Composite Design (CCD) or Box-Behnken matrix."""
    body         = await request.json()
    factor_names = body.get("factor_names",  ["X1", "X2"])
    factor_levels= body.get("factor_levels", {})
    design_type  = body.get("design_type",   "ccd")
    center_pts   = int(body.get("center_points", 3))
    alpha_axial  = float(body.get("alpha", 1.414))
    k            = len(factor_names)

    runs: list = []
    if design_type == "ccd":
        for combo in itertools.product([-1, 1], repeat=k):
            run = {"run_type": "factorial"}
            for i, nm in enumerate(factor_names): run[nm] = float(combo[i])
            runs.append(run)
        for i, nm in enumerate(factor_names):
            for sign in (-1, 1):
                run = {"run_type": "axial"}
                for j, nm2 in enumerate(factor_names):
                    run[nm2] = round(sign * alpha_axial, 4) if j == i else 0.0
                runs.append(run)
    elif design_type == "bbd" and k == 3:
        bbd = [(1,1,0),(-1,1,0),(1,-1,0),(-1,-1,0),(1,0,1),(-1,0,1),
               (1,0,-1),(-1,0,-1),(0,1,1),(0,-1,1),(0,1,-1),(0,-1,-1)]
        for combo in bbd:
            run = {"run_type": "bbd"}
            for i, nm in enumerate(factor_names): run[nm] = float(combo[i])
            runs.append(run)
    else:
        raise HTTPException(422, f"Unsupported design type '{design_type}' for k={k}")

    for _ in range(center_pts):
        run = {"run_type": "center"}
        for nm in factor_names: run[nm] = 0.0
        runs.append(run)

    # Decode coded to actual
    c2a = {}
    for nm in factor_names:
        levels = factor_levels.get(nm, [-1.0, 1.0])
        lo, hi = float(levels[0]), float(levels[1])
        c2a[nm] = {"center": (lo + hi) / 2, "half_range": (hi - lo) / 2}

    for i, run in enumerate(runs):
        run["run"] = i + 1
        run["response"] = None
        for nm in factor_names:
            run[f"{nm}_actual"] = round(
                c2a[nm]["center"] + run[nm] * c2a[nm]["half_range"], 4
            )

    terms = (["intercept"] + factor_names +
             [f"{nm}²" for nm in factor_names] +
             [f"{factor_names[i]}×{factor_names[j]}"
              for i in range(k) for j in range(i + 1, k)])

    return jd({
        "design_type":   design_type.upper(),
        "k":             k,
        "n_runs":        len(runs),
        "center_points": center_pts,
        "alpha":         alpha_axial,
        "factor_names":  factor_names,
        "factor_levels": factor_levels,
        "run_matrix":    runs,
        "model_terms":   terms,
    })


@app.post("/api/v1/rsm/analyze")
async def rsm_analyze(request: Request):
    """Fit a quadratic RSM model and find the optimal settings."""
    body = await request.json()
    from scipy.optimize import minimize

    try:
        factor_names = body["factor_names"]
        run_matrix   = body["run_matrix"]
        responses    = [float(v) for v in body["responses"]]
        goal         = body.get("goal", "maximize")
        target_val   = body.get("target_value")
        factor_levels= body.get("factor_levels", {})
        alpha_axial  = float(body.get("alpha", 1.414))
    except (KeyError, TypeError) as e:
        raise HTTPException(422, f"Invalid request body: {e}")

    k     = len(factor_names)
    n_run = len(responses)

    # Build model matrix [1, x1,..,xk, x1²,..,xk², x1x2,..]
    X_coded = np.array([[row.get(nm, 0) for nm in factor_names]
                         for row in run_matrix], dtype=float)
    y = np.array(responses, dtype=float)

    cols = ([np.ones(n_run)] +
            [X_coded[:, i] for i in range(k)] +
            [X_coded[:, i] ** 2 for i in range(k)] +
            [X_coded[:, i] * X_coded[:, j]
             for i in range(k) for j in range(i + 1, k)])
    X_model = np.column_stack(cols)

    beta, *_ = np.linalg.lstsq(X_model, y, rcond=None)
    y_pred   = X_model @ beta
    ss_res   = float(np.sum((y - y_pred) ** 2))
    ss_tot   = float(np.sum((y - y.mean()) ** 2))
    r2       = 1 - ss_res / max(ss_tot, 1e-9)
    n_params = X_model.shape[1]
    r2_adj   = 1 - (1 - r2) * (n_run - 1) / max(n_run - n_params, 1)
    rmse     = math.sqrt(ss_res / max(n_run - n_params, 1))

    def _predict(x_coded: np.ndarray) -> float:
        row = np.concatenate([[1.0], x_coded,
                              x_coded ** 2,
                              [x_coded[i] * x_coded[j]
                               for i in range(k) for j in range(i + 1, k)]])
        return float(row @ beta)

    def objective(x):
        v = _predict(x)
        if goal == "minimize":    return  v
        if goal == "maximize":    return -v
        return (v - float(target_val)) ** 2

    best_result = None
    best_obj    = float("inf")
    bounds      = [(-alpha_axial, alpha_axial)] * k
    rng         = np.random.default_rng(42)
    for _ in range(30):
        x0  = rng.uniform(-1, 1, k)
        res = minimize(objective, x0, method="L-BFGS-B", bounds=bounds)
        if res.fun < best_obj:
            best_obj    = res.fun
            best_result = res

    optimal_coded = best_result.x.tolist() if best_result else [0.0] * k
    optimal_actual: dict = {}
    for i, nm in enumerate(factor_names):
        levels = factor_levels.get(nm, [-1.0, 1.0])
        lo, hi = float(levels[0]), float(levels[1])
        optimal_actual[nm] = round((lo + hi) / 2 + optimal_coded[i] * (hi - lo) / 2, 4)
    optimal_response = round(_predict(np.array(optimal_coded)), 4)

    term_names = (["Intercept"] + factor_names +
                  [f"{nm}²" for nm in factor_names] +
                  [f"{factor_names[i]}×{factor_names[j]}"
                   for i in range(k) for j in range(i + 1, k)])

    return jd({
        "success": True,
        "model": {
            "r_squared":     round(r2,    4),
            "r_squared_adj": round(r2_adj,4),
            "rmse":          round(rmse,  4),
            "n_runs":        n_run,
            "n_params":      n_params,
            "terms": [{"name": nm, "coeff": round(float(b), 4)}
                      for nm, b in zip(term_names, beta)],
        },
        "goal":             goal,
        "optimal_coded":    [round(float(c), 4) for c in optimal_coded],
        "optimal_settings": optimal_actual,
        "predicted_optimum": optimal_response,
        "y_actual":         [round(float(v), 4) for v in y],
        "y_predicted":      [round(float(v), 4) for v in y_pred],
    })
