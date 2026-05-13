"""
StatMind — API v4: Sessions 1–4
Run: uvicorn api4:app --port 8010
"""
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import numpy as np, json, dataclasses
from normality import analyze_column, parse_uploaded_file
from capability import analyze_capability
from control_charts import analyze_control_chart
from gauge_rr import analyze_gauge_rr, parse_grr_csv

app = FastAPI(title="StatMind API", version="4.0.0")
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
def health(): return {"status":"ok","service":"StatMind","version":"4.0.0"}

@app.post("/api/v1/columns")
async def get_columns(file: UploadFile = File(...)):
    c = await file.read()
    try: df = parse_uploaded_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    cols = [{"name":col,"n":int(len(d:=df[col].dropna().values.astype(float))),"mean":round(float(d.mean()),4),
             "std":round(float(d.std(ddof=1)),4),"min":round(float(d.min()),4),"max":round(float(d.max()),4)}
            for col in df.columns]
    return jd({"columns":cols})

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

@app.post("/api/v1/spc/analyze")
async def spc(file: UploadFile = File(...), column: str = Query(...), subgroup_size: int = Query(1)):
    c = await file.read()
    try: df = parse_uploaded_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    if column not in df.columns: raise HTTPException(404, f"Column '{column}' not found")
    try: return jobj(analyze_control_chart(df[column].dropna().values.astype(float), column, subgroup_size))
    except ValueError as e: raise HTTPException(400, str(e))

@app.post("/api/v1/grr/analyze")
async def grr_analyze(
    file: UploadFile = File(...),
    tolerance: float = Query(None),
    method: str = Query("ANOVA"),
):
    """Upload a GRR study CSV with columns: Part, Operator, Measurement"""
    c = await file.read()
    try:
        measurements, parts, operators, col_name = parse_grr_csv(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    try:
        report = analyze_gauge_rr(measurements, parts, operators, col_name, tolerance, method)
        return jobj(report)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/grr/preview")
async def grr_preview(file: UploadFile = File(...)):
    """Return study design info before running analysis."""
    c = await file.read()
    try:
        measurements, parts, operators, col_name = parse_grr_csv(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    unique_parts = list(set(str(p) for p in parts))
    unique_ops   = list(set(str(o) for o in operators))
    n_reps = len(measurements) // (len(unique_parts) * len(unique_ops))
    return jd({
        "column": col_name, "n_total": len(measurements),
        "n_parts": len(unique_parts), "n_operators": len(unique_ops), "n_replicates": n_reps,
        "parts": sorted(unique_parts), "operators": sorted(unique_ops),
        "mean": round(float(np.mean(measurements)),4), "std": round(float(np.std(measurements,ddof=1)),4),
    })
