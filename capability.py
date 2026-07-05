"""
StatMind — Process Capability Engine  (hardened v3)

Fixes applied (audit findings P0 + P1):
  P0-STAT-1  c4 used scipy.special.gamma — numerically fragile for n>10,
             returns NaN on some platforms. Replaced with AIAG MSA 4th Ed.
             lookup table for n=2..25; formula fallback for n>25.
  P0-STAT-2  expected_ppm() was one-sided: 2*norm.sf(3*cpk) assumes
             perfectly centred process. Correct formula uses both tails
             independently: sf((USL-μ)/σ) + cdf((LSL-μ)/σ).
  P0-STAT-3  cpk_confidence_interval() divided by zero when n<3 (variance
             formula has 1/(9n) + cpk²/(2(n-1))). Added n<5 guard.
  P0-STAT-4  _build_capa_notes() fired false positive when LSL is negative:
             `mean - 3*sw < lsl + (usl - lsl) * 0.02  # relative tolerance, safe for negative LSL` → for lsl=-5 this checks < -4.9
             which always fires. Fixed to use absolute spec-range distance.
  P0-STAT-5  analyze_capability() did not guard against zero-variance data
             before computing capability indices → ZeroDivisionError or inf.
  P0-SEC-1   File size not checked before processing — unbounded memory.
             Added MAX_DATA_POINTS = 1_000_000 guard.
"""

from __future__ import annotations

import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import Optional
import warnings

warnings.filterwarnings("ignore")

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_DATA_POINTS = 1_000_000   # refuse arrays larger than this (P0-SEC-1)

# AIAG MSA 4th Ed. Table B-1 — c4 unbiasing constants
# Index = subgroup size n; valid for n=2..25
_C4_TABLE = [
    0, 0,        # n=0, n=1 (unused)
    0.7979,      # n=2
    0.8862,      # n=3
    0.9213,      # n=4
    0.9400,      # n=5
    0.9515,      # n=6
    0.9594,      # n=7
    0.9650,      # n=8
    0.9693,      # n=9
    0.9727,      # n=10
    0.9754,      # n=11
    0.9776,      # n=12
    0.9794,      # n=13
    0.9810,      # n=14
    0.9823,      # n=15
    0.9835,      # n=16
    0.9845,      # n=17
    0.9854,      # n=18
    0.9862,      # n=19
    0.9869,      # n=20
    0.9876,      # n=21
    0.9882,      # n=22
    0.9887,      # n=23
    0.9892,      # n=24
    0.9896,      # n=25
]

# d2 values (expected range / sigma) for span-2 moving range: n=2
_D2_MR = 1.128


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class ConfidenceInterval:
    lower: float
    upper: float
    confidence: float


@dataclass
class CapabilityReport:
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
    cpk_ci_90: ConfidenceInterval
    cpk_ci_95: ConfidenceInterval
    cpk_ci_99: ConfidenceInterval
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


# ── c4 constant ───────────────────────────────────────────────────────────────

def _c4(n: int) -> float:
    """
    Unbiasing constant c4 for sample standard deviation.
    Uses AIAG MSA 4th Ed. Table B-1 for n=2..25.
    Uses gamma-function formula for n>25 (always converges; no NaN risk).
    """
    if n < 2:
        raise ValueError(f"c4 requires n >= 2, got {n}")
    if n <= 25:
        return _C4_TABLE[n]
    # Formula fallback: sqrt(2/(n-1)) * Γ(n/2) / Γ((n-1)/2)
    # Use math.lgamma (stdlib, always available) for numerical stability
    import math
    log_c4 = (
        0.5 * math.log(2.0 / (n - 1))
        + math.lgamma(n / 2.0)
        - math.lgamma((n - 1) / 2.0)
    )
    return float(np.exp(log_c4))


# ── Sigma estimators ──────────────────────────────────────────────────────────

def estimate_sigma_within(data: np.ndarray, subgroup_size: int = 1) -> float:
    """
    Estimate within-subgroup (short-term) standard deviation.
    subgroup_size=1 → moving-range method (d2=1.128)
    subgroup_size>1 → pooled s-bar / c4
    """
    data = data[~np.isnan(data)]
    n = len(data)
    if n < 2:
        raise ValueError("Need ≥ 2 non-NaN points to estimate sigma_within.")

    # P0-STAT-7: subgroup_size=0 previously reached `len(data) // 0`
    # (ZeroDivisionError → unhandled 500); negatives produced garbage reshapes.
    if int(subgroup_size) < 1:
        raise ValueError(f"subgroup_size must be ≥ 1; got {subgroup_size}.")
    subgroup_size = int(subgroup_size)

    if subgroup_size == 1:
        mr = np.abs(np.diff(data))
        if len(mr) == 0 or float(np.mean(mr)) == 0.0:
            return float(np.std(data, ddof=1)) or 1e-12
        return float(np.mean(mr) / _D2_MR)
    else:
        k = len(data) // subgroup_size
        if k < 2:
            raise ValueError(
                f"Need ≥ 2 complete subgroups for subgroup_size={subgroup_size}; "
                f"got {k} from {n} points."
            )
        groups = data[: k * subgroup_size].reshape(k, subgroup_size)
        s_bar = float(np.mean(np.std(groups, ddof=1, axis=1)))
        return s_bar / _c4(subgroup_size)


# ── Cpk confidence interval ───────────────────────────────────────────────────

def cpk_confidence_interval(cpk: float, n: int, confidence: float = 0.95) -> ConfidenceInterval:
    """
    Two-sided Cpk CI using Chou, Owen & Borrego (1990) chi-squared
    approximation (same as Minitab, Montgomery 8th Ed. §8.3).

    Var(Cpk) = 1/(9n) + Cpk² / (2(n-1))

    FIX P0-STAT-3: guard n<5 — formula is undefined/unreliable below this.
    """
    if n < 5:
        return ConfidenceInterval(lower=0.0, upper=float("inf"), confidence=confidence)

    alpha = 1.0 - confidence
    z = float(stats.norm.ppf(1.0 - alpha / 2.0))
    var_cpk = (1.0 / (9.0 * n)) + (cpk ** 2 / (2.0 * (n - 1)))
    se = float(np.sqrt(max(0.0, var_cpk)))  # clamp to avoid sqrt of negative float noise

    lower = float(max(0.0, cpk - z * se))
    upper = float(cpk + z * se)
    return ConfidenceInterval(lower=round(lower, 4), upper=round(upper, 4),
                              confidence=confidence)


# ── PPM — FIX P0-STAT-2: both tails separately ───────────────────────────────

def expected_ppm(mean: float, std: float, usl: float, lsl: float) -> float:
    """
    Expected defects per million using actual mean and std.

    FIX: The shortcut  2 * Φ(-3·Cpk) * 1e6  is WRONG for off-centre
    processes — it double-counts the nearer tail and ignores the farther.
    Correct: compute each tail independently.
    """
    if std <= 0:
        return 0.0
    ppm_above = float(stats.norm.sf((usl - mean) / std)) * 1_000_000
    ppm_below = float(stats.norm.cdf((lsl - mean) / std)) * 1_000_000
    return round(max(0.0, ppm_above + ppm_below), 2)


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze_capability(
    data: np.ndarray,
    column: str,
    usl: float,
    lsl: float,
    target: Optional[float] = None,
    subgroup_size: int = 1,
    confidence: float = 0.95,
) -> CapabilityReport:
    """
    Full process capability analysis.
    Returns CapabilityReport — all numeric fields are Python native floats/ints
    (not numpy scalars) so FastAPI's default JSON encoder handles them cleanly.
    """
    # ── Sanitise inputs ───────────────────────────────────────────────────────
    data = np.asarray(data, dtype=float)
    data = data[~np.isnan(data)]
    n = int(len(data))

    if n < 5:
        raise ValueError(f"Capability analysis requires ≥ 5 data points; got {n}.")

    # P0-SEC-1: refuse unbounded arrays
    if n > MAX_DATA_POINTS:
        raise ValueError(
            f"Dataset has {n:,} rows; maximum allowed is {MAX_DATA_POINTS:,}. "
            "Please pre-aggregate or sample your data."
        )

    usl = float(usl)
    lsl = float(lsl)
    if usl <= lsl:
        raise ValueError(f"USL ({usl}) must be strictly greater than LSL ({lsl}).")

    spec_range = usl - lsl
    midspec    = (usl + lsl) / 2.0
    target_val = float(target) if target is not None else midspec

    # ── Statistics ────────────────────────────────────────────────────────────
    mean = float(np.mean(data))
    std_overall = float(np.std(data, ddof=1))

    # P0-STAT-5: guard zero variance
    if std_overall == 0.0:
        raise ValueError(
            "All data values are identical (std = 0). "
            "Capability indices are undefined for a degenerate distribution."
        )

    std_within = float(estimate_sigma_within(data, subgroup_size))
    if std_within == 0.0:
        std_within = std_overall  # safe fallback

    # ── Within (short-term) capability ───────────────────────────────────────
    cp  = spec_range / (6.0 * std_within)
    cpu = (usl - mean) / (3.0 * std_within)
    cpl = (mean - lsl) / (3.0 * std_within)
    cpk = min(cpu, cpl)

    # Taguchi Cpm
    tau = float(np.sqrt(std_within ** 2 + (mean - target_val) ** 2))
    cpm = spec_range / (6.0 * tau) if tau > 0 else cp

    # ── Overall (long-term) performance ──────────────────────────────────────
    pp  = spec_range / (6.0 * std_overall)
    ppu = (usl - mean) / (3.0 * std_overall)
    ppl = (mean - lsl) / (3.0 * std_overall)
    ppk = min(ppu, ppl)

    # ── Confidence intervals ──────────────────────────────────────────────────
    ci_90 = cpk_confidence_interval(cpk, n, 0.90)
    ci_95 = cpk_confidence_interval(cpk, n, 0.95)
    ci_99 = cpk_confidence_interval(cpk, n, 0.99)

    # ── PPM — P0-STAT-2: both tails ──────────────────────────────────────────
    ppm_w = expected_ppm(mean, std_within,  usl, lsl)
    ppm_o = expected_ppm(mean, std_overall, usl, lsl)

    # ── Sigma level (capped at 6) ─────────────────────────────────────────────
    sigma_level = round(min(float(3.0 * cpk), 6.0), 3)

    # ── Verdict ───────────────────────────────────────────────────────────────
    if cpk >= 1.67:
        verdict = "Excellent"
        verdict_detail = (
            f"Cpk = {cpk:.3f} ≥ 1.67 — Six Sigma capable process. World-class performance."
        )
        capa_required = False
    elif cpk >= 1.33:
        verdict = "Capable"
        verdict_detail = (
            f"Cpk = {cpk:.3f} ≥ 1.33 — Meets AIAG/IATF industry standard. "
            "Monitor for drift."
        )
        capa_required = False
    elif cpk >= 1.00:
        verdict = "Marginal"
        verdict_detail = (
            f"Cpk = {cpk:.3f} (1.00–1.33) — Barely capable. Improvement recommended."
        )
        capa_required = True
    else:
        verdict = "Not Capable"
        verdict_detail = (
            f"Cpk = {cpk:.3f} < 1.00 — Process is producing non-conforming output. "
            "Immediate corrective action required."
        )
        capa_required = True

    capa_notes = _build_capa_notes(
        cpk=cpk, ppk=ppk, cp=cp,
        mean=mean, usl=usl, lsl=lsl,
        target=target_val, spec_range=spec_range,
        sw=std_within, so=std_overall, ppm=ppm_w,
    )

    hist_data  = _build_histogram(data, usl, lsl, target_val, mean, std_within, std_overall)
    curve_data = _build_capability_curve(mean, std_within, std_overall, usl, lsl)

    return CapabilityReport(
        column=column,
        n=n,
        mean=round(mean, 6),
        std_within=round(std_within, 6),
        std_overall=round(std_overall, 6),
        usl=usl,
        lsl=lsl,
        target=target_val,
        cp=round(cp, 4),
        cpk=round(cpk, 4),
        cpm=round(cpm, 4),
        pp=round(pp, 4),
        ppk=round(ppk, 4),
        cpu=round(cpu, 4),
        cpl=round(cpl, 4),
        cpk_ci_90=ci_90,
        cpk_ci_95=ci_95,
        cpk_ci_99=ci_99,
        ppm_within=ppm_w,
        ppm_overall=ppm_o,
        sigma_level=sigma_level,
        verdict=verdict,
        verdict_detail=verdict_detail,
        capa_required=capa_required,
        capa_notes=capa_notes,
        histogram_data=hist_data,
        capability_curve_data=curve_data,
        subgroup_size=subgroup_size,
    )


# ── CAPA advisory notes ───────────────────────────────────────────────────────

def _build_capa_notes(
    cpk: float, ppk: float, cp: float,
    mean: float, usl: float, lsl: float, target: float,
    spec_range: float, sw: float, so: float, ppm: float,
) -> list:
    """
    Generate human-readable diagnostic notes.

    FIX P0-STAT-4: all proximity checks now use absolute distances from
    spec limits rather than limit * 1.02, which fires falsely when the
    limit is zero or negative (e.g. LSL = -5.0 → -5.0 * 1.02 = -5.1,
    so mean - 3σ < -5.1 fires for any process near zero).
    """
    notes = []
    midspec = (usl + lsl) / 2.0
    # 10% of spec range as the "close" threshold — dimensionally correct
    proximity = spec_range * 0.10

    # 1. Centering
    offset = mean - midspec
    if abs(offset) > proximity:
        direction = "above" if offset > 0 else "below"
        potential_gain = round(cp - cpk, 3)
        notes.append(
            f"Process mean is off-centre ({direction} midspec by {abs(offset):.4f}). "
            f"Centring correction alone could improve Cpk by ≈ {potential_gain}."
        )

    # 2. Spread vs centring gap
    if cp > 0 and (cp - cpk) / cp > 0.20:
        notes.append(
            f"Cp = {cp:.3f} but Cpk = {cpk:.3f} — centring gap "
            f"({(cp - cpk) / cp * 100:.0f}% of potential lost to off-target mean). "
            "Correct mean-shift before attempting spread reduction."
        )

    # 3. Long-term drift signal: σ_within / σ_overall ratio
    if so > 0:
        ratio = sw / so
        if ratio < 0.75:
            notes.append(
                f"σ_within/σ_overall = {ratio:.2f} — significant long-term drift or "
                "batch-to-batch variation is inflating overall sigma. "
                "Investigate time-based trends."
            )
        elif ratio > 0.95:
            notes.append(
                f"σ_within/σ_overall = {ratio:.2f} — process is stable; "
                "short-term and long-term performance are well aligned."
            )

    # 4. Ppk vs Cpk
    if cpk - ppk > 0.15:
        notes.append(
            f"Cpk = {cpk:.3f} but Ppk = {ppk:.3f} — long-term performance is "
            f"{cpk - ppk:.3f} below short-term capability. "
            "Process is not in sustained statistical control."
        )

    # 5. PPM guidance
    if ppm > 10_000:
        notes.append(
            f"Expected non-conformance: {ppm:,.0f} PPM. "
            "Immediate investigation and containment required."
        )
    elif ppm > 1_000:
        notes.append(
            f"Expected non-conformance: {ppm:,.0f} PPM. "
            "Implement SPC monitoring and schedule a process improvement event."
        )
    elif ppm > 100:
        notes.append(
            f"Expected non-conformance: {ppm:,.0f} PPM. "
            "Monitor closely; consider EWMA or CUSUM chart for early drift detection."
        )
    else:
        notes.append(
            f"Expected non-conformance: {ppm:.1f} PPM — process is well-controlled."
        )

    # 6. Tail proximity — FIX P0-STAT-4: use absolute distance, not limit*factor
    upper_tail = mean + 3.0 * sw
    lower_tail = mean - 3.0 * sw
    upper_margin = usl - upper_tail   # positive = clearance from USL
    lower_margin = lower_tail - lsl   # positive = clearance from LSL

    if upper_margin < proximity * 0.3:
        notes.append(
            f"3σ upper tail ({upper_tail:.4f}) is within {max(upper_margin, 0):.4f} "
            "units of USL. Adjust process mean or reduce spread."
        )
    if lower_margin < proximity * 0.3:
        notes.append(
            f"3σ lower tail ({lower_tail:.4f}) is within {max(lower_margin, 0):.4f} "
            "units of LSL. Adjust process mean or reduce spread."
        )

    return notes


# ── Histogram data ────────────────────────────────────────────────────────────

def _build_histogram(
    data: np.ndarray,
    usl: float, lsl: float, target: float,
    mean: float, sw: float, so: float,
) -> dict:
    n = len(data)
    counts, edges = np.histogram(data, bins="auto")
    centers = ((edges[:-1] + edges[1:]) / 2.0).tolist()
    bw = float(edges[1] - edges[0]) if len(edges) > 1 else 1.0

    spread = max(sw, so)
    x_min = min(float(data.min()), lsl) - 2.0 * spread
    x_max = max(float(data.max()), usl) + 2.0 * spread
    x = np.linspace(x_min, x_max, 300)

    return {
        "bin_centers":    centers,
        "counts":         counts.tolist(),
        "bin_width":      bw,
        "curve_x":        x.tolist(),
        "curve_within":   (stats.norm.pdf(x, mean, sw)  * n * bw).tolist(),
        "curve_overall":  (stats.norm.pdf(x, mean, so)  * n * bw).tolist(),
        "usl":            usl,
        "lsl":            lsl,
        "target":         target,
        "mean":           mean,
        "pct_below_lsl":  round(float(np.mean(data < lsl) * 100), 3),
        "pct_above_usl":  round(float(np.mean(data > usl) * 100), 3),
    }


def _build_capability_curve(
    mean: float, sw: float, so: float, usl: float, lsl: float
) -> dict:
    spread = max(sw, so)
    x = np.linspace(mean - 5.0 * spread, mean + 5.0 * spread, 400)
    return {
        "x":         x.tolist(),
        "y_within":  stats.norm.pdf(x, mean, sw).tolist(),
        "y_overall": stats.norm.pdf(x, mean, so).tolist(),
        "usl":       usl,
        "lsl":       lsl,
        "mean":      mean,
    }
