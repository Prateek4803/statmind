"""
StatMind E8 — Tolerance Intervals
One-sided / two-sided tolerance intervals.
Answers: "What range covers X% of the population with Y% confidence?"
Used in PPAP, design validation, IQ/OQ/PQ in medical devices.
References: ASTM E2810, ISO 16269-6, NIST Handbook 148
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import Optional


@dataclass
class ToleranceResult:
    column: str
    n: int
    mean: float
    std: float
    # Parameters
    coverage: float       # P — proportion of population covered (e.g. 0.99)
    confidence: float     # γ — confidence level (e.g. 0.95)
    interval_type: str    # "two_sided", "one_sided_lower", "one_sided_upper"
    # Tolerance factors
    k_factor: float       # tolerance factor k
    # Interval bounds
    lower: Optional[float]
    upper: Optional[float]
    # Interpretation
    interpretation: str   # plain English
    # Comparison to spec limits
    within_spec: Optional[bool]
    usl: Optional[float]
    lsl: Optional[float]
    spec_verdict: str
    # Normality check
    normality_p: float
    normality_ok: bool
    # Chart data
    chart_data: dict


def _k_two_sided(n: int, coverage: float, confidence: float) -> float:
    """
    Two-sided tolerance interval k-factor.
    Uses Howe's method (approximate, widely used in industry).
    """
    z_p = float(stats.norm.ppf((1 + coverage) / 2))   # z for coverage/2
    chi2_val = float(stats.chi2.ppf(1 - confidence, df=n-1))  # chi2 lower tail
    # Howe approximation
    k = z_p * np.sqrt((n + 1) / n) * np.sqrt(1 + (n - 1) / chi2_val * (1/n + z_p**2 / (2*(n+1))))
    return float(k)


def _k_one_sided(n: int, coverage: float, confidence: float) -> float:
    """
    One-sided tolerance interval k-factor.
    Uses exact non-central t distribution method.
    """
    z_p = float(stats.norm.ppf(coverage))
    delta = z_p * np.sqrt(n)
    # k = ncp_t(confidence, df=n-1, nc=delta) / sqrt(n)
    k = float(stats.nct.ppf(confidence, df=n-1, nc=delta) / np.sqrt(n))
    return k


def tolerance_interval(
    data: np.ndarray,
    column: str = "Measurement",
    coverage: float = 0.99,       # 99% of population
    confidence: float = 0.95,     # 95% confidence
    interval_type: str = "two_sided",
    usl: float = None,
    lsl: float = None,
) -> ToleranceResult:
    """
    Calculate tolerance interval.
    interval_type: "two_sided", "one_sided_lower", "one_sided_upper"
    """
    data = data[~np.isnan(data)].astype(float)
    n    = len(data)
    if n < 5:
        raise ValueError("Need at least 5 data points for tolerance interval.")

    mean = float(np.mean(data))
    std  = float(np.std(data, ddof=1))

    # Normality check
    _, sw_p = stats.shapiro(data[:5000])
    norm_ok = float(sw_p) > 0.05

    # Calculate k factor and bounds
    if interval_type == "two_sided":
        k = _k_two_sided(n, coverage, confidence)
        lower = round(mean - k * std, 6)
        upper = round(mean + k * std, 6)
        interp = (f"With {confidence*100:.0f}% confidence, at least {coverage*100:.0f}% of "
                  f"all future {column} measurements will fall between [{lower:.4f}, {upper:.4f}].")
    elif interval_type == "one_sided_upper":
        k = _k_one_sided(n, coverage, confidence)
        lower = None
        upper = round(mean + k * std, 6)
        interp = (f"With {confidence*100:.0f}% confidence, at least {coverage*100:.0f}% of "
                  f"all future {column} measurements will be ≤ {upper:.4f}.")
    else:  # one_sided_lower
        k = _k_one_sided(n, coverage, confidence)
        lower = round(mean - k * std, 6)
        upper = None
        interp = (f"With {confidence*100:.0f}% confidence, at least {coverage*100:.0f}% of "
                  f"all future {column} measurements will be ≥ {lower:.4f}.")

    # Spec comparison
    within_spec = None
    spec_verdict = ""
    if usl is not None or lsl is not None:
        ti_ok = True
        if usl is not None and upper is not None and upper > usl:
            ti_ok = False
        if lsl is not None and lower is not None and lower < lsl:
            ti_ok = False
        within_spec = ti_ok
        spec_verdict = (
            f"✅ Tolerance interval fits within spec limits — process meets design intent with "
            f"{coverage*100:.0f}%/{confidence*100:.0f}% coverage/confidence."
            if ti_ok else
            f"❌ Tolerance interval EXCEEDS spec limits — process does NOT meet design intent. "
            f"{'Upper TI ' + str(upper) + ' > USL ' + str(usl) if upper and usl and upper > usl else ''} "
            f"{'Lower TI ' + str(lower) + ' < LSL ' + str(lsl) if lower and lsl and lower < lsl else ''}".strip()
        )

    # Chart data
    x = np.linspace(mean - 4*std, mean + 4*std, 300)
    y = stats.norm.pdf(x, mean, std).tolist()
    sorted_data = np.sort(data)
    theo_q = [float(stats.norm.ppf((i+0.5)/n)) for i in range(n)]

    chart_data = {
        "distribution_x": [round(float(v),6) for v in x],
        "distribution_y": [round(float(v),6) for v in y],
        "mean": round(mean, 6),
        "std": round(std, 6),
        "lower": lower,
        "upper": upper,
        "usl": usl,
        "lsl": lsl,
        "data_values": sorted_data.tolist(),
        "prob_plot": {
            "theoretical": theo_q,
            "sample": sorted_data.tolist(),
        }
    }

    if not norm_ok:
        interp += " NOTE: Data appears non-normal (SW p={:.4f}). Tolerance interval assumes normality — consider transforming data first (use E5 Transformation).".format(float(sw_p))

    return ToleranceResult(
        column=column, n=n, mean=round(mean,6), std=round(std,6),
        coverage=coverage, confidence=confidence,
        interval_type=interval_type,
        k_factor=round(k, 5),
        lower=lower, upper=upper,
        interpretation=interp,
        within_spec=within_spec, usl=usl, lsl=lsl,
        spec_verdict=spec_verdict,
        normality_p=round(float(sw_p),5), normality_ok=norm_ok,
        chart_data=chart_data,
    )
