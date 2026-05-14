"""
StatMind E1 — Hypothesis Testing API routes
Add to main.py:  from hypothesis_api import router as hyp_router
                 app.include_router(hyp_router)
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import numpy as np

from hypothesis import (one_sample_t, two_sample_t, paired_t,
                         one_way_anova, chi_square, mann_whitney, kruskal_wallis)
from hypothesis_charts import (chart_one_sample_t, chart_two_sample_t, chart_paired_t,
                                chart_one_way_anova, chart_chi_square,
                                chart_mann_whitney, chart_kruskal_wallis)

router = APIRouter(prefix="/api/v1/hypothesis", tags=["E1 Hypothesis Testing"])


# ── Request models ────────────────────────────

class OneSampleReq(BaseModel):
    data: List[float]
    target: float
    alpha: float = 0.05

class TwoSampleReq(BaseModel):
    data1: List[float]
    data2: List[float]
    alpha: float = 0.05
    label1: str = "Group 1"
    label2: str = "Group 2"

class PairedReq(BaseModel):
    data1: List[float]
    data2: List[float]
    alpha: float = 0.05
    label1: str = "Before"
    label2: str = "After"

class AnovaReq(BaseModel):
    groups: List[List[float]]
    group_names: Optional[List[str]] = None
    alpha: float = 0.05

class ChiSquareReq(BaseModel):
    observed: List             # 1-D list or 2-D list-of-lists
    alpha: float = 0.05

class MannWhitneyReq(BaseModel):
    data1: List[float]
    data2: List[float]
    alpha: float = 0.05
    label1: str = "Group 1"
    label2: str = "Group 2"

class KruskalReq(BaseModel):
    groups: List[List[float]]
    group_names: Optional[List[str]] = None
    alpha: float = 0.05


# ── Endpoints ────────────────────────────────

@router.post("/one-sample-t")
def ep_one_sample(req: OneSampleReq):
    result = one_sample_t(req.data, req.target, req.alpha)
    chart  = chart_one_sample_t(req.data, result)
    return {**result, "chart": chart}


@router.post("/two-sample-t")
def ep_two_sample(req: TwoSampleReq):
    result = two_sample_t(req.data1, req.data2, req.alpha, req.label1, req.label2)
    chart  = chart_two_sample_t(req.data1, req.data2, result)
    return {**result, "chart": chart}


@router.post("/paired-t")
def ep_paired(req: PairedReq):
    result = paired_t(req.data1, req.data2, req.alpha, req.label1, req.label2)
    chart  = chart_paired_t(req.data1, req.data2, result)
    return {**result, "chart": chart}


@router.post("/one-way-anova")
def ep_anova(req: AnovaReq):
    result = one_way_anova(req.groups, req.group_names, req.alpha)
    chart  = chart_one_way_anova(req.groups, result)
    return {**result, "chart": chart}


@router.post("/chi-square")
def ep_chi_square(req: ChiSquareReq):
    result = chi_square(req.observed, req.alpha)
    chart  = chart_chi_square(req.observed, result)
    return {**result, "chart": chart}


@router.post("/mann-whitney")
def ep_mann_whitney(req: MannWhitneyReq):
    result = mann_whitney(req.data1, req.data2, req.alpha, req.label1, req.label2)
    chart  = chart_mann_whitney(req.data1, req.data2, result)
    return {**result, "chart": chart}


@router.post("/kruskal-wallis")
def ep_kruskal(req: KruskalReq):
    result = kruskal_wallis(req.groups, req.group_names, req.alpha)
    chart  = chart_kruskal_wallis(req.groups, result)
    return {**result, "chart": chart}


# ── Catalog (discovery endpoint) ─────────────

@router.get("/catalog")
def catalog():
    return {"tests": [
        {"id": "one-sample-t",   "name": "One-Sample t-Test",
         "use": "Is this process mean equal to a target value?",
         "parametric": True,  "groups": 1},
        {"id": "two-sample-t",   "name": "Two-Sample t-Test",
         "use": "Are Chamber A and Chamber B significantly different?",
         "parametric": True,  "groups": 2},
        {"id": "paired-t",       "name": "Paired t-Test",
         "use": "Did this process change before vs after an adjustment?",
         "parametric": True,  "groups": 2, "paired": True},
        {"id": "one-way-anova",  "name": "One-Way ANOVA",
         "use": "Do 3+ machines/operators/shifts produce different means?",
         "parametric": True,  "groups": "3+"},
        {"id": "chi-square",     "name": "Chi-Square Test",
         "use": "Is defect type independent of production shift?",
         "parametric": False, "groups": "categorical"},
        {"id": "mann-whitney",   "name": "Mann-Whitney U Test",
         "use": "Non-normal 2-group comparison — alternative to 2-sample t",
         "parametric": False, "groups": 2},
        {"id": "kruskal-wallis", "name": "Kruskal-Wallis H Test",
         "use": "Non-normal 3+ group comparison — alternative to ANOVA",
         "parametric": False, "groups": "3+"},
    ]}
