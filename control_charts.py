"""
StatMind — Session 3: Control Charts Engine
Auto-selects: I-MR, Xbar-R, Xbar-S, P, NP, C, U
Western Electric Rules + Nelson Rules detection
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings("ignore")

# ── Control chart constants ───────────────────────────────────────────────────
# d2, d3, A2, A3, B3, B4, D3, D4 indexed by subgroup size n (index = n)
_D2 = [0, 0, 1.128, 1.693, 2.059, 2.326, 2.534, 2.704, 2.847, 2.970, 3.078]
_D3_const = [0, 0, 0, 0, 0, 0, 0.076, 0.136, 0.184, 0.223, 0.256]
_D4_const = [0, 0, 3.267, 2.575, 2.282, 2.114, 1.924, 1.864, 1.816, 1.777, 1.744]
_A2 = [0, 0, 1.880, 1.023, 0.729, 0.577, 0.483, 0.419, 0.373, 0.337, 0.308]
_A3 = [0, 0, 2.659, 1.954, 1.628, 1.427, 1.287, 1.182, 1.099, 1.032, 0.975]
_B3 = [0, 0, 0, 0, 0, 0, 0.030, 0.118, 0.185, 0.239, 0.284]
_B4 = [0, 0, 3.267, 2.568, 2.266, 2.089, 1.970, 1.882, 1.815, 1.761, 1.716]
_C4 = [0, 0, 0.7979, 0.8862, 0.9213, 0.9400, 0.9515, 0.9594, 0.9650, 0.9693, 0.9727]


@dataclass
class Alarm:
    index: int          # data point index
    rule: str           # e.g. "WE1", "NE2"
    description: str
    value: float


@dataclass
class ControlChartResult:
    chart_type: str         # "I-MR", "Xbar-R", "Xbar-S", "P", "NP", "C", "U"
    column: str
    subgroup_size: int
    n_points: int           # number of plotted points
    # Primary chart (I, Xbar, P, C, U)
    primary_values: list
    primary_ucl: float
    primary_cl: float
    primary_lcl: float
    primary_label: str      # "Individual", "X̄", "Proportion", etc.
    # Secondary chart (MR, R, S) — None for attribute charts
    secondary_values: list
    secondary_ucl: float
    secondary_cl: float
    secondary_lcl: float
    secondary_label: str
    # Alarms
    western_electric_alarms: list   # list of Alarm dicts
    nelson_alarms: list
    total_alarms: int
    # Process stats
    process_mean: float
    process_sigma: float
    # Stability verdict
    in_control: bool
    stability_verdict: str
    alarm_summary: list     # human-readable summary


# ── Chart type auto-selection ─────────────────────────────────────────────────

def select_chart_type(data: np.ndarray, subgroup_size: int,
                      is_attribute: bool = False, attribute_type: str = None) -> str:
    if is_attribute:
        return attribute_type or "P"
    if subgroup_size == 1:
        return "I-MR"
    elif subgroup_size <= 8:
        return "Xbar-R"
    else:
        return "Xbar-S"


# ── I-MR Chart ────────────────────────────────────────────────────────────────

def build_imr(data: np.ndarray, column: str) -> ControlChartResult:
    n = len(data)
    mr = np.abs(np.diff(data))
    mr_bar = np.mean(mr)
    x_bar = np.mean(data)
    d2 = _D2[2]   # n=2 for moving range
    D4 = _D4_const[2]
    D3 = _D3_const[2]

    sigma_est = mr_bar / d2

    # Individuals chart limits
    ucl_i = x_bar + 3 * sigma_est
    lcl_i = x_bar - 3 * sigma_est

    # MR chart limits
    ucl_mr = D4 * mr_bar
    lcl_mr = D3 * mr_bar   # always 0 for n=2

    we_alarms = western_electric_rules(data, x_bar, sigma_est)
    ne_alarms = nelson_rules(data, x_bar, sigma_est)

    return _make_result("I-MR", column, 1, data,
                        ucl_i, x_bar, lcl_i, "Individual (X)",
                        list(mr), ucl_mr, mr_bar, lcl_mr, "Moving Range (MR)",
                        we_alarms, ne_alarms, x_bar, sigma_est)


# ── Xbar-R Chart ─────────────────────────────────────────────────────────────

def build_xbar_r(data: np.ndarray, column: str, n: int) -> ControlChartResult:
    k = len(data) // n
    groups = data[:k*n].reshape(k, n)
    x_bars = groups.mean(axis=1)
    ranges = groups.max(axis=1) - groups.min(axis=1)

    x_dbl_bar = x_bars.mean()
    r_bar = ranges.mean()
    d2 = _D2[n]
    sigma_est = r_bar / d2

    ucl_x = x_dbl_bar + _A2[n] * r_bar
    lcl_x = x_dbl_bar - _A2[n] * r_bar
    ucl_r = _D4_const[n] * r_bar
    lcl_r = _D3_const[n] * r_bar

    we_alarms = western_electric_rules(x_bars, x_dbl_bar, sigma_est / np.sqrt(n))
    ne_alarms = nelson_rules(x_bars, x_dbl_bar, sigma_est / np.sqrt(n))

    return _make_result("Xbar-R", column, n, x_bars,
                        ucl_x, x_dbl_bar, lcl_x, "Subgroup Mean (X̄)",
                        list(ranges), ucl_r, r_bar, lcl_r, "Subgroup Range (R)",
                        we_alarms, ne_alarms, x_dbl_bar, sigma_est)


# ── Xbar-S Chart ─────────────────────────────────────────────────────────────

def build_xbar_s(data: np.ndarray, column: str, n: int) -> ControlChartResult:
    k = len(data) // n
    groups = data[:k*n].reshape(k, n)
    x_bars = groups.mean(axis=1)
    s_vals = groups.std(axis=1, ddof=1)

    x_dbl_bar = x_bars.mean()
    s_bar = s_vals.mean()
    c4 = _C4[min(n, 10)]
    sigma_est = s_bar / c4

    ucl_x = x_dbl_bar + _A3[n] * s_bar
    lcl_x = x_dbl_bar - _A3[n] * s_bar
    ucl_s = _B4[n] * s_bar
    lcl_s = _B3[n] * s_bar

    we_alarms = western_electric_rules(x_bars, x_dbl_bar, sigma_est / np.sqrt(n))
    ne_alarms = nelson_rules(x_bars, x_dbl_bar, sigma_est / np.sqrt(n))

    return _make_result("Xbar-S", column, n, x_bars,
                        ucl_x, x_dbl_bar, lcl_x, "Subgroup Mean (X̄)",
                        list(s_vals), ucl_s, s_bar, lcl_s, "Subgroup Std Dev (S)",
                        we_alarms, ne_alarms, x_dbl_bar, sigma_est)


# ── Western Electric Rules ────────────────────────────────────────────────────

def western_electric_rules(data: np.ndarray, cl: float, sigma: float) -> list:
    alarms = []
    n = len(data)
    z = (data - cl) / sigma

    # Rule 1: 1 point beyond 3σ
    for i in range(n):
        if abs(z[i]) > 3:
            alarms.append({"index": i, "rule": "WE1", "value": float(data[i]),
                "description": f"Point beyond 3σ (z={z[i]:.2f})"})

    # Rule 2: 2 of 3 consecutive beyond 2σ same side
    for i in range(2, n):
        window = z[i-2:i+1]
        if sum(1 for v in window if v > 2) >= 2:
            alarms.append({"index": i, "rule": "WE2", "value": float(data[i]),
                "description": "2 of 3 consecutive points beyond +2σ"})
        elif sum(1 for v in window if v < -2) >= 2:
            alarms.append({"index": i, "rule": "WE2", "value": float(data[i]),
                "description": "2 of 3 consecutive points beyond -2σ"})

    # Rule 3: 4 of 5 consecutive beyond 1σ same side
    for i in range(4, n):
        window = z[i-4:i+1]
        if sum(1 for v in window if v > 1) >= 4:
            alarms.append({"index": i, "rule": "WE3", "value": float(data[i]),
                "description": "4 of 5 consecutive points beyond +1σ"})
        elif sum(1 for v in window if v < -1) >= 4:
            alarms.append({"index": i, "rule": "WE3", "value": float(data[i]),
                "description": "4 of 5 consecutive points beyond -1σ"})

    # Rule 4: 8 consecutive same side of CL
    for i in range(7, n):
        window = z[i-7:i+1]
        if all(v > 0 for v in window):
            alarms.append({"index": i, "rule": "WE4", "value": float(data[i]),
                "description": "8 consecutive points above centerline"})
        elif all(v < 0 for v in window):
            alarms.append({"index": i, "rule": "WE4", "value": float(data[i]),
                "description": "8 consecutive points below centerline"})

    return alarms


# ── Nelson Rules ──────────────────────────────────────────────────────────────

def nelson_rules(data: np.ndarray, cl: float, sigma: float) -> list:
    alarms = []
    n = len(data)
    z = (data - cl) / sigma

    # Nelson 1 = WE1 (already captured, skip dupe)

    # Nelson 2: 9 consecutive same side
    for i in range(8, n):
        window = z[i-8:i+1]
        if all(v > 0 for v in window):
            alarms.append({"index": i, "rule": "NE2", "value": float(data[i]),
                "description": "9 consecutive points above centerline (shift)"})
        elif all(v < 0 for v in window):
            alarms.append({"index": i, "rule": "NE2", "value": float(data[i]),
                "description": "9 consecutive points below centerline (shift)"})

    # Nelson 3: 6 consecutive trending (monotone)
    for i in range(5, n):
        window = data[i-5:i+1]
        diffs = np.diff(window)
        if all(d > 0 for d in diffs):
            alarms.append({"index": i, "rule": "NE3", "value": float(data[i]),
                "description": "6 consecutive points trending upward"})
        elif all(d < 0 for d in diffs):
            alarms.append({"index": i, "rule": "NE3", "value": float(data[i]),
                "description": "6 consecutive points trending downward"})

    # Nelson 4: 14 alternating up-down
    for i in range(13, n):
        window = data[i-13:i+1]
        diffs = np.diff(window)
        if all(diffs[j] * diffs[j+1] < 0 for j in range(len(diffs)-1)):
            alarms.append({"index": i, "rule": "NE4", "value": float(data[i]),
                "description": "14 consecutive points alternating up-down (stratification)"})

    # Nelson 5: 2 of 3 beyond 2σ (= WE2, already handled)

    # Nelson 6: 4 of 5 beyond 1σ (= WE3, already handled)

    # Nelson 7: 15 within 1σ (hugging centerline — stratification)
    for i in range(14, n):
        window = z[i-14:i+1]
        if all(abs(v) < 1 for v in window):
            alarms.append({"index": i, "rule": "NE7", "value": float(data[i]),
                "description": "15 consecutive points within ±1σ (hugging — possible stratification)"})

    # Nelson 8: 8 beyond 1σ both sides
    for i in range(7, n):
        window = z[i-7:i+1]
        if all(abs(v) > 1 for v in window):
            alarms.append({"index": i, "rule": "NE8", "value": float(data[i]),
                "description": "8 consecutive points beyond ±1σ (bimodal / mixture)"})

    return alarms


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_result(chart_type, column, subgroup_size, primary_vals,
                 ucl_p, cl_p, lcl_p, p_label,
                 secondary_vals, ucl_s, cl_s, lcl_s, s_label,
                 we_alarms, ne_alarms, proc_mean, proc_sigma):
    total = len(we_alarms) + len(ne_alarms)
    in_control = total == 0
    if in_control:
        verdict = "In Control — No rule violations detected"
    elif total <= 2:
        verdict = f"Minor Issues — {total} alarm(s) detected, monitor closely"
    elif total <= 5:
        verdict = f"Unstable — {total} alarms detected, investigate assignable causes"
    else:
        verdict = f"Out of Control — {total} alarms, immediate investigation required"

    # Deduplicate alarms by index+rule
    seen = set()
    we_clean, ne_clean = [], []
    for a in we_alarms:
        k = (a['index'], a['rule'])
        if k not in seen: seen.add(k); we_clean.append(a)
    for a in ne_alarms:
        k = (a['index'], a['rule'])
        if k not in seen: seen.add(k); ne_clean.append(a)

    # Alarm summary
    rule_counts = {}
    for a in we_clean + ne_clean:
        rule_counts[a['rule']] = rule_counts.get(a['rule'], 0) + 1
    summary = [f"{rule}: {cnt} occurrence(s)" for rule, cnt in sorted(rule_counts.items())]

    return ControlChartResult(
        chart_type=chart_type, column=column, subgroup_size=subgroup_size,
        n_points=len(primary_vals),
        primary_values=[round(float(v), 6) for v in primary_vals],
        primary_ucl=round(float(ucl_p), 6), primary_cl=round(float(cl_p), 6),
        primary_lcl=round(float(lcl_p), 6), primary_label=p_label,
        secondary_values=[round(float(v), 6) for v in secondary_vals],
        secondary_ucl=round(float(ucl_s), 6), secondary_cl=round(float(cl_s), 6),
        secondary_lcl=round(float(lcl_s), 6), secondary_label=s_label,
        western_electric_alarms=we_clean, nelson_alarms=ne_clean,
        total_alarms=len(we_clean)+len(ne_clean),
        process_mean=round(float(proc_mean), 6),
        process_sigma=round(float(proc_sigma), 6),
        in_control=in_control, stability_verdict=verdict,
        alarm_summary=summary
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze_control_chart(data: np.ndarray, column: str,
                          subgroup_size: int = 1) -> ControlChartResult:
    data = data[~np.isnan(data)].astype(float)
    if len(data) < 10:
        raise ValueError("Need at least 10 data points for a control chart")

    chart_type = select_chart_type(data, subgroup_size)
    if chart_type == "I-MR":
        return build_imr(data, column)
    elif chart_type == "Xbar-R":
        return build_xbar_r(data, column, subgroup_size)
    else:
        return build_xbar_s(data, column, subgroup_size)
