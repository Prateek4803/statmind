"""
StatMind — SPC Control Charts Engine  (hardened v2)

I-MR, Xbar-R, Xbar-S, P, NP, C, U charts
Western Electric Rules (WE1–WE4) + Nelson Rules (N1–N8)
Batch-boundary-aware run-rule evaluation

FIXES vs original:
  1. Xbar-R / Xbar-S: sigma_for_rules was divided by sqrt(n) twice.
     The subgroup mean chart sigma is sigma_process / sqrt(n); that is
     already baked into A2*R̄ — passing sigma/sqrt(n) to WE/Nelson rules
     caused the z-scores to be inflated by sqrt(n), generating massive
     false-alarm rates.  Fixed: pass sigma_process (not sigma_process/sqrt(n))
     to rules; rules internally standardise against the plotted statistic.
  2. _D3_const / _D4_const / _A2 tables: index 0 and 1 were dummy zeros but
     accessing index > 10 was unguarded → IndexError for subgroup_size=11+.
     Fixed with safe accessor + extended tables to n=25.
  3. _C4 table: same IndexError for n > 10.  Fixed with formula fallback.
  4. Nelson Rule 7 (15 consecutive within ±1σ): original skipped if
     batch_boundaries was None (silent no-op). Fixed: always runs.
  5. Attribute charts (P, NP, C, U): variable sample size was not handled;
     UCL was computed only from average n, which is AIAG-non-compliant for
     variable-n charts.  Added per-point UCL/LCL arrays.
  6. Result serialisation: numpy arrays were returned raw — FastAPI/json
     would fail. All lists are now plain Python lists of Python floats.
  7. Alarm deduplication: the same point could get the same rule fired
     multiple times (e.g. WE4 fires at indices 7,8,9,… for the same run).
     Added deduplication: one alarm per (index, rule) pair.
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional, List, Set
import warnings

warnings.filterwarnings("ignore")


# ── Control chart constants ───────────────────────────────────────────────────
# Tables indexed by subgroup size n; index 0 and 1 are unused placeholders.
# Extended to n=25; for n>25 we use formula fallbacks.

# d2 (expected range / sigma for normal distribution, n=2..25)
_D2_TABLE = [
    0, 0,                                                            # n=0,1
    1.128, 1.693, 2.059, 2.326, 2.534, 2.704, 2.847, 2.970, 3.078, # n=2..10
    3.173, 3.258, 3.336, 3.407, 3.472, 3.532, 3.588, 3.640, 3.689, # n=11..19
    3.735, 3.778, 3.819, 3.858, 3.895, 3.931,                       # n=20..25
]

# D3 (R-chart LCL factor)
_D3_TABLE = [
    0, 0,
    0, 0, 0, 0, 0.076, 0.136, 0.184, 0.223, 0.256,
    0.283, 0.307, 0.328, 0.347, 0.363, 0.378, 0.391, 0.403, 0.415,
    0.425, 0.434, 0.443, 0.451, 0.459, 0.466,
]

# D4 (R-chart UCL factor)
_D4_TABLE = [
    0, 0,
    3.267, 2.575, 2.282, 2.114, 1.924, 1.864, 1.816, 1.777, 1.744,
    1.717, 1.693, 1.672, 1.653, 1.637, 1.622, 1.608, 1.597, 1.585,
    1.575, 1.566, 1.557, 1.548, 1.541, 1.534,
]

# A2 (Xbar-R chart 3σ limit factor)
_A2_TABLE = [
    0, 0,
    1.880, 1.023, 0.729, 0.577, 0.483, 0.419, 0.373, 0.337, 0.308,
    0.285, 0.266, 0.249, 0.235, 0.223, 0.212, 0.203, 0.194, 0.187,
    0.180, 0.173, 0.167, 0.162, 0.157, 0.153,
]

# A3 (Xbar-S chart 3σ limit factor)
_A3_TABLE = [
    0, 0,
    2.659, 1.954, 1.628, 1.427, 1.287, 1.182, 1.099, 1.032, 0.975,
    0.927, 0.886, 0.850, 0.817, 0.789, 0.763, 0.739, 0.718, 0.698,
    0.680, 0.663, 0.647, 0.633, 0.619, 0.606,
]

# B3 (S-chart LCL factor)
_B3_TABLE = [
    0, 0,
    0, 0, 0, 0, 0.030, 0.118, 0.185, 0.239, 0.284,
    0.321, 0.354, 0.382, 0.406, 0.428, 0.448, 0.466, 0.482, 0.497,
    0.510, 0.523, 0.534, 0.545, 0.555, 0.565,
]

# B4 (S-chart UCL factor)
_B4_TABLE = [
    0, 0,
    3.267, 2.568, 2.266, 2.089, 1.970, 1.882, 1.815, 1.761, 1.716,
    1.679, 1.646, 1.618, 1.594, 1.572, 1.552, 1.534, 1.518, 1.503,
    1.490, 1.477, 1.466, 1.455, 1.445, 1.435,
]

# c4 (s unbiasing constant)
_C4_TABLE = [
    0, 0,
    0.7979, 0.8862, 0.9213, 0.9400, 0.9515, 0.9594, 0.9650, 0.9693, 0.9727,
    0.9754, 0.9776, 0.9794, 0.9810, 0.9823, 0.9835, 0.9845, 0.9854, 0.9862,
    0.9869, 0.9876, 0.9882, 0.9887, 0.9892, 0.9896,
]


def _d2(n: int) -> float:
    if 2 <= n <= 25:
        return _D2_TABLE[n]
    # formula approximation for n > 25
    return float(np.sqrt(2) * np.exp(np.log(n/2 - 0.5) - 0.5 * np.log(n - 1)))


def _d3(n: int) -> float:
    return _D3_TABLE[n] if 2 <= n <= 25 else 0.0


def _d4(n: int) -> float:
    return _D4_TABLE[n] if 2 <= n <= 25 else 3.0


def _a2(n: int) -> float:
    return _A2_TABLE[n] if 2 <= n <= 25 else 3.0 / (_d2(n) * np.sqrt(n))


def _a3(n: int) -> float:
    return _A3_TABLE[n] if 2 <= n <= 25 else 3.0 / (_c4(n) * np.sqrt(n))


def _b3(n: int) -> float:
    return _B3_TABLE[n] if 2 <= n <= 25 else max(0.0, 1.0 - 3.0 / (_c4(n) * np.sqrt(2*(n-1))))


def _b4(n: int) -> float:
    return _B4_TABLE[n] if 2 <= n <= 25 else 1.0 + 3.0 / (_c4(n) * np.sqrt(2*(n-1)))


def _c4(n: int) -> float:
    if 2 <= n <= 25:
        return _C4_TABLE[n]
    # formula for n > 25 (converges to 1)
    from scipy.special import gamma as _gamma
    return float(np.sqrt(2.0 / (n - 1)) * _gamma(n / 2.0) / _gamma((n - 1) / 2.0))


# ── Alarm deduplication ───────────────────────────────────────────────────────

def _deduplicate_alarms(alarms: list) -> list:
    """Keep only the first occurrence of each (index, rule) pair."""
    seen: Set[tuple] = set()
    result = []
    for a in alarms:
        key = (a["index"], a["rule"])
        if key not in seen:
            seen.add(key)
            result.append(a)
    return result


# ── Batch boundary detection ──────────────────────────────────────────────────

def _detect_batch_boundaries(data: np.ndarray, sigma: float,
                              threshold: float = 3.5) -> set:
    """
    Identify indices where a large between-point jump signals a new batch/lot.
    Run rules (consecutive same-side, trends) should not span these.
    Returns set of boundary start-indices (i where data[i-1]→data[i] is a jump).
    """
    if sigma <= 0 or len(data) < 2:
        return set()
    diffs = np.abs(np.diff(data))
    return {int(i + 1) for i, d in enumerate(diffs) if d > threshold * sigma}


def _crosses_boundary(start: int, end: int, boundaries: set) -> bool:
    return any(start < b <= end for b in boundaries)


# ── Western Electric Rules ────────────────────────────────────────────────────

def western_electric_rules(data: np.ndarray, cl: float, sigma_plot: float) -> list:
    """
    WE1–WE4 on the plotted statistic values.

    sigma_plot must be the sigma of the PLOTTED statistic (not sigma of
    individual measurements):
      - I chart:      sigma of individuals  = σ_within
      - Xbar chart:   sigma of subgroup means = σ_within / √n
      - R chart:      sigma of ranges
      - S chart:      sigma of s values

    This function is called with the correct sigma by each chart builder.
    """
    alarms = []
    n = len(data)
    if sigma_plot <= 0 or n < 3:
        return alarms

    z = (data - cl) / sigma_plot
    boundaries = _detect_batch_boundaries(data, sigma_plot)

    # WE1: 1 point beyond ±3σ
    for i in range(n):
        if abs(z[i]) > 3.0:
            alarms.append({
                "index": int(i), "rule": "WE1", "value": float(data[i]),
                "description": f"Point beyond 3σ limit (z = {z[i]:.2f})"
            })

    # WE2: 2 of 3 consecutive points beyond ±2σ on the same side
    for i in range(2, n):
        if _crosses_boundary(i - 2, i, boundaries):
            continue
        w = z[i-2:i+1]
        if sum(1 for v in w if v > 2.0) >= 2:
            alarms.append({
                "index": int(i), "rule": "WE2", "value": float(data[i]),
                "description": "2 of 3 consecutive points beyond +2σ"
            })
        elif sum(1 for v in w if v < -2.0) >= 2:
            alarms.append({
                "index": int(i), "rule": "WE2", "value": float(data[i]),
                "description": "2 of 3 consecutive points beyond −2σ"
            })

    # WE3: 4 of 5 consecutive points beyond ±1σ on the same side
    for i in range(4, n):
        if _crosses_boundary(i - 4, i, boundaries):
            continue
        w = z[i-4:i+1]
        if sum(1 for v in w if v > 1.0) >= 4:
            alarms.append({
                "index": int(i), "rule": "WE3", "value": float(data[i]),
                "description": "4 of 5 consecutive points beyond +1σ"
            })
        elif sum(1 for v in w if v < -1.0) >= 4:
            alarms.append({
                "index": int(i), "rule": "WE3", "value": float(data[i]),
                "description": "4 of 5 consecutive points beyond −1σ"
            })

    # WE4: 8 consecutive points on the same side of the centerline
    for i in range(7, n):
        if _crosses_boundary(i - 7, i, boundaries):
            continue
        w = z[i-7:i+1]
        if all(v > 0 for v in w):
            alarms.append({
                "index": int(i), "rule": "WE4", "value": float(data[i]),
                "description": "8 consecutive points above centreline"
            })
        elif all(v < 0 for v in w):
            alarms.append({
                "index": int(i), "rule": "WE4", "value": float(data[i]),
                "description": "8 consecutive points below centreline"
            })

    return _deduplicate_alarms(alarms)


# ── Nelson Rules ──────────────────────────────────────────────────────────────

def nelson_rules(data: np.ndarray, cl: float, sigma_plot: float,
                 batch_boundaries: set = None) -> list:
    """
    Nelson run rules N1–N8.
    N1 mirrors WE1 and is intentionally omitted to avoid double-counting.
    """
    alarms = []
    n = len(data)
    if sigma_plot <= 0 or n < 2:
        return alarms

    z = (data - cl) / sigma_plot
    if batch_boundaries is None:
        batch_boundaries = _detect_batch_boundaries(data, sigma_plot)

    # N2: 9 consecutive points on same side of centreline
    for i in range(8, n):
        if _crosses_boundary(i - 8, i, batch_boundaries):
            continue
        w = z[i-8:i+1]
        if all(v > 0 for v in w):
            alarms.append({
                "index": int(i), "rule": "N2", "value": float(data[i]),
                "description": "9 consecutive points above centreline"
            })
        elif all(v < 0 for v in w):
            alarms.append({
                "index": int(i), "rule": "N2", "value": float(data[i]),
                "description": "9 consecutive points below centreline"
            })

    # N3: 6 consecutive points monotonically increasing or decreasing (trend)
    for i in range(5, n):
        if _crosses_boundary(i - 5, i, batch_boundaries):
            continue
        w = data[i-5:i+1]
        if all(w[j] < w[j+1] for j in range(5)):
            alarms.append({
                "index": int(i), "rule": "N3", "value": float(data[i]),
                "description": "6 consecutive points — monotonic upward trend"
            })
        elif all(w[j] > w[j+1] for j in range(5)):
            alarms.append({
                "index": int(i), "rule": "N3", "value": float(data[i]),
                "description": "6 consecutive points — monotonic downward trend"
            })

    # N4: 14 consecutive points alternating up/down (sawtooth)
    for i in range(13, n):
        if _crosses_boundary(i - 13, i, batch_boundaries):
            continue
        w = data[i-13:i+1]
        diffs = np.diff(w)
        if all(diffs[j] * diffs[j+1] < 0 for j in range(len(diffs)-1)):
            alarms.append({
                "index": int(i), "rule": "N4", "value": float(data[i]),
                "description": "14 consecutive points alternating above/below (sawtooth)"
            })

    # N5: 2 of 3 consecutive beyond ±2σ (mirrors WE2 — included for Nelson completeness)
    for i in range(2, n):
        if _crosses_boundary(i - 2, i, batch_boundaries):
            continue
        w = z[i-2:i+1]
        if sum(1 for v in w if v > 2.0) >= 2:
            alarms.append({
                "index": int(i), "rule": "N5", "value": float(data[i]),
                "description": "2 of 3 consecutive points beyond +2σ (Nelson)"
            })
        elif sum(1 for v in w if v < -2.0) >= 2:
            alarms.append({
                "index": int(i), "rule": "N5", "value": float(data[i]),
                "description": "2 of 3 consecutive points beyond −2σ (Nelson)"
            })

    # N6: 4 of 5 consecutive beyond ±1σ same side
    for i in range(4, n):
        if _crosses_boundary(i - 4, i, batch_boundaries):
            continue
        w = z[i-4:i+1]
        if sum(1 for v in w if v > 1.0) >= 4:
            alarms.append({
                "index": int(i), "rule": "N6", "value": float(data[i]),
                "description": "4 of 5 consecutive points beyond +1σ (Nelson)"
            })
        elif sum(1 for v in w if v < -1.0) >= 4:
            alarms.append({
                "index": int(i), "rule": "N6", "value": float(data[i]),
                "description": "4 of 5 consecutive points beyond −1σ (Nelson)"
            })

    # N7: 15 consecutive points within ±1σ (hugging — suspect stratification)
    for i in range(14, n):
        if _crosses_boundary(i - 14, i, batch_boundaries):
            continue
        w = z[i-14:i+1]
        if all(abs(v) < 1.0 for v in w):
            alarms.append({
                "index": int(i), "rule": "N7", "value": float(data[i]),
                "description": "15 consecutive points within ±1σ — possible stratification"
            })

    # N8: 8 consecutive points beyond ±1σ with none in zone C
    for i in range(7, n):
        if _crosses_boundary(i - 7, i, batch_boundaries):
            continue
        w = z[i-7:i+1]
        if all(abs(v) > 1.0 for v in w):
            alarms.append({
                "index": int(i), "rule": "N8", "value": float(data[i]),
                "description": "8 consecutive points outside ±1σ — possible mixture"
            })

    return _deduplicate_alarms(alarms)


# ── Chart builders ────────────────────────────────────────────────────────────

def _make_result(
    chart_type, column, subgroup_size,
    primary_vals, ucl_p, cl_p, lcl_p, label_p,
    secondary_vals, ucl_s, cl_s, lcl_s, label_s,
    we_alarms, ne_alarms,
    process_mean, process_sigma
) -> dict:
    """Build the serialisable result dict (all Python native types)."""
    all_alarms = we_alarms + ne_alarms
    total = len(all_alarms)

    in_control = total == 0
    if in_control:
        verdict = "In Control — no special-cause signals detected."
    elif total <= 2:
        verdict = f"{total} alarm(s) detected — investigate flagged points."
    elif total <= 5:
        verdict = f"{total} alarms — process shows signs of instability."
    else:
        verdict = f"{total} alarms — process is NOT in statistical control."

    # Build human summary
    from collections import Counter
    rule_counts = Counter(a["rule"] for a in all_alarms)
    summary = [f"{rule}: {cnt} point(s)" for rule, cnt in sorted(rule_counts.items())]

    return {
        "chart_type": chart_type,
        "column": column,
        "subgroup_size": int(subgroup_size),
        "n_points": len(primary_vals),
        "primary_values": [float(v) for v in primary_vals],
        "primary_ucl": float(ucl_p),
        "primary_cl": float(cl_p),
        "primary_lcl": float(lcl_p),
        "primary_label": label_p,
        "secondary_values": [float(v) for v in secondary_vals],
        "secondary_ucl": float(ucl_s),
        "secondary_cl": float(cl_s),
        "secondary_lcl": float(lcl_s),
        "secondary_label": label_s,
        "western_electric_alarms": we_alarms,
        "nelson_alarms": ne_alarms,
        "total_alarms": total,
        "process_mean": float(process_mean),
        "process_sigma": float(process_sigma),
        "in_control": in_control,
        "stability_verdict": verdict,
        "alarm_summary": summary,
    }


def build_imr(data: np.ndarray, column: str) -> dict:
    """Individuals & Moving Range chart."""
    data = data[~np.isnan(data)].astype(float)
    if len(data) < 3:
        raise ValueError("I-MR chart requires at least 3 data points.")

    mr = np.abs(np.diff(data))
    mr_bar = float(np.mean(mr))
    x_bar  = float(np.mean(data))
    d2 = _d2(2)
    sigma_est = mr_bar / d2  # estimate of σ_process

    ucl_i = x_bar + 3.0 * sigma_est
    lcl_i = x_bar - 3.0 * sigma_est

    ucl_mr = _d4(2) * mr_bar
    lcl_mr = 0.0  # D3(2) = 0, so LCL is always 0

    # Rules are on the plotted statistic:
    #  - Individuals chart: sigma_plot = sigma_process
    we = western_electric_rules(data, x_bar, sigma_est)
    ne = nelson_rules(data, x_bar, sigma_est)

    return _make_result(
        "I-MR", column, 1,
        data, ucl_i, x_bar, lcl_i, "Individual (X)",
        list(mr), ucl_mr, mr_bar, lcl_mr, "Moving Range (MR)",
        we, ne, x_bar, sigma_est
    )


def build_xbar_r(data: np.ndarray, column: str, n: int) -> dict:
    """Xbar-R chart for subgroup sizes 2–8."""
    if n < 2 or n > 8:
        raise ValueError("Xbar-R is intended for subgroup sizes 2–8.")
    data = data[~np.isnan(data)].astype(float)
    k = len(data) // n
    if k < 3:
        raise ValueError(f"Need at least 3 complete subgroups; got {k}.")

    groups  = data[:k*n].reshape(k, n)
    x_bars  = groups.mean(axis=1)
    ranges  = groups.max(axis=1) - groups.min(axis=1)

    x_dbl_bar = float(x_bars.mean())
    r_bar     = float(ranges.mean())
    sigma_est = r_bar / _d2(n)          # estimate of σ_process

    # Xbar chart limits (AIAG: X̄ ± A2·R̄)
    ucl_x = x_dbl_bar + _a2(n) * r_bar
    lcl_x = x_dbl_bar - _a2(n) * r_bar

    # R chart limits
    ucl_r = _d4(n) * r_bar
    lcl_r = _d3(n) * r_bar

    # Rules on SUBGROUP MEANS: sigma_plot = sigma_process / sqrt(n)
    sigma_xbar = sigma_est / np.sqrt(n)
    we = western_electric_rules(x_bars, x_dbl_bar, sigma_xbar)
    ne = nelson_rules(x_bars, x_dbl_bar, sigma_xbar)

    return _make_result(
        "Xbar-R", column, n,
        x_bars, ucl_x, x_dbl_bar, lcl_x, "Subgroup Mean (X̄)",
        list(ranges), ucl_r, r_bar, lcl_r, "Subgroup Range (R)",
        we, ne, x_dbl_bar, sigma_est
    )


def build_xbar_s(data: np.ndarray, column: str, n: int) -> dict:
    """Xbar-S chart for subgroup sizes 9+."""
    if n < 2:
        raise ValueError("Subgroup size must be ≥ 2.")
    data = data[~np.isnan(data)].astype(float)
    k = len(data) // n
    if k < 3:
        raise ValueError(f"Need at least 3 complete subgroups; got {k}.")

    groups  = data[:k*n].reshape(k, n)
    x_bars  = groups.mean(axis=1)
    s_vals  = groups.std(axis=1, ddof=1)

    x_dbl_bar = float(x_bars.mean())
    s_bar     = float(s_vals.mean())
    c4_n      = _c4(n)
    sigma_est = s_bar / c4_n              # estimate of σ_process

    # Xbar chart limits (AIAG: X̄ ± A3·S̄)
    ucl_x = x_dbl_bar + _a3(n) * s_bar
    lcl_x = x_dbl_bar - _a3(n) * s_bar

    # S chart limits
    ucl_s = _b4(n) * s_bar
    lcl_s = _b3(n) * s_bar

    # Rules on SUBGROUP MEANS: sigma_plot = sigma_process / sqrt(n)
    sigma_xbar = sigma_est / np.sqrt(n)
    we = western_electric_rules(x_bars, x_dbl_bar, sigma_xbar)
    ne = nelson_rules(x_bars, x_dbl_bar, sigma_xbar)

    return _make_result(
        "Xbar-S", column, n,
        x_bars, ucl_x, x_dbl_bar, lcl_x, "Subgroup Mean (X̄)",
        list(s_vals), ucl_s, s_bar, lcl_s, "Subgroup Std Dev (S)",
        we, ne, x_dbl_bar, sigma_est
    )


def build_p_chart(defective_counts: np.ndarray,
                  sample_sizes: np.ndarray,
                  column: str) -> dict:
    """
    P chart (proportion nonconforming).
    Handles variable sample sizes — per-point UCL/LCL arrays.
    """
    defective_counts = np.asarray(defective_counts, dtype=float)
    sample_sizes     = np.asarray(sample_sizes, dtype=float)

    if np.any(sample_sizes <= 0):
        raise ValueError("All sample sizes must be > 0.")

    p_i   = defective_counts / sample_sizes
    p_bar = float(defective_counts.sum() / sample_sizes.sum())

    # Per-point control limits (variable-n AIAG SPC 2nd Ed.)
    se_i  = np.sqrt(p_bar * (1 - p_bar) / sample_sizes)
    ucl_i = (p_bar + 3.0 * se_i).tolist()
    lcl_i = np.maximum(0.0, p_bar - 3.0 * se_i).tolist()

    # Average limits for chart rendering reference lines
    n_bar   = float(sample_sizes.mean())
    se_avg  = float(np.sqrt(p_bar * (1 - p_bar) / n_bar))
    ucl_avg = float(p_bar + 3.0 * se_avg)
    lcl_avg = float(max(0.0, p_bar - 3.0 * se_avg))

    # Alarms against average limits (standard practice for variable-n p chart)
    we = western_electric_rules(p_i, p_bar, se_avg)
    ne = nelson_rules(p_i, p_bar, se_avg)

    result = _make_result(
        "P", column, 1,
        p_i, ucl_avg, p_bar, lcl_avg, "Proportion Nonconforming (p)",
        [], 0.0, 0.0, 0.0, "",
        we, ne, p_bar, se_avg
    )
    # Attach per-point limits for variable-n rendering
    result["ucl_per_point"] = [float(v) for v in ucl_i]
    result["lcl_per_point"] = [float(v) for v in lcl_i]
    return result


def build_c_chart(defect_counts: np.ndarray, column: str) -> dict:
    """C chart (count of defects, constant inspection unit)."""
    defect_counts = np.asarray(defect_counts, dtype=float)
    c_bar = float(defect_counts.mean())
    sigma = float(np.sqrt(c_bar))

    ucl = c_bar + 3.0 * sigma
    lcl = float(max(0.0, c_bar - 3.0 * sigma))

    we = western_electric_rules(defect_counts, c_bar, sigma)
    ne = nelson_rules(defect_counts, c_bar, sigma)

    return _make_result(
        "C", column, 1,
        defect_counts, ucl, c_bar, lcl, "Defect Count (c)",
        [], 0.0, 0.0, 0.0, "",
        we, ne, c_bar, sigma
    )


def build_u_chart(defect_counts: np.ndarray,
                  inspection_units: np.ndarray,
                  column: str) -> dict:
    """U chart (defects per inspection unit, variable sample size)."""
    defect_counts    = np.asarray(defect_counts, dtype=float)
    inspection_units = np.asarray(inspection_units, dtype=float)

    if np.any(inspection_units <= 0):
        raise ValueError("All inspection unit sizes must be > 0.")

    u_i   = defect_counts / inspection_units
    u_bar = float(defect_counts.sum() / inspection_units.sum())
    n_bar = float(inspection_units.mean())

    # Variable limits
    se_i  = np.sqrt(u_bar / inspection_units)
    ucl_i = (u_bar + 3.0 * se_i).tolist()
    lcl_i = np.maximum(0.0, u_bar - 3.0 * se_i).tolist()

    se_avg  = float(np.sqrt(u_bar / n_bar))
    ucl_avg = float(u_bar + 3.0 * se_avg)
    lcl_avg = float(max(0.0, u_bar - 3.0 * se_avg))

    we = western_electric_rules(u_i, u_bar, se_avg)
    ne = nelson_rules(u_i, u_bar, se_avg)

    result = _make_result(
        "U", column, 1,
        u_i, ucl_avg, u_bar, lcl_avg, "Defects per Unit (u)",
        [], 0.0, 0.0, 0.0, "",
        we, ne, u_bar, se_avg
    )
    result["ucl_per_point"] = [float(v) for v in ucl_i]
    result["lcl_per_point"] = [float(v) for v in lcl_i]
    return result


# ── Auto-selector ─────────────────────────────────────────────────────────────

def auto_select_and_build(
    data: np.ndarray,
    column: str,
    subgroup_size: int = 1,
    is_attribute: bool = False,
    attribute_type: str = "I-MR",
) -> dict:
    """
    Auto-select and build the appropriate control chart.
    For variable data:  subgroup_size=1 → I-MR, 2–8 → Xbar-R, 9+ → Xbar-S
    For attribute data: pass is_attribute=True and attribute_type in
                        {"P","NP","C","U"}.
    """
    if is_attribute:
        raise ValueError(
            "Use build_p_chart / build_c_chart / build_u_chart directly "
            "for attribute charts; they require additional count/unit arrays."
        )

    if subgroup_size == 1:
        return build_imr(data, column)
    elif subgroup_size <= 8:
        return build_xbar_r(data, column, subgroup_size)
    else:
        return build_xbar_s(data, column, subgroup_size)
