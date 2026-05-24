"""
StatMind — Session 2: Process Capability Engine
Cp, Cpk, Pp, Ppk, confidence intervals, within vs overall variation
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


def _welford_std(data: np.ndarray, ddof: int = 1) -> float:
    """
    Welford's one-pass online algorithm for sample standard deviation.
    Numerically stable for data with very small values (e.g. 1e-7) where
    the naive two-pass formula suffers catastrophic cancellation.
    Reference: Welford (1962), Knuth TAOCP Vol.2.
    """
    n = 0
    mean = 0.0
    M2 = 0.0
    for x in data:
        n += 1
        delta = x - mean
        mean += delta / n
        delta2 = x - mean
        M2 += delta * delta2
    if n - ddof <= 0:
        return 0.0
    return float(np.sqrt(M2 / (n - ddof)))


@dataclass
class CapabilityIndices:
    cp: float
    cpk: float
    cpm: float        # Taguchi index
    pp: float
    ppk: float
    # Components
    cpu: float        # upper capability
    cpl: float        # lower capability
    # Variation
    sigma_within: float
    sigma_overall: float
    # Spec limits used
    usl: float
    lsl: float
    target: Optional[float]
    mean: float
    n: int


@dataclass
class ConfidenceInterval:
    lower: float
    upper: float
    confidence: float   # e.g. 0.95


@dataclass
class CapabilityReport:
    column: str
    n: int
    mean: float
    std_within: float
    std_overall: float
    usl: float
    lsl: float
    target: Optional[float]
    # Indices
    cp: float
    cpk: float
    cpm: float
    pp: float
    ppk: float
    cpu: float
    cpl: float
    # CI on Cpk
    cpk_ci_90: ConfidenceInterval
    cpk_ci_95: ConfidenceInterval
    cpk_ci_99: ConfidenceInterval
    # Expected ppm
    ppm_within: float
    ppm_overall: float
    # Sigma level
    sigma_level: float
    # Verdict
    verdict: str           # "Capable", "Marginal", "Not Capable"
    verdict_detail: str
    capa_required: bool
    capa_notes: list
    # Chart data
    histogram_data: dict
    capability_curve_data: dict
    # Subgroup info
    subgroup_size: int


def estimate_sigma_within(data: np.ndarray, subgroup_size: int = 1) -> float:
    """
    Estimate within-subgroup (short-term) standard deviation.
    For individual data (subgroup_size=1): use moving range method (d2=1.128).
    For subgroups: use pooled standard deviation.
    """
    if subgroup_size == 1:
        # Moving range method — standard for I-MR charts
        moving_ranges = np.abs(np.diff(data))
        mr_bar = np.mean(moving_ranges)
        d2 = 1.128  # control chart constant for n=2 (moving range of 2)
        return mr_bar / d2
    else:
        # Reshape into subgroups and pool
        n_complete = (len(data) // subgroup_size) * subgroup_size
        groups = data[:n_complete].reshape(-1, subgroup_size)
        s_values = np.std(groups, ddof=1, axis=1)
        s_bar = np.mean(s_values)
        # c4 constant for unbiasing
        c4 = _c4(subgroup_size)
        return s_bar / c4


def _c4(n: int) -> float:
    """Unbiasing constant c4 for standard deviation."""
    from scipy.special import gamma
    return (np.sqrt(2 / (n - 1)) * gamma(n / 2) / gamma((n - 1) / 2))


def cpk_confidence_interval(cpk: float, n: int, confidence: float = 0.95) -> ConfidenceInterval:
    """
    Approximate confidence interval for Cpk using the chi-squared approximation
    (Bissell 1990 / Chou et al. 1990).
    """
    alpha = 1 - confidence
    z = stats.norm.ppf(1 - alpha / 2)
    # Variance of Cpk estimate
    var_cpk = (1 / (9 * n)) + (cpk**2 / (2 * (n - 1)))
    se = np.sqrt(var_cpk)
    lower = cpk - z * se
    upper = cpk + z * se
    return ConfidenceInterval(
        lower=round(max(0, lower), 4),
        upper=round(upper, 4),
        confidence=confidence
    )


def expected_ppm(cpk: float) -> float:
    """Expected defects per million (one-sided, based on Cpk)."""
    z = 3 * cpk
    ppm = 2 * stats.norm.sf(z) * 1_000_000
    return round(float(ppm), 2)


def sigma_level(cpk: float) -> float:
    """Convert Cpk to sigma level."""
    return round(float(3 * cpk), 3)


def analyze_capability(
    data: np.ndarray,
    column: str,
    usl: float,
    lsl: float,
    target: Optional[float] = None,
    subgroup_size: int = 1,
    confidence: float = 0.95
) -> CapabilityReport:
    data = data[~np.isnan(data)].astype(float)
    n = len(data)

    if n < 5:
        raise ValueError(f"Need at least 5 data points, got {n}")
    if usl <= lsl:
        raise ValueError(f"USL ({usl}) must be greater than LSL ({lsl})")
    mean = float(np.mean(data))
    # Use Welford's algorithm for numerically stable variance
    # (prevents catastrophic cancellation on very small-magnitude data)
    std_overall = _welford_std(data, ddof=1)
    std_within = float(estimate_sigma_within(data, subgroup_size))

    # Sanity check: mean wildly outside spec suggests unit mismatch
    spec_width = usl - lsl
    if mean > usl + 10 * spec_width or mean < lsl - 10 * spec_width:
        raise ValueError(
            f"Process mean ({mean:.4f}) is far outside spec limits "
            f"[LSL={lsl}, USL={usl}]. Check that spec limits match your data units."
        )

    if std_within == 0:
        raise ValueError("All data values are identical — cannot compute capability (zero variation)")
    if std_overall == 0:
        std_overall = std_within  # fallback: use within sigma

    if target is None:
        target_val = (usl + lsl) / 2
    else:
        target_val = float(target)

    spec_range = usl - lsl

    # --- Within (short-term) indices ---
    cp  = spec_range / (6 * std_within)
    cpu = (usl - mean) / (3 * std_within)
    cpl = (mean - lsl) / (3 * std_within)
    cpk = min(cpu, cpl)

    # Taguchi Cpm (accounts for deviation from target)
    tau = np.sqrt(std_within**2 + (mean - target_val)**2)
    cpm = spec_range / (6 * tau)

    # --- Overall (long-term) indices ---
    pp  = spec_range / (6 * std_overall)
    ppu = (usl - mean) / (3 * std_overall)
    ppl = (mean - lsl) / (3 * std_overall)
    ppk = min(ppu, ppl)

    # --- Confidence intervals on Cpk ---
    ci_90 = cpk_confidence_interval(cpk, n, 0.90)
    ci_95 = cpk_confidence_interval(cpk, n, 0.95)
    ci_99 = cpk_confidence_interval(cpk, n, 0.99)

    # --- PPM & Sigma ---
    ppm_w = expected_ppm(cpk)
    ppm_o = expected_ppm(ppk)
    sig = sigma_level(cpk)

    # --- Verdict ---
    if cpk >= 1.67:
        verdict = "Excellent"
        verdict_detail = f"Cpk={cpk:.3f} ≥ 1.67 — Six Sigma capable. World-class process."
        capa_required = False
    elif cpk >= 1.33:
        verdict = "Capable"
        verdict_detail = f"Cpk={cpk:.3f} ≥ 1.33 — Meets industry standard. Monitor for drift."
        capa_required = False
    elif cpk >= 1.00:
        verdict = "Marginal"
        verdict_detail = f"Cpk={cpk:.3f} between 1.00–1.33 — Barely capable. Improvement recommended."
        capa_required = True
    else:
        verdict = "Not Capable"
        verdict_detail = f"Cpk={cpk:.3f} < 1.00 — Process is producing defects. Immediate action required."
        capa_required = True

    capa_notes = _build_capa_notes(cpk, ppk, cp, mean, usl, lsl, target_val, std_within, std_overall)

    # Add non-normal data flag to notes if distribution appears skewed
    try:
        from scipy.stats import shapiro
        _, sw_p = shapiro(data[:min(len(data), 5000)])
        if sw_p < 0.05:
            capa_notes.insert(0,
                f"⚠ Non-normal distribution detected (Shapiro-Wilk p={sw_p:.4f} < 0.05). "
                "Cp/Cpk assume normality and may be unreliable. "
                "Consider running Non-Normal Capability (Johnson SU/SB) for accurate results."
            )
    except Exception:
        pass

    hist_data = _build_capability_histogram(data, usl, lsl, target_val, mean, std_within, std_overall)
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
        sigma_level=sig,
        verdict=verdict,
        verdict_detail=verdict_detail,
        capa_required=capa_required,
        capa_notes=capa_notes,
        histogram_data=hist_data,
        capability_curve_data=curve_data,
        subgroup_size=subgroup_size,
    )


def _build_capa_notes(cpk, ppk, cp, mean, usl, lsl, target, sw, so):
    notes = []
    midspec = (usl + lsl) / 2

    # Centering check
    if abs(mean - midspec) > (usl - lsl) * 0.1:
        direction = "above" if mean > midspec else "below"
        notes.append(f"Process is off-center ({direction} midspec by {abs(mean-midspec):.4f}). Centering adjustment could raise Cpk by ~{(cp-cpk):.3f}.")

    # Within vs overall spread
    ratio = sw / so if so > 0 else 1
    if ratio < 0.75:
        notes.append(f"Large within/overall sigma ratio ({ratio:.2f}) suggests significant long-term drift or batch-to-batch variation.")
    elif ratio > 0.95:
        notes.append(f"Within and overall sigma are similar ({ratio:.2f}) — process is stable with minimal drift.")

    # Cpk vs Cp gap
    if cp > 0 and (cp - cpk) / cp > 0.2:
        notes.append(f"Cp={cp:.3f} but Cpk={cpk:.3f} — large gap indicates centering is the primary issue, not spread.")

    # PPM guidance
    ppm = expected_ppm(cpk)
    if ppm > 1000:
        notes.append(f"Expected {ppm:,.0f} PPM defects — investigate assignable causes and tighten process control.")
    elif ppm > 100:
        notes.append(f"Expected {ppm:,.0f} PPM — monitor closely, consider SPC chart to detect drift early.")
    else:
        notes.append(f"Expected {ppm:.1f} PPM — process well under control.")

    # Spec limit proximity
    if cpk < 1.33:
        if mean + 3*sw > usl * 0.98:
            notes.append("Process mean is dangerously close to USL. Consider recipe adjustment or tighter APC setpoint.")
        if mean - 3*sw < lsl * 1.02:
            notes.append("Process mean is dangerously close to LSL. Review process baseline and tool conditioning.")

    return notes


def _build_capability_histogram(data, usl, lsl, target, mean, sw, so):
    # Welford std already passed in as sw/so — histogram bins using numpy is fine
    counts, edges = np.histogram(data, bins='auto')
    centers = ((edges[:-1] + edges[1:]) / 2).tolist()
    bw = float(edges[1] - edges[0])
    n = len(data)

    x_min = min(data.min(), lsl) - 2 * sw
    x_max = max(data.max(), usl) + 2 * sw
    x = np.linspace(x_min, x_max, 300)

    curve_within  = stats.norm.pdf(x, mean, sw)  * n * bw
    curve_overall = stats.norm.pdf(x, mean, so) * n * bw

    # Spec limit markers
    pct_below_lsl = float(np.mean(data < lsl) * 100)
    pct_above_usl = float(np.mean(data > usl) * 100)

    return {
        "bin_centers": centers,
        "counts": counts.tolist(),
        "bin_width": bw,
        "curve_x": x.tolist(),
        "curve_within": curve_within.tolist(),
        "curve_overall": curve_overall.tolist(),
        "usl": usl,
        "lsl": lsl,
        "target": target,
        "mean": mean,
        "pct_below_lsl": round(pct_below_lsl, 3),
        "pct_above_usl": round(pct_above_usl, 3),
    }


def _build_capability_curve(mean, sw, so, usl, lsl):
    """Data for the sigma-level gauge / process spread visualization."""
    spec_range = usl - lsl
    x = np.linspace(mean - 5*max(sw, so), mean + 5*max(sw, so), 400)
    y_within  = stats.norm.pdf(x, mean, sw).tolist()
    y_overall = stats.norm.pdf(x, mean, so).tolist()
    return {
        "x": x.tolist(),
        "y_within": y_within,
        "y_overall": y_overall,
        "usl": usl,
        "lsl": lsl,
        "mean": mean,
    }
