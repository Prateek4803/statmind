"""
StatMind — API v5: Sessions 1-5 with Rule-Based CAPA Engine
Run: uvicorn api5:app --port 8010
"""
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import numpy as np, json, dataclasses

from normality import analyze_column, parse_uploaded_file
from capability import analyze_capability
from control_charts import analyze_control_chart
from gauge_rr import analyze_gauge_rr, parse_grr_csv
from capa_rules_engine import run_capa_engine, get_capa_for_rule, get_all_rules_catalog

app = FastAPI(title="StatMind API", version="5.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class NpEnc(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, np.bool_): return bool(o)
        return super().default(o)

def jd(d): return JSONResponse(content=json.loads(json.dumps(d, cls=NpEnc)))
def jobj(obj): return jd(dataclasses.asdict(obj))

@app.get("/health")
def health(): return {"status":"ok","service":"StatMind","version":"5.0.0"}

# ── Shared ────────────────────────────────────────────────────────────────────
@app.post("/api/v1/columns")
async def get_columns(file: UploadFile = File(...)):
    c = await file.read()
    try: df = parse_uploaded_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    cols = [{"name":col,"n":int(len(d:=df[col].dropna().values.astype(float))),"mean":round(float(d.mean()),4),
             "std":round(float(d.std(ddof=1)),4),"min":round(float(d.min()),4),"max":round(float(d.max()),4)}
            for col in df.columns]
    return jd({"columns":cols})

# ── S1: Normality ─────────────────────────────────────────────────────────────
@app.post("/api/v1/normality/analyze")
async def normality(file: UploadFile = File(...), alpha: float = 0.05):
    c = await file.read()
    try: df = parse_uploaded_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    results, errors = [], []
    for col in df.columns:
        try: results.append(dataclasses.asdict(analyze_column(df[col].dropna().values.astype(float), col, alpha)))
        except Exception as e: errors.append({"column":col,"error":str(e)})
    return jd({"filename":file.filename,"rows":len(df),"columns_analyzed":len(results),"alpha":alpha,"results":results,"errors":errors})

# ── S2: Capability ────────────────────────────────────────────────────────────
@app.post("/api/v1/capability/analyze")
async def capability(file: UploadFile = File(...),
    column: str = Query(...), usl: float = Query(...), lsl: float = Query(...),
    target: float = Query(None), subgroup_size: int = Query(1)):
    c = await file.read()
    try: df = parse_uploaded_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    if column not in df.columns: raise HTTPException(404, f"Column '{column}' not found")
    try: return jobj(analyze_capability(df[column].dropna().values.astype(float), column, usl, lsl, target, subgroup_size))
    except ValueError as e: raise HTTPException(400, str(e))

# ── S3: SPC ───────────────────────────────────────────────────────────────────
@app.post("/api/v1/spc/analyze")
async def spc(file: UploadFile = File(...), column: str = Query(...), subgroup_size: int = Query(1)):
    c = await file.read()
    try: df = parse_uploaded_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    if column not in df.columns: raise HTTPException(404, f"Column '{column}' not found")
    try: return jobj(analyze_control_chart(df[column].dropna().values.astype(float), column, subgroup_size))
    except ValueError as e: raise HTTPException(400, str(e))

# ── S4: GRR ───────────────────────────────────────────────────────────────────
@app.post("/api/v1/grr/analyze")
async def grr_analyze(file: UploadFile = File(...), tolerance: float = Query(None), method: str = Query("ANOVA")):
    c = await file.read()
    try: measurements, parts, operators, col_name = parse_grr_csv(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    try: return jobj(analyze_gauge_rr(measurements, parts, operators, col_name, tolerance, method))
    except Exception as e: raise HTTPException(400, str(e))

@app.post("/api/v1/grr/preview")
async def grr_preview(file: UploadFile = File(...)):
    c = await file.read()
    try: measurements, parts, operators, col_name = parse_grr_csv(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    up = list(set(str(p) for p in parts)); uo = list(set(str(o) for o in operators))
    return jd({"column":col_name,"n_total":len(measurements),"n_parts":len(up),"n_operators":len(uo),
               "n_replicates":len(measurements)//(len(up)*len(uo)),"parts":sorted(up),"operators":sorted(uo),
               "mean":round(float(np.mean(measurements)),4),"std":round(float(np.std(measurements,ddof=1)),4)})

# ── S5: Rule-Based CAPA ───────────────────────────────────────────────────────
@app.post("/api/v1/capa/generate")
async def capa_generate(request: Request):
    """
    Body: {
      normality_result, capability_result, spc_result, grr_result,
      process_context, parameter_name, process_type
    }
    No API key needed — rule-based engine.
    """
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
    """User manually selects a rule_id. Returns full CAPA for that rule."""
    body = await request.json()
    rule_id = body.get("rule_id")
    if not rule_id: raise HTTPException(400, "rule_id required")
    from capa_rules_engine import _extract_stats
    stats = _extract_stats(
        body.get("normality_result"), body.get("capability_result"),
        body.get("spc_result"), body.get("grr_result")
    )
    result = get_capa_for_rule(rule_id, stats, body.get("process_context",""), body.get("parameter_name",""))
    return jd({"success": True, "primary_capa": result})

@app.get("/api/v1/capa/catalog")
async def capa_catalog():
    """Return full rule catalog for manual override dropdown."""
    return jd({"rules": get_all_rules_catalog()})
