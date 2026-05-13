"""
StatMind — Updated API with Session 2: Capability endpoints
Run: uvicorn api2:app --port 8010
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import numpy as np
import json
import dataclasses
from normality import analyze_column, parse_uploaded_file
from capability import analyze_capability

app = FastAPI(title="StatMind API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, np.bool_): return bool(obj)
        return super().default(obj)

def to_json(obj):
    return json.loads(json.dumps(dataclasses.asdict(obj), cls=NumpyEncoder))


@app.get("/health")
def health():
    return {"status": "ok", "service": "StatMind", "version": "2.0.0"}


# ── Session 1: Normality ──────────────────────────────────────────────────────

@app.post("/api/v1/normality/analyze")
async def analyze_normality(file: UploadFile = File(...), alpha: float = 0.05):
    contents = await file.read()
    try:
        df = parse_uploaded_file(contents, file.filename)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse file: {e}")
    if df.empty:
        raise HTTPException(400, "No numeric columns found")

    results, errors = [], []
    for col in df.columns:
        try:
            r = analyze_column(df[col].dropna().values.astype(float), col, alpha=alpha)
            results.append(dataclasses.asdict(r))
        except Exception as e:
            errors.append({"column": col, "error": str(e)})

    return JSONResponse(content=json.loads(json.dumps({
        "filename": file.filename, "rows": len(df),
        "columns_analyzed": len(results), "alpha": alpha,
        "results": results, "errors": errors,
    }, cls=NumpyEncoder)))


# ── Session 2: Capability ─────────────────────────────────────────────────────

@app.post("/api/v1/capability/analyze")
async def analyze_cap(
    file: UploadFile = File(...),
    column: str = Query(..., description="Column name to analyze"),
    usl: float = Query(..., description="Upper spec limit"),
    lsl: float = Query(..., description="Lower spec limit"),
    target: float = Query(None, description="Target value (optional)"),
    subgroup_size: int = Query(1, description="Subgroup size (1 = individuals)"),
):
    contents = await file.read()
    try:
        df = parse_uploaded_file(contents, file.filename)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse file: {e}")

    if column not in df.columns:
        raise HTTPException(404, f"Column '{column}' not found. Available: {df.columns.tolist()}")

    data = df[column].dropna().values.astype(float)
    try:
        report = analyze_capability(data, column, usl, lsl, target, subgroup_size)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return JSONResponse(content=json.loads(json.dumps(dataclasses.asdict(report), cls=NumpyEncoder)))


@app.post("/api/v1/capability/columns")
async def get_columns(file: UploadFile = File(...)):
    """Return available numeric columns + basic stats for the spec limit form."""
    contents = await file.read()
    try:
        df = parse_uploaded_file(contents, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))

    cols = []
    for col in df.columns:
        d = df[col].dropna().values.astype(float)
        cols.append({
            "name": col, "n": int(len(d)),
            "mean": round(float(d.mean()), 4),
            "std": round(float(d.std(ddof=1)), 4),
            "min": round(float(d.min()), 4),
            "max": round(float(d.max()), 4),
        })
    return JSONResponse(content={"columns": cols})
