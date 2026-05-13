"""
StatMind — FastAPI Backend (Session 1)
Run: uvicorn api:app --port 8010
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import numpy as np
import json
from normality import analyze_column, parse_uploaded_file

app = FastAPI(title="StatMind API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.bool_):
            return bool(obj)
        return super().default(obj)


@app.get("/health")
def health():
    return {"status": "ok", "service": "StatMind"}


@app.post("/api/v1/normality/analyze")
async def analyze_normality(
    file: UploadFile = File(...),
    alpha: float = 0.05
):
    """
    Upload Excel or CSV file. Returns normality analysis for all numeric columns.
    """
    if not file.filename:
        raise HTTPException(400, "No file provided")

    contents = await file.read()
    try:
        df = parse_uploaded_file(contents, file.filename)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse file: {str(e)}")

    if df.empty or len(df.columns) == 0:
        raise HTTPException(400, "No numeric columns found in file")

    results = []
    errors = []
    for col in df.columns:
        data = df[col].dropna().values
        try:
            report = analyze_column(data.astype(float), col, alpha=alpha)
            # Convert dataclass to dict
            import dataclasses
            results.append(dataclasses.asdict(report))
        except Exception as e:
            errors.append({"column": col, "error": str(e)})

    response = {
        "filename": file.filename,
        "rows": len(df),
        "columns_analyzed": len(results),
        "alpha": alpha,
        "results": results,
        "errors": errors,
    }

    return JSONResponse(content=json.loads(json.dumps(response, cls=NumpyEncoder)))


@app.post("/api/v1/normality/analyze-column")
async def analyze_single_column(
    file: UploadFile = File(...),
    column: str = "",
    alpha: float = 0.05
):
    """Analyze a specific column by name."""
    contents = await file.read()
    try:
        df = parse_uploaded_file(contents, file.filename)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse file: {str(e)}")

    if column not in df.columns:
        raise HTTPException(404, f"Column '{column}' not found. Available: {df.columns.tolist()}")

    data = df[column].dropna().values.astype(float)
    import dataclasses
    report = analyze_column(data, column, alpha=alpha)
    return JSONResponse(content=json.loads(json.dumps(dataclasses.asdict(report), cls=NumpyEncoder)))
