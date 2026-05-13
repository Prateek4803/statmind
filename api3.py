"""
StatMind — API v3 with Sessions 1, 2, 3
Run: uvicorn api3:app --port 8010
"""
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import numpy as np, json, dataclasses
from normality import analyze_column, parse_uploaded_file
from capability import analyze_capability
from control_charts import analyze_control_chart

app = FastAPI(title="StatMind API", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class NpEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, np.integer): return int(o)
        if isinstance(o, np.floating): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, np.bool_): return bool(o)
        return super().default(o)

def j(obj): return json.loads(json.dumps(dataclasses.asdict(obj), cls=NpEncoder))
def jd(d):  return JSONResponse(content=json.loads(json.dumps(d, cls=NpEncoder)))

@app.get("/health")
def health(): return {"status": "ok", "service": "StatMind", "version": "3.0.0"}

# ── Shared: get columns ───────────────────────────────────────────────────────
@app.post("/api/v1/columns")
async def get_columns(file: UploadFile = File(...)):
    c = await file.read()
    try: df = parse_uploaded_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    cols = []
    for col in df.columns:
        d = df[col].dropna().values.astype(float)
        cols.append({"name": col, "n": int(len(d)), "mean": round(float(d.mean()),4),
                     "std": round(float(d.std(ddof=1)),4), "min": round(float(d.min()),4), "max": round(float(d.max()),4)})
    return jd({"columns": cols})

# ── Session 1: Normality ──────────────────────────────────────────────────────
@app.post("/api/v1/normality/analyze")
async def normality(file: UploadFile = File(...), alpha: float = 0.05):
    c = await file.read()
    try: df = parse_uploaded_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    results, errors = [], []
    for col in df.columns:
        try: results.append(dataclasses.asdict(analyze_column(df[col].dropna().values.astype(float), col, alpha)))
        except Exception as e: errors.append({"column": col, "error": str(e)})
    return jd({"filename": file.filename, "rows": len(df), "columns_analyzed": len(results),
               "alpha": alpha, "results": results, "errors": errors})

# ── Session 2: Capability ─────────────────────────────────────────────────────
@app.post("/api/v1/capability/analyze")
async def capability(file: UploadFile = File(...),
    column: str = Query(...), usl: float = Query(...), lsl: float = Query(...),
    target: float = Query(None), subgroup_size: int = Query(1)):
    c = await file.read()
    try: df = parse_uploaded_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    if column not in df.columns: raise HTTPException(404, f"Column '{column}' not found")
    try: return jd(dataclasses.asdict(analyze_capability(df[column].dropna().values.astype(float), column, usl, lsl, target, subgroup_size)))
    except ValueError as e: raise HTTPException(400, str(e))

# ── Session 3: Control Charts ─────────────────────────────────────────────────
@app.post("/api/v1/spc/analyze")
async def spc(file: UploadFile = File(...),
    column: str = Query(...), subgroup_size: int = Query(1)):
    c = await file.read()
    try: df = parse_uploaded_file(c, file.filename)
    except Exception as e: raise HTTPException(400, str(e))
    if column not in df.columns: raise HTTPException(404, f"Column '{column}' not found")
    try: return jd(dataclasses.asdict(analyze_control_chart(df[column].dropna().values.astype(float), column, subgroup_size)))
    except ValueError as e: raise HTTPException(400, str(e))
