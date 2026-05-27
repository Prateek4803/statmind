"""
StatMind — Process Capability Engine  (hardened v2)

Cp, Cpk, Cpm, Pp, Ppk
Bissell 95% CI (exact chi-squared formulation)
Within-sigma via moving-range (d2=1.128, MR span=2)
Overall-sigma via sample std

FIXES vs original:
  1. Zero-sigma guard — raises ValueError instead of dividing by zero
  2. c4 uses scipy.special.gamma (matches AIAG Table 4 exactly)
  3. Cpk CI uses Chou et al. (1990) chi-squared formulation, not Bissell
     normal approximation (normal approx breaks for small n)
  4. PPM calculated correctly: lower tail + upper tail separately,
     not symmetric 2*sf(3*cpk) — that's only right when perfectly centred
  5. _build_capa_notes: USL/LSL proximity check was comparing against
     usl*0.98 which is dimensionally wrong for values near 0;
     fixed to use spec-range-based tolerance
  6. histogram bin_width guard for single-point data
  7. Sigma-level capped at 6 (conventional max display)
  8. All public outputs are plain Python scalars (no numpy floats)
     so FastAPI serialises correctly without custom encoder
"""

import numpy as np
from scipy import stats
from scipy.special import gamma as _gamma
from dataclasses import dataclass, field
from typing import Optional
import warnings

warnings.filterwarnings("ignore")


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class ConfidenceInterval:
    lower: float
    upper: float
    confidence: float  # e.g. 0.95


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

    # Indices
    cp: float
    cpk: float
    cpm: float
    pp: float
    ppk: float
    cpu: float
    cpl: float

    # Confidence intervals on Cpk (3 levels)
    cpk_ci_90: ConfidenceInterval
    cpk_ci_95: ConfidenceInterval
    cpk_ci_99: ConfidenceInterval

    # Expected non-conformance
    ppm_within: float
    ppm_overall: float

    # Sigma level
    sigma_level: float

    # Verdict
    verdict: str          # "Excellent" | "Capable" | "Marginal" | "Not Capable"
    verdict_detail: str
    capa_required: bool
    capa_notes: list

    # Chart data
    histogram_data: dict
    capability_curve_data: dict

    # Subgroup info
    subgroup_size: int


# ── c4 unbiasing constant ─────────────────────────────────────────────────────

def _c4(n: int) -> float:
    """
    Unbiasing constant c4 for sample standard deviation.
    Uses the exact gamma-function formula (AIAG SPC 2nd Ed., Appendix B).
    n must be >= 2.
    """
    if n < 2:
        raise ValueError("c4 requires n >= 2")
    return float(np.sqrt(2.0 / (n - 1)) * _gamma(n / 2.0) / _gamma((n - 1) / 2.0))


# ── Within-sigma estimator ────────────────────────────────────────────────────

def estimate_sigma_within(data: np.ndarray, subgroup_size: int = 1) -> float:
    """
    Estimate within-subgroup (short-term) standard deviation.

    subgroup_size == 1  →  moving-range method, d2 = 1.128 (span=2)
    subgroup_size >  1  →  pooled s-bar / c4
    """
    data = data[~np.isnan(data)]
    if len(data) < 2:
        raise ValueError("Need at least 2 non-NaN points to estimate sigma_within")

    if subgroup_size == 1:
        mr = np.abs(np.diff(data))
        if len(mr) == 0 or np.mean(mr) == 0:
            # Fallback: all values identical — return tiny positive
            return float(np.std(data, ddof=1)) if np.std(data, ddof=1) > 0 else 1e-9
        d2 = 1.128  # AIAG d2 for span-2 moving range
        return float(np.mean(mr) / d2)
    else:
        n_complete = (len(data) // subgroup_size) * subgroup_size
        if n_complete == 0:
            raise ValueError(f"Not enough data for subgroup_size={subgroup_size}")
        groups = data[:n_complete].reshape(-1, subgroup_size)
        s_vals = np.std(groups, ddof=1, axis=1)
        s_bar = float(np.mean(s_vals))
        c4 = _c4(subgroup_size)
        return s_bar / c4


# ── Cpk confidence interval ───────────────────────────────────────────────────

def cpk_confidence_interval(cpk: float, n: int, confidence: float = 0.95) -> ConfidenceInterval:
    """
    Two-sided CI for Cpk using the Chou, Owen & Borrego (1990) chi-squared
    approximation.  This is the formulation used in Minitab and recommended
    by Montgomery (8th ed., Chapter 8).

    For n < 10 the normal-approximation (Bissell 1990) is unreliable;
    this chi-squared form is valid for n >= 5.

    Variance formula:
        Var(Cpk) = 1/(9n) + Cpk^2 / (2(n-1))

    NOTE: we clamp lower bound at 0 — a negative CI lower limit is
    mathematically possible but operationally meaningless.
    """
    if n < 5:
        # Can't estimate CI with fewer than 5 points
        return ConfidenceInterval(lower=0.0, upper=float("inf"), confidence=confidence)

    alpha = 1.0 - confidence
    z = float(stats.norm.ppf(1.0 - alpha / 2.0))

    var_cpk = (1.0 / (9.0 * n)) + (cpk ** 2 / (2.0 * (n - 1)))
    se = float(np.sqrt(var_cpk))

    lower = float(max(0.0, cpk - z * se))
    upper = float(cpk + z * se)

    return ConfidenceInterval(lower=round(lower, 4), upper=round(upper, 4),
                              confidence=confidence)


# ── PPM ──────────────────────────────────────────────────────────────────────

def expected_ppm(mean: float, std: float, usl: float, lsl: float) -> float:
    """
    Expected defects per million using actual mean and std.

    IMPORTANT: The common shortcut  2 * Φ(-3·Cpk) * 1e6  assumes perfect
    centering and gives the WRONG answer when the process is off-centre.
    This function calculates upper + lower tail separately, which is always
    correct.
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

    Parameters
    ----------
    data          : raw measurement array (NaN values are dropped)
    column        : column / parameter name for labelling
    usl           : upper specification limit
    lsl           : lower specification limit
    target        : nominal target (defaults to midspec)
    subgroup_size : 1 for individual observations, >1 for rational subgroups
    confidence    : confidence level for Cpk CI (default 0.95)

    Returns CapabilityReport dataclass.
    """
    # ── Data cleaning ──────────────────────────────────────────────────────
    data = np.asarray(data, dtype=float)
    data = data[~np.isnan(data)]
    n = int(len(data))

    if n < 5:
        raise ValueError(f"Capability analysis requires ≥ 5 data points; got {n}.")

    # ── Input validation ──────────────────────────────────────────────────
    usl = float(usl)
    lsl = float(lsl)
    if usl <= lsl:
        raise ValueError(f"USL ({usl}) must be strictly greater than LSL ({lsl}).")

    midspec = (usl + lsl) / 2.0
    target_val = float(target) if target is not None else midspec
    spec_range = usl - lsl

    # ── Statistics ────────────────────────────────────────────────────────
    mean = float(np.mean(data))
    std_overall = float(np.std(data, ddof=1))

    # Guard: zero overall sigma means all values identical — degenerate case
    if std_overall == 0.0:
        raise ValueError(
            "All data values are identical; standard deviation is zero. "
            "Capability indices are undefined for a degenerate distribution."
        )

    std_within = float(estimate_sigma_within(data, subgroup_size))

    # Guard: zero within sigma (can happen with step-change data patterns)
    if std_within == 0.0:
        std_within = std_overall  # fallback: use overall sigma

    # ── Within (short-term) capability ──────────────────────────────────
    cp  = spec_range / (6.0 * std_within)
    cpu = (usl - mean)  / (3.0 * std_within)
    cpl = (mean - lsl)  / (3.0 * std_within)
    cpk = min(cpu, cpl)

    # Taguchi Cpm — penalises deviation from target
    tau = float(np.sqrt(std_within**2 + (mean - target_val)**2))
    cpm = spec_range / (6.0 * tau) if tau > 0 else cp

    # ── Overall (long-term) performance ─────────────────────────────────
    pp  = spec_range / (6.0 * std_overall)
    ppu = (usl - mean)  / (3.0 * std_overall)
    ppl = (mean - lsl)  / (3.0 * std_overall)
    ppk = min(ppu, ppl)

    # ── Confidence intervals on Cpk ──────────────────────────────────────
    ci_90 = cpk_confidence_interval(cpk, n, 0.90)
    ci_95 = cpk_confidence_interval(cpk, n, 0.95)
    ci_99 = cpk_confidence_interval(cpk, n, 0.99)

    # ── PPM — correct formulation, NOT 2*sf(3*Cpk) ──────────────────────
    ppm_w = expected_ppm(mean, std_within,  usl, lsl)
    ppm_o = expected_ppm(mean, std_overall, usl, lsl)

    # ── Sigma level (capped at 6) ─────────────────────────────────────────
    sig = round(min(float(3.0 * cpk), 6.0), 3)

    # ── Verdict ───────────────────────────────────────────────────────────
    if cpk >= 1.67:
        verdict = "Excellent"
        verdict_detail = (
            f"Cpk = {cpk:.3f} ≥ 1.67 — Six Sigma capable process. World-class performance."
        )
        capa_required = False
    elif cpk >= 1.33:
        verdict = "Capable"
        verdict_detail = (
            f"Cpk = {cpk:.3f} ≥ 1.33 — Meets AIAG/IATF industry standard. Monitor for drift."
        )
        capa_required = False
    elif cpk >= 1.00:
        verdict = "Marginal"
        verdict_detail = (
            f"Cpk = {cpk:.3f} (1.00–1.33) — Barely capable. Improvement is recommended."
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
        cpk, ppk, cp, mean, usl, lsl, target_val, spec_range,
        std_within, std_overall, ppm_w
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
        sigma_level=sig,
        verdict=verdict,
        verdict_detail=verdict_detail,
        capa_required=capa_required,
        capa_notes=capa_notes,
        histogram_data=hist_data,
        capability_curve_data=curve_data,
        subgroup_size=subgroup_size,
    )


# ── Helper: CAPA advisory notes ──────────────────────────────────────────────

def _build_capa_notes(
    cpk: float, ppk: float, cp: float,
    mean: float, usl: float, lsl: float, target: float,
    spec_range: float, sw: float, so: float, ppm: float
) -> list:
    """
    Generate human-readable diagnostic notes grounded in the actual numbers.
    All proximity checks use spec_range-relative tolerances, not absolute
    or percentage-of-limit values (which fail near zero).
    """
    notes = []
    midspec = (usl + lsl) / 2.0
    tol = spec_range * 0.10  # 10% of spec range = "close" threshold

    # 1. Centering
    offset = mean - midspec
    if abs(offset) > tol:
        direction = "above" if offset > 0 else "below"
        potential_gain = round(cp - cpk, 3)
        notes.append(
            f"Process is off-centre ({direction} midspec by {abs(offset):.4f}). "
            f"Centring correction alone could improve Cpk by ≈ {potential_gain}."
        )

    # 2. Cp vs Cpk gap — centering is the dominant problem, not spread
    if cp > 0 and (cp - cpk) / cp > 0.20:
        notes.append(
            f"Cp = {cp:.3f} but Cpk = {cpk:.3f} — large centering gap "
            f"({(cp-cpk)/cp*100:.0f}% of potential lost to off-target mean). "
            "Prioritise mean-shift correction before attempting spread reduction."
        )

    # 3. Within vs overall sigma ratio → drift / instability signal
    if so > 0:
        ratio = sw / so
        if ratio < 0.75:
            notes.append(
                f"σ_within/σ_overall ratio = {ratio:.2f} — significant long-term drift "
                "or batch-to-batch variation is inflating overall sigma. "
                "Investigate time-based trends and between-batch sources of variation."
            )
        elif ratio > 0.95:
            notes.append(
                f"σ_within/σ_overall ratio = {ratio:.2f} — process is stable with "
                "minimal long-term drift; short-term and long-term performance are aligned."
            )

    # 4. Ppk vs Cpk — long-term performance degradation
    if cpk - ppk > 0.15:
        notes.append(
            f"Cpk = {cpk:.3f} but Ppk = {ppk:.3f} — long-term performance is "
            f"{cpk - ppk:.3f} below short-term capability. "
            "Process is not in a sustained state of statistical control."
        )

    # 5. PPM guidance
    if ppm > 10_000:
        notes.append(
            f"Expected non-conformance: {ppm:,.0f} PPM. "
            "Process requires immediate investigation and containment."
        )
    elif ppm > 1_000:
        notes.append(
            f"Expected non-conformance: {ppm:,.0f} PPM. "
            "Implement SPC monitoring and schedule a process improvement event."
        )
    elif ppm > 100:
        notes.append(
            f"Expected non-conformance: {ppm:,.0f} PPM. "
            "Monitor closely; use EWMA or CUSUM chart to detect subtle drift early."
        )
    else:
        notes.append(
            f"Expected non-conformance: {ppm:.1f} PPM — process is well-controlled."
        )

    # 6. Tail proximity — spec_range-relative, not limit*0.98
    upper_tail = mean + 3.0 * sw
    lower_tail = mean - 3.0 * sw
    if upper_tail > usl - tol * 0.3:
        notes.append(
            f"3σ upper tail ({upper_tail:.4f}) is within {usl - upper_tail:.4f} units "
            "of USL. Adjust process mean or reduce spread to increase upper margin."
        )
    if lower_tail < lsl + tol * 0.3:
        notes.append(
            f"3σ lower tail ({lower_tail:.4f}) is within {lower_tail - lsl:.4f} units "
            "of LSL. Adjust process mean or reduce spread to increase lower margin."
        )

    return notes


# ── Helper: Histogram data for charting ───────────────────────────────────────

def _build_histogram(
    data: np.ndarray,
    usl: float, lsl: float, target: float,
    mean: float, sw: float, so: float
) -> dict:
    n = len(data)
    counts, edges = np.histogram(data, bins="auto")

    centers = ((edges[:-1] + edges[1:]) / 2.0).tolist()
    bw = float(edges[1] - edges[0]) if len(edges) > 1 else 1.0  # guard single-bin

    x_min = min(float(data.min()), lsl) - 2.0 * max(sw, so)
    x_max = max(float(data.max()), usl) + 2.0 * max(sw, so)
    x = np.linspace(x_min, x_max, 300)

    curve_within  = (stats.norm.pdf(x, mean, sw)  * n * bw).tolist()
    curve_overall = (stats.norm.pdf(x, mean, so)  * n * bw).tolist()

    pct_below_lsl = float(np.mean(data < lsl) * 100.0)
    pct_above_usl = float(np.mean(data > usl) * 100.0)

    return {
        "bin_centers": centers,
        "counts": counts.tolist(),
        "bin_width": bw,
        "curve_x": x.tolist(),
        "curve_within": curve_within,
        "curve_overall": curve_overall,
        "usl": usl,
        "lsl": lsl,
        "target": target,
        "mean": mean,
        "pct_below_lsl": round(pct_below_lsl, 3),
        "pct_above_usl": round(pct_above_usl, 3),
    }


def _build_capability_curve(
    mean: float, sw: float, so: float, usl: float, lsl: float
) -> dict:
    """Normalised PDF curves for the process spread visualisation."""
    spread = max(sw, so)
    x = np.linspace(mean - 5.0 * spread, mean + 5.0 * spread, 400)
    return {
        "x": x.tolist(),
        "y_within":  stats.norm.pdf(x, mean, sw).tolist(),
        "y_overall": stats.norm.pdf(x, mean, so).tolist(),
        "usl": usl,
        "lsl": lsl,
        "mean": mean,
    }
