"""
StatMind — Capability Router
/api/v1/capability/analyze

Extracted from main.py (was inline endpoint).
Part of the router-split refactor to eliminate the 2,897-line monolith.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from capability import analyze_capability, CapabilityReport
from capa_rules_engine import run_capa_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/capability", tags=["capability"])


# ── Request / Response models ─────────────────────────────────────────────────

class CapabilityRequest(BaseModel):
    column: str                   = Field(..., description="Column name in the uploaded CSV/Excel")
    usl: float                    = Field(..., description="Upper Specification Limit")
    lsl: float                    = Field(..., description="Lower Specification Limit")
    target: Optional[float]       = Field(None, description="Nominal/target value (defaults to midspec)")
    subgroup_size: int            = Field(1, ge=1, le=100, description="Rational subgroup size")
    process_type: str             = Field("", description="Process family for CAPA matching")
    confidence: float             = Field(0.95, ge=0.80, le=0.999, description="CI confidence level")
    session_id: Optional[str]     = Field(None, description="Session token (for future auth)")

    @validator("usl")
    def usl_gt_lsl(cls, v, values):
        if "lsl" in values and v <= values["lsl"]:
            raise ValueError(f"USL ({v}) must be greater than LSL ({values['lsl']})")
        return v


class CapabilityResponse(BaseModel):
    success: bool
    column: str
    n: int
    mean: float
    std_within: float
    std_overall: float
    usl: float
    lsl: float
    target: float
    cp: float
    cpk: float
    cpm: float
    pp: float
    ppk: float
    cpu: float
    cpl: float
    cpk_ci_95_lower: float
    cpk_ci_95_upper: float
    cpk_ci_90_lower: float
    cpk_ci_90_upper: float
    cpk_ci_99_lower: float
    cpk_ci_99_upper: float
    ppm_within: float
    ppm_overall: float
    sigma_level: float
    verdict: str
    verdict_detail: str
    capa_required: bool
    capa_notes: list
    histogram_data: dict
    capability_curve_data: dict
    subgroup_size: int
    capa_results: Optional[dict] = None
    elapsed_ms: float


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/analyze", response_model=CapabilityResponse)
async def analyze(
    file: UploadFile = File(..., description="CSV or Excel file with process data"),
    column: str      = Form(...),
    usl: float       = Form(...),
    lsl: float       = Form(...),
    target: Optional[float]   = Form(None),
    subgroup_size: int         = Form(1),
    process_type: str          = Form(""),
    confidence: float          = Form(0.95),
    session_id: Optional[str]  = Form(None),
) -> CapabilityResponse:
    """
    Run full process capability analysis on an uploaded file column.

    Returns Cp, Cpk, Cpm, Pp, Ppk, confidence intervals, PPM, sigma level,
    histogram/curve data for charting, and optional CAPA recommendations.
    """
    t0 = time.perf_counter()

    # ── File validation ───────────────────────────────────────────────────
    filename = file.filename or ""
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(
            status_code=422,
            detail="Unsupported file type. Upload a .csv or .xlsx file."
        )

    # ── Read file ─────────────────────────────────────────────────────────
    try:
        content = await file.read()
        if filename.lower().endswith(".csv"):
            import io
            df = pd.read_csv(io.BytesIO(content))
        else:
            import io
            df = pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        logger.exception("File read failed: %s", exc)
        raise HTTPException(status_code=422, detail=f"Could not read file: {exc}")

    # ── Column validation ─────────────────────────────────────────────────
    if column not in df.columns:
        available = list(df.columns)
        raise HTTPException(
            status_code=422,
            detail=f"Column '{column}' not found. Available columns: {available}"
        )

    # ── Extract numeric data ──────────────────────────────────────────────
    raw = pd.to_numeric(df[column], errors="coerce").dropna()
    if len(raw) < 5:
        raise HTTPException(
            status_code=422,
            detail=f"Column '{column}' has fewer than 5 numeric values ({len(raw)} found)."
        )
    data = raw.to_numpy(dtype=float)

    # ── Run analysis (offloaded to thread — numpy can block event loop) ───
    try:
        report: CapabilityReport = await asyncio.to_thread(
            analyze_capability,
            data, column, usl, lsl, target, subgroup_size, confidence
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Capability analysis failed: %s", exc)
        raise HTTPException(status_code=500, detail="Internal analysis error.")

    # ── Optional CAPA engine ──────────────────────────────────────────────
    capa_results = None
    if report.capa_required and process_type:
        try:
            capa_results = await asyncio.to_thread(
                run_capa_engine,
                capability_result={
                    "cpk": report.cpk,
                    "ppk": report.ppk,
                    "cp":  report.cp,
                    "ppm_within": report.ppm_within,
                },
                process_context=process_type,
                parameter_name=column,
                process_type=process_type,
            )
        except Exception as exc:
            logger.warning("CAPA engine failed (non-fatal): %s", exc)

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    return CapabilityResponse(
        success=True,
        column=report.column,
        n=report.n,
        mean=report.mean,
        std_within=report.std_within,
        std_overall=report.std_overall,
        usl=report.usl,
        lsl=report.lsl,
        target=report.target,
        cp=report.cp,
        cpk=report.cpk,
        cpm=report.cpm,
        pp=report.pp,
        ppk=report.ppk,
        cpu=report.cpu,
        cpl=report.cpl,
        cpk_ci_95_lower=report.cpk_ci_95.lower,
        cpk_ci_95_upper=report.cpk_ci_95.upper,
        cpk_ci_90_lower=report.cpk_ci_90.lower,
        cpk_ci_90_upper=report.cpk_ci_90.upper,
        cpk_ci_99_lower=report.cpk_ci_99.lower,
        cpk_ci_99_upper=report.cpk_ci_99.upper,
        ppm_within=report.ppm_within,
        ppm_overall=report.ppm_overall,
        sigma_level=report.sigma_level,
        verdict=report.verdict,
        verdict_detail=report.verdict_detail,
        capa_required=report.capa_required,
        capa_notes=report.capa_notes,
        histogram_data=report.histogram_data,
        capability_curve_data=report.capability_curve_data,
        subgroup_size=report.subgroup_size,
        capa_results=capa_results,
        elapsed_ms=elapsed_ms,
    )
