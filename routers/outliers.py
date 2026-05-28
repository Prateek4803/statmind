"""
outliers.py — StatMind Outlier Detection Engine
================================================
Implements three complementary outlier-detection methods:

  1. Grubbs (iterative)  — detects outliers one at a time; removes and retests.
                           Works for n ≥ 7.
  2. Dixon Q             — for small samples (3 ≤ n ≤ 30). Tests min and max.
  3. Rosner ESD          — Generalized Extreme Studentized Deviate; tests for
                           up to r = min(10, n//5) outliers simultaneously.
                           Works for n ≥ 25.

ENGINEERING NOTES
-----------------
- Never removes outliers automatically.  Returns a report; disposition is
  the engineer's responsibility.
- All three methods use α = 0.05 by default (configurable).
- When method='all': Grubbs runs first; Dixon and ESD add any NEW indices
  not already flagged by Grubbs.
- Results are sorted by z-score descending.
- The dataclass is JSON-serialisable via dataclasses.asdict().
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from scipy import stats


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class OutlierPoint:
    index:   int           # 0-based index in the original array
    value:   float
    method:  str           # "Grubbs" | "Dixon Q" | "Rosner ESD"
    z_score: float
    p_value: Optional[float] = None
    # Method-specific test statistics
    g_stat:  Optional[float] = None   # Grubbs G
    g_crit:  Optional[float] = None
    q_stat:  Optional[float] = None   # Dixon Q
    q_crit:  Optional[float] = None
    r_stat:  Optional[float] = None   # Rosner R_i


@dataclass
class OutlierResult:
    column:        str
    n:             int
    mean:          float
    std:           float
    median:        float
    methods_used:  List[str]
    outliers:      List[OutlierPoint]
    n_outliers:    int
    data:          List[float]
    verdict:       str
    summary:       str
    recommendation: str
    alpha:         float = 0.05


# ── Grubbs (iterative) ────────────────────────────────────────────────────────

def _grubbs_critical(n: int, alpha: float) -> float:
    """Two-sided Grubbs critical value from t-distribution."""
    t_crit = stats.t.ppf(1.0 - alpha / (2.0 * n), df=n - 2)
    return ((n - 1) / math.sqrt(n)) * math.sqrt(
        t_crit ** 2 / (n - 2 + t_crit ** 2)
    )


def _grubbs_pvalue(G: float, n: int) -> float:
    """Approximate two-sided p-value for Grubbs statistic G."""
    try:
        denom = (n - 1) ** 2 - n * G ** 2
        if denom <= 0:
            return 0.0
        t_stat = math.sqrt(n * (n - 2) * G ** 2 / denom)
        return float(min(1.0, 2.0 * n * (1.0 - stats.t.cdf(t_stat, df=n - 2))))
    except Exception:
        return 0.0


def _grubbs_iterative(
    data: np.ndarray, alpha: float = 0.05
) -> List[OutlierPoint]:
    """
    Iterative Grubbs test.  Each iteration removes the most extreme value
    and retests until G ≤ G_crit or n < 7.
    """
    working     = data.copy()
    orig_indices = list(range(len(data)))
    results: List[OutlierPoint] = []

    for _ in range(min(10, len(data))):
        n = len(working)
        if n < 7:
            break
        mean = working.mean()
        std  = working.std(ddof=1)
        if std == 0:
            break

        z       = np.abs(working - mean) / std
        max_idx = int(z.argmax())
        G       = float(z[max_idx])
        G_crit  = _grubbs_critical(n, alpha)

        if G <= G_crit:
            break

        orig_idx = orig_indices[max_idx]
        results.append(
            OutlierPoint(
                index=orig_idx,
                value=round(float(working[max_idx]), 6),
                method="Grubbs",
                z_score=round(G, 4),
                p_value=round(_grubbs_pvalue(G, n), 5),
                g_stat=round(G, 4),
                g_crit=round(G_crit, 4),
            )
        )

        working      = np.delete(working, max_idx)
        orig_indices.pop(max_idx)

    return results


# ── Dixon Q ──────────────────────────────────────────────────────────────────

# Critical values at α = 0.05 for n = 3..30 (Dean & Dixon 1951)
_DIXON_Q_CRIT_05 = {
    3: 0.970, 4: 0.829, 5: 0.710, 6: 0.628, 7: 0.569,
    8: 0.608, 9: 0.564, 10: 0.530, 11: 0.502, 12: 0.479,
    13: 0.611, 14: 0.586, 15: 0.565, 16: 0.546, 17: 0.529,
    18: 0.514, 19: 0.501, 20: 0.489, 21: 0.478, 22: 0.468,
    23: 0.459, 24: 0.451, 25: 0.443, 26: 0.436, 27: 0.429,
    28: 0.423, 29: 0.417, 30: 0.412,
}

# Critical values at α = 0.01 (more conservative)
_DIXON_Q_CRIT_01 = {
    3: 0.994, 4: 0.926, 5: 0.821, 6: 0.740, 7: 0.680,
    8: 0.717, 9: 0.672, 10: 0.635, 11: 0.605, 12: 0.579,
    13: 0.697, 14: 0.670, 15: 0.647, 16: 0.627, 17: 0.610,
    18: 0.594, 19: 0.580, 20: 0.567, 21: 0.555, 22: 0.544,
    23: 0.535, 24: 0.526, 25: 0.517, 26: 0.510, 27: 0.502,
    28: 0.495, 29: 0.489, 30: 0.483,
}


def _dixon_q_stat(sorted_data: np.ndarray, test_min: bool) -> float:
    """Compute Dixon Q statistic for minimum (test_min=True) or maximum."""
    n = len(sorted_data)
    data_range = float(sorted_data[-1] - sorted_data[0])
    if data_range == 0:
        return 0.0

    if n <= 7:
        gap = sorted_data[1] - sorted_data[0] if test_min else sorted_data[-1] - sorted_data[-2]
        return gap / data_range
    elif n <= 10:
        gap = sorted_data[1] - sorted_data[0] if test_min else sorted_data[-1] - sorted_data[-2]
        span = sorted_data[-2] - sorted_data[0] if test_min else sorted_data[-1] - sorted_data[1]
        return gap / span if span else 0.0
    elif n <= 13:
        gap = sorted_data[2] - sorted_data[0] if test_min else sorted_data[-1] - sorted_data[-3]
        span = sorted_data[-2] - sorted_data[0] if test_min else sorted_data[-1] - sorted_data[1]
        return gap / span if span else 0.0
    else:
        gap = sorted_data[2] - sorted_data[0] if test_min else sorted_data[-1] - sorted_data[-3]
        span = sorted_data[-3] - sorted_data[0] if test_min else sorted_data[-1] - sorted_data[2]
        return gap / span if span else 0.0


def _dixon_q(data: np.ndarray, alpha: float = 0.05) -> List[OutlierPoint]:
    """Dixon Q test. Valid for 3 ≤ n ≤ 30 only."""
    n = len(data)
    if not (3 <= n <= 30):
        return []

    q_table = _DIXON_Q_CRIT_01 if alpha <= 0.01 else _DIXON_Q_CRIT_05
    q_crit = q_table.get(n, 0.412)

    sorted_data  = np.sort(data)
    orig_sorted  = np.argsort(data)
    results: List[OutlierPoint] = []
    mean = float(data.mean())
    std  = float(data.std(ddof=1)) if n > 1 else 1.0

    for test_min in (True, False):
        q_stat = _dixon_q_stat(sorted_data, test_min)
        if q_stat > q_crit:
            idx = int(orig_sorted[0]) if test_min else int(orig_sorted[-1])
            val = float(data[idx])
            results.append(
                OutlierPoint(
                    index=idx,
                    value=round(val, 6),
                    method="Dixon Q",
                    z_score=round(abs(val - mean) / max(std, 1e-10), 4),
                    q_stat=round(float(q_stat), 4),
                    q_crit=round(float(q_crit), 4),
                )
            )

    return results


# ── Rosner ESD ────────────────────────────────────────────────────────────────

def _rosner_esd(
    data: np.ndarray, alpha: float = 0.05, max_outliers: Optional[int] = None
) -> List[OutlierPoint]:
    """
    Rosner's Generalized ESD (Extreme Studentized Deviate) test.
    Tests for up to max_outliers outliers simultaneously.
    Requires n ≥ 25.
    """
    n = len(data)
    if n < 25:
        return []

    r = min(max_outliers or 10, n // 5, 10)
    working      = data.copy()
    removed_vals: List[float] = []
    removed_orig: List[int]   = []
    test_stats:   List[float] = []
    all_indices  = list(range(n))

    for _ in range(r):
        mean = working.mean()
        std  = working.std(ddof=1)
        if std == 0:
            break
        z       = np.abs(working - mean) / std
        max_loc = int(z.argmax())
        test_stats.append(float(z[max_loc]))
        removed_orig.append(all_indices[max_loc])
        removed_vals.append(float(working[max_loc]))
        working = np.delete(working, max_loc)
        all_indices.pop(max_loc)

    # Determine how many are significant (λ critical values)
    last_sig = -1
    for i in range(len(test_stats)):
        ni      = n - i
        p       = 1.0 - alpha / (2.0 * (ni - i))
        try:
            t_c  = stats.t.ppf(p, df=ni - i - 2)
            lam  = (ni - i - 1) * t_c / math.sqrt(
                (ni - i - 2 + t_c ** 2) * (ni - i)
            )
        except Exception:
            continue
        if test_stats[i] > lam:
            last_sig = i

    if last_sig < 0:
        return []

    # Re-trace to get original indices
    results: List[OutlierPoint] = []
    working2    = data.copy()
    orig_track  = list(range(n))
    for i in range(last_sig + 1):
        mean = working2.mean()
        std  = working2.std(ddof=1)
        if std == 0:
            break
        z       = np.abs(working2 - mean) / std
        max_loc = int(z.argmax())
        orig_idx = orig_track[max_loc]
        results.append(
            OutlierPoint(
                index=orig_idx,
                value=round(float(working2[max_loc]), 6),
                method="Rosner ESD",
                z_score=round(float(z[max_loc]), 4),
                r_stat=round(test_stats[i], 4),
            )
        )
        working2 = np.delete(working2, max_loc)
        orig_track.pop(max_loc)

    return results


# ── Public API ────────────────────────────────────────────────────────────────

def detect_outliers(
    data: np.ndarray,
    column: str,
    method: str = "all",
    alpha: float = 0.05,
) -> OutlierResult:
    """
    Detect outliers in a 1-D numeric array.

    Parameters
    ----------
    data    : 1-D array of float values (NaNs stripped internally)
    column  : column name for the report
    method  : "all" | "grubbs" | "dixon" | "esd"
    alpha   : significance level (0.01 or 0.05)

    Returns
    -------
    OutlierResult  (JSON-serialisable via dataclasses.asdict)
    """
    data = np.asarray(data, dtype=float)
    data = data[~np.isnan(data)]
    n    = len(data)

    mean   = float(data.mean()) if n > 0 else 0.0
    std    = float(data.std(ddof=1)) if n > 1 else 0.0
    median = float(np.median(data)) if n > 0 else 0.0

    seen_indices: set[int] = set()
    all_outliers: List[OutlierPoint] = []
    methods_used: List[str] = []

    if method in ("all", "grubbs"):
        methods_used.append("Grubbs")
        for pt in _grubbs_iterative(data, alpha):
            if pt.index not in seen_indices:
                all_outliers.append(pt)
                seen_indices.add(pt.index)

    if method in ("all", "dixon") and 3 <= n <= 30:
        methods_used.append("Dixon Q")
        for pt in _dixon_q(data, alpha):
            if pt.index not in seen_indices:
                all_outliers.append(pt)
                seen_indices.add(pt.index)

    if method in ("all", "esd") and n >= 25:
        methods_used.append("Rosner ESD")
        for pt in _rosner_esd(data, alpha):
            if pt.index not in seen_indices:
                all_outliers.append(pt)
                seen_indices.add(pt.index)

    # Sort by z-score descending
    all_outliers.sort(key=lambda x: x.z_score, reverse=True)

    n_out = len(all_outliers)
    if n_out > 0:
        vals    = [o.value for o in all_outliers]
        verdict = f"{n_out} outlier{'s' if n_out != 1 else ''} detected"
        summary = (
            f"{n_out} statistically significant outlier(s) found in '{column}' "
            f"(n={n}, α={alpha}): {vals}. "
            f"Methods: {', '.join(methods_used)}."
        )
        recommendation = (
            "Each outlier requires physical investigation before any disposition. "
            "Check for: (1) measurement/transcription error, (2) real process event "
            "(chamber maintenance, material lot change), (3) calibration drift. "
            "Document investigation and root cause before removing any data point. "
            "Never remove outliers automatically."
        )
    else:
        verdict = "No outliers detected"
        summary = (
            f"No statistically significant outliers found in '{column}' "
            f"(n={n}, α={alpha}). Methods: {', '.join(methods_used) or 'none applicable'}."
        )
        recommendation = (
            f"Data appears free of outliers at α={alpha}. "
            "Proceed with capability and SPC analysis."
        )

    return OutlierResult(
        column        = column,
        n             = n,
        mean          = round(mean, 6),
        std           = round(std, 6),
        median        = round(median, 6),
        methods_used  = methods_used,
        outliers      = all_outliers,
        n_outliers    = n_out,
        data          = [round(float(x), 6) for x in data],
        verdict       = verdict,
        summary       = summary,
        recommendation= recommendation,
        alpha         = alpha,
    )
