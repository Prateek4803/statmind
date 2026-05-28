"""
StatMind — FRACAS (Failure Reporting, Analysis, Corrective Action System)
Google: "analyze field quality data", "fleet-wide technical issues"
Apple: "Conduct reliability tests and analyze field quality data"
Amazon: "field returns RMA analysis"
Tracks failures over product life → Weibull analysis → reliability prediction → CAPA
"""
import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class FieldFailure:
    failure_id: str
    product: str
    serial_number: str
    failure_date: str
    age_at_failure_hours: float    # operating hours at failure
    failure_mode: str
    failure_description: str
    failure_category: str    # "Wear-Out","Random","Infant Mortality","Systematic","Unknown"
    affected_component: str
    customer_impact: str     # "Safety","Functional","Cosmetic","Latent"
    rma_number: str
    repair_action: str
    # Root cause
    root_cause: str
    corrective_action_id: str   # links to 8D or CAPA
    recurrence: bool
    # Cost
    warranty_cost: float
    # FA disposition
    fa_complete: bool
    fa_conclusion: str

@dataclass
class FRACASResult:
    product: str
    total_failures: int
    total_units_fielded: int
    observation_period_hours: float
    # Reliability metrics
    failure_rate_per_hour: float  # λ = failures / total_unit_hours
    mttf_hours: float             # 1/λ
    mtbf_hours: float             # same for non-repairable, 1/λ
    fit_rate: float               # Failures in Time = λ × 1e9
    reliability_at_1000h: float   # R(1000h) = e^(-λ×1000)
    reliability_at_target: float  # R(target_hours)
    # Pareto of failure modes
    failure_mode_pareto: list     # [{mode, count, pct, cumulative_pct}]
    # Weibull parameters (if enough failures)
    weibull_beta: Optional[float]
    weibull_eta: Optional[float]
    weibull_r_squared: Optional[float]
    shape_interpretation: str
    # Trend
    failure_trend: str            # "Increasing","Stable","Decreasing"
    # Time periods
    by_period: list               # [{period, failures, failure_rate}]
    # Open issues
    open_fa_count: int
    recurrence_count: int
    total_warranty_cost: float
    # Chart data
    chart_data: dict
    conclusion: str

_failures: dict = {}  # product → list of FieldFailure
_failure_counter = [0]

def log_failure(product: str, failure_mode: str, age_hours: float,
                serial_number: str = "", failure_description: str = "",
                category: str = "Unknown", component: str = "",
                customer_impact: str = "Functional",
                warranty_cost: float = 0.0) -> FieldFailure:
    if product not in _failures:
        _failures[product] = []
    _failure_counter[0] += 1
    fid = f"FF-{datetime.now().strftime('%Y%m%d')}-{_failure_counter[0]:05d}"
    f = FieldFailure(
        failure_id=fid, product=product, serial_number=serial_number,
        failure_date=datetime.now().strftime("%Y-%m-%d"),
        age_at_failure_hours=age_hours,
        failure_mode=failure_mode, failure_description=failure_description,
        failure_category=category, affected_component=component,
        customer_impact=customer_impact, rma_number="",
        repair_action="", root_cause="", corrective_action_id="",
        recurrence=False, warranty_cost=warranty_cost,
        fa_complete=False, fa_conclusion="",
    )
    _failures[product].append(f)
    return f

def analyze_fracas(
    product: str,
    total_units_fielded: int = 1000,
    observation_hours: float = 8760.0,  # 1 year
    target_reliability_hours: float = 1000.0,
) -> FRACASResult:
    if product not in _failures or not _failures[product]:
        raise ValueError(f"No failures logged for product '{product}'.")

    failures = _failures[product]
    n_fail = len(failures)
    ages   = np.array([f.age_at_failure_hours for f in failures])
    total_unit_hours = total_units_fielded * observation_hours

    # Basic reliability metrics
    lam = n_fail / total_unit_hours  # failure rate per unit-hour
    mttf = 1 / lam if lam > 0 else float('inf')
    fit  = lam * 1e9  # FIT rate
    r1000 = float(np.exp(-lam * 1000))
    r_tgt = float(np.exp(-lam * target_reliability_hours))

    # Failure mode pareto
    mode_counts: dict = {}
    for f in failures:
        mode_counts[f.failure_mode] = mode_counts.get(f.failure_mode, 0) + 1
    sorted_modes = sorted(mode_counts.items(), key=lambda x: x[1], reverse=True)
    cumulative = 0
    pareto = []
    for mode, cnt in sorted_modes:
        cumulative += cnt
        pareto.append({
            "mode": mode, "count": cnt,
            "pct": round(cnt/n_fail*100, 1),
            "cumulative_pct": round(cumulative/n_fail*100, 1),
        })

    # Weibull fit if ≥ 5 failures
    beta = eta = r2 = None
    shape_interp = "Insufficient data for Weibull fit (need ≥ 5 failures)"
    if n_fail >= 5:
        sorted_ages = np.sort(ages)
        # Median ranks
        ranks = (np.arange(1, n_fail+1) - 0.3) / (n_fail + 0.4)
        ranks = np.clip(ranks, 1e-6, 1-1e-6)
        x = np.log(sorted_ages)
        y = np.log(-np.log(1 - ranks))
        slope, intercept, r, *_ = stats.linregress(x, y)
        beta = round(float(slope), 4)
        eta  = round(float(np.exp(-intercept/slope)), 4)
        r2   = round(float(r**2), 4)
        if beta < 1:   shape_interp = f"β={beta:.2f}: Infant mortality — field failures dominated by early defects. Improve process screening/burn-in."
        elif beta < 1.5: shape_interp = f"β={beta:.2f}: Near-random failures — exponential distribution. External/random stress driving failures."
        elif beta < 3: shape_interp = f"β={beta:.2f}: Early wear-out — fatigue beginning. Review design life margins."
        else:          shape_interp = f"β={beta:.2f}: Wear-out dominant — design life is the primary failure driver. B50={eta:.0f}h."

    # Failure trend (split into thirds)
    dates_sorted = sorted(failures, key=lambda f: f.failure_date)
    third = max(1, n_fail//3)
    period1 = len(dates_sorted[:third])
    period3 = len(dates_sorted[-third:])
    trend = "Stable"
    if period3 > period1 * 1.3: trend = "Increasing"
    elif period3 < period1 * 0.7: trend = "Decreasing"

    by_period = [
        {"period": "Early", "failures": period1, "rate_pct": round(period1/n_fail*100,1)},
        {"period": "Mid",   "failures": n_fail - period1 - period3, "rate_pct": round((n_fail-period1-period3)/n_fail*100,1)},
        {"period": "Late",  "failures": period3, "rate_pct": round(period3/n_fail*100,1)},
    ]

    chart_data = {
        "failure_ages": sorted(ages.tolist()),
        "cumulative_failures": list(range(1, n_fail+1)),
        "pareto_modes": [p["mode"] for p in pareto],
        "pareto_counts": [p["count"] for p in pareto],
        "pareto_cumulative": [p["cumulative_pct"] for p in pareto],
        "weibull_beta": beta, "weibull_eta": eta,
        "mttf": round(mttf, 1), "fit_rate": round(fit, 2),
        "reliability_curve_t": [t*observation_hours/200 for t in range(201)],
        "reliability_curve_r": [float(np.exp(-lam*t*observation_hours/200)) for t in range(201)],
    }

    conclusion = (
        f"FRACAS: {n_fail} failures / {total_units_fielded:,} units × {observation_hours:.0f}h. "
        f"MTTF={mttf:.0f}h, FIT={fit:.0f}, R(1000h)={r1000:.4f}. "
        f"Top failure mode: {pareto[0]['mode']} ({pareto[0]['pct']}%). "
        f"Trend: {trend}. {shape_interp[:60]}."
    )

    return FRACASResult(
        product=product, total_failures=n_fail,
        total_units_fielded=total_units_fielded,
        observation_period_hours=observation_hours,
        failure_rate_per_hour=round(lam, 10),
        mttf_hours=round(mttf, 2), mtbf_hours=round(mttf, 2),
        fit_rate=round(fit, 3),
        reliability_at_1000h=round(r1000, 6),
        reliability_at_target=round(r_tgt, 6),
        failure_mode_pareto=pareto,
        weibull_beta=beta, weibull_eta=eta, weibull_r_squared=r2,
        shape_interpretation=shape_interp,
        failure_trend=trend, by_period=by_period,
        open_fa_count=sum(1 for f in failures if not f.fa_complete),
        recurrence_count=sum(1 for f in failures if f.recurrence),
        total_warranty_cost=round(sum(f.warranty_cost for f in failures), 2),
        chart_data=chart_data, conclusion=conclusion,
    )

def list_products() -> list:
    return [{"product": p, "n_failures": len(f)} for p, f in _failures.items()]

import dataclasses as _dc
def failure_to_dict(f: FieldFailure) -> dict: return _dc.asdict(f)
