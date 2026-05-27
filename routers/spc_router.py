"""
StatMind — SPC Router
/api/v1/spc/analyze

Extracted from main.py.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from control_charts import (
    build_imr, build_xbar_r, build_xbar_s,
    build_p_chart, build_c_chart, build_u_chart,
    auto_select_and_build,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/spc", tags=["spc"])


@router.post("/analyze")
async def spc_analyze(
    file: UploadFile       = File(...),
    column: str            = Form(...),
    chart_type: str        = Form("auto"),
    subgroup_size: int     = Form(1),
    session_id: Optional[str] = Form(None),
):
    """
    Run SPC control chart analysis.

    chart_type: "auto" | "I-MR" | "Xbar-R" | "Xbar-S" | "P" | "C" | "U"
    For attribute charts (P/C/U) additional count/size columns must be
    passed as defective_col, sample_size_col, defect_col, unit_col.
    """
    t0 = time.perf_counter()

    filename = file.filename or ""
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(422, "Upload a .csv or .xlsx file.")

    try:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content)) if filename.lower().endswith(".csv") \
             else pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(422, f"File read error: {exc}")

    if column not in df.columns:
        raise HTTPException(422, f"Column '{column}' not found. Available: {list(df.columns)}")

    raw = pd.to_numeric(df[column], errors="coerce").dropna()
    if len(raw) < 3:
        raise HTTPException(422, f"Need at least 3 numeric values; got {len(raw)}.")

    data = raw.to_numpy(dtype=float)

    try:
        if chart_type == "auto":
            result = await asyncio.to_thread(auto_select_and_build, data, column, subgroup_size)
        elif chart_type == "I-MR":
            result = await asyncio.to_thread(build_imr, data, column)
        elif chart_type == "Xbar-R":
            result = await asyncio.to_thread(build_xbar_r, data, column, subgroup_size)
        elif chart_type == "Xbar-S":
            result = await asyncio.to_thread(build_xbar_s, data, column, subgroup_size)
        else:
            raise HTTPException(422, f"chart_type '{chart_type}' not supported via this endpoint.")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        logger.exception("SPC analysis failed: %s", exc)
        raise HTTPException(500, "Internal SPC analysis error.")

    result["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    result["success"] = True
    return result
