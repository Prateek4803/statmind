"""
outliers.py — StatMind Outlier Detection Engine
Grubbs (single/iterative), Dixon Q, Rosner ESD
"""

import dataclasses
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
from scipy import stats


@dataclass
class OutlierResult:
    column: str
    n: int
    mean: float
    std: float
    median: float
    methods_used: List[str]
    outliers: List[dict]          # {index, value, method, z_score, p_value}
    n_outliers: int
    data: List[float]
    verdict: str                  # "Outliers found" | "No outliers detected"
    summary: str
    recommendation: str


def _grubbs_single(data: np.ndarray, alpha: float = 0.05):
    """
    Grubbs test (Extreme Studentized Deviate) — tests the single most extreme value.
    Returns (is_outlier, index, G_stat, G_crit, p_value)
    """
    n = len(data)
    if n < 7:
        return False, -1, 0.0, 0.0, 1.0

    mean = data.mean()
    std = data.std(ddof=1)
    if std == 0:
        return False, -1, 0.0, 0.0, 1.0

    z = np.abs(data - mean) / std
    idx = int(z.argmax())
    G = float(z[idx])

    # Critical value from t-distribution
    t_crit = stats.t.ppf(1 - alpha / (2 * n), df=n - 2)
    G_crit = ((n - 1) / np.sqrt(n)) * np.sqrt(t_crit ** 2 / (n - 2 + t_crit ** 2))

    # Approximate p-value
    # P(G > G_obs) ≈ 2 * P(t > sqrt((n*(n-2)*G^2) / ((n-1)^2 - n*G^2)))
    try:
        t_stat = np.sqrt((n * (n - 2) * G ** 2) / ((n - 1) ** 2 - n * G ** 2))
        p_value = float(min(1.0, 2 * n * (1 - stats.t.cdf(t_stat, df=n - 2))))
    except Exception:
        p_value = 1.0

    return G > G_crit, idx, round(G, 4), round(G_crit, 4), round(p_value, 5)


def _grubbs_iterative(data: np.ndarray, alpha: float = 0.05, max_iter: int = 10):
    """
    Iterative Grubbs — removes most extreme outlier and retests.
    Returns list of (original_index, value, G, G_crit, p_value).
    """
    original_indices = np.arange(len(data))
    working = data.copy()
    working_idx = original_indices.copy()
    outliers = []

    for _ in range(max_iter):
        if len(working) < 7:
            break
        is_out, local_idx, G, G_crit, p = _grubbs_single(working, alpha)
        if not is_out:
            break
        orig_idx = int(working_idx[local_idx])
        outliers.append({
            "index": orig_idx,
            "value": round(float(working[local_idx]), 6),
            "method": "Grubbs",
            "g_stat": G,
            "g_crit": G_crit,
            "z_score": round(float(np.abs(working[local_idx] - working.mean()) / working.std(ddof=1)), 4),
            "p_value": p,
        })
        # Remove outlier and continue
        working = np.delete(working, local_idx)
        working_idx = np.delete(working_idx, local_idx)

    return outliers


def _dixon_q(data: np.ndarray, alpha: float = 0.05):
    """
    Dixon Q test — for small samples (3–30). Tests min and max values.
    Returns list of outlier dicts.
    """
    n = len(data)
    if not (3 <= n <= 30):
        return []

    sorted_data = np.sort(data)
    original_indices = np.argsort(data)
    outliers = []

    # Q critical values (alpha=0.05) for n=3..30
    q_crit_table = {
        3: 0.970, 4: 0.829, 5: 0.710, 6: 0.628, 7: 0.569,
        8: 0.608, 9: 0.564, 10: 0.530, 11: 0.502, 12: 0.479,
        13: 0.611, 14: 0.586, 15: 0.565, 16: 0.546, 17: 0.529,
        18: 0.514, 19: 0.501, 20: 0.489, 21: 0.478, 22: 0.468,
        23: 0.459, 24: 0.451, 25: 0.443, 26: 0.436, 27: 0.429,
        28: 0.423, 29: 0.417, 30: 0.412,
    }
    q_crit = q_crit_table.get(n, 0.412)
    data_range = float(sorted_data[-1] - sorted_data[0])

    if data_range == 0:
        return []

    # Test minimum (lower outlier)
    if n <= 7:
        q_min = (sorted_data[1] - sorted_data[0]) / data_range
    elif n <= 10:
        q_min = (sorted_data[1] - sorted_data[0]) / (sorted_data[-2] - sorted_data[0])
    elif n <= 13:
        q_min = (sorted_data[2] - sorted_data[0]) / (sorted_data[-2] - sorted_data[0])
    else:
        q_min = (sorted_data[2] - sorted_data[0]) / (sorted_data[-3] - sorted_data[0])

    if q_min > q_crit:
        outliers.append({
            "index": int(original_indices[0]),
            "value": round(float(sorted_data[0]), 6),
            "method": "Dixon Q",
            "q_stat": round(float(q_min), 4),
            "q_crit": round(q_crit, 4),
            "z_score": round(float(abs(sorted_data[0] - data.mean()) / max(data.std(ddof=1), 1e-10)), 4),
            "p_value": None,
        })

    # Test maximum (upper outlier)
    if n <= 7:
        q_max = (sorted_data[-1] - sorted_data[-2]) / data_range
    elif n <= 10:
        q_max = (sorted_data[-1] - sorted_data[-2]) / (sorted_data[-1] - sorted_data[1])
    elif n <= 13:
        q_max = (sorted_data[-1] - sorted_data[-3]) / (sorted_data[-1] - sorted_data[1])
    else:
        q_max = (sorted_data[-1] - sorted_data[-3]) / (sorted_data[-1] - sorted_data[2])

    if q_max > q_crit:
        outliers.append({
            "index": int(original_indices[-1]),
            "value": round(float(sorted_data[-1]), 6),
            "method": "Dixon Q",
            "q_stat": round(float(q_max), 4),
            "q_crit": round(q_crit, 4),
            "z_score": round(float(abs(sorted_data[-1] - data.mean()) / max(data.std(ddof=1), 1e-10)), 4),
            "p_value": None,
        })

    return outliers


def _rosner_esd(data: np.ndarray, alpha: float = 0.05, max_outliers: int = 10):
    """
    Rosner's Generalized ESD (Extreme Studentized Deviate) test.
    Tests for up to max_outliers outliers simultaneously.
    More powerful than iterative Grubbs for multiple outliers.
    """
    n = len(data)
    if n < 25:
        return []

    r = min(max_outliers, n // 5, 10)
    working = data.copy()
    test_stats = []
    removed_indices = []
    removed_values = []

    for i in range(r):
        mean = working.mean()
        std = working.std(ddof=1)
        if std == 0:
            break
        z = np.abs(working - mean) / std
        max_idx = int(z.argmax())
        R_i = float(z[max_idx])
        test_stats.append(R_i)
        removed_values.append(float(working[max_idx]))
        removed_indices.append(max_idx)
        working = np.delete(working, max_idx)

    # Compute critical values λ_i for i=1..r
    outliers = []
    last_significant = -1
    for i in range(r):
        ni = n - i
        p = 1 - alpha / (2 * (ni - i))
        t_crit = stats.t.ppf(p, df=ni - i - 2)
        lambda_i = ((ni - i - 1) * t_crit) / np.sqrt((ni - i - 2 + t_crit ** 2) * (ni - i))
        if test_stats[i] > lambda_i:
            last_significant = i

    if last_significant >= 0:
        # Find original indices of removed values
        working2 = data.copy()
        orig_indices = list(range(len(data)))
        for i in range(last_significant + 1):
            mean = working2.mean()
            std = working2.std(ddof=1)
            z = np.abs(working2 - mean) / std
            max_local = int(z.argmax())
            orig_idx = orig_indices[max_local]
            outliers.append({
                "index": orig_idx,
                "value": round(float(working2[max_local]), 6),
                "method": "Rosner ESD",
                "r_stat": round(test_stats[i], 4),
                "z_score": round(float(z[max_local]), 4),
                "p_value": None,
            })
            working2 = np.delete(working2, max_local)
            orig_indices.pop(max_local)

    return outliers


def detect_outliers(data: np.ndarray, column: str,
                    method: str = "all", alpha: float = 0.05) -> OutlierResult:
    """
    Main outlier detection function.
    method: "all" | "grubbs" | "dixon" | "esd"
    """
    data = np.array(data, dtype=float)
    data = data[~np.isnan(data)]
    n = len(data)

    mean = float(data.mean())
    std = float(data.std(ddof=1)) if n > 1 else 0.0
    median = float(np.median(data))

    all_outliers = []
    methods_used = []
    seen_indices = set()

    if method in ("all", "grubbs"):
        methods_used.append("Grubbs")
        grubbs_out = _grubbs_iterative(data, alpha=alpha)
        for o in grubbs_out:
            if o["index"] not in seen_indices:
                all_outliers.append(o)
                seen_indices.add(o["index"])

    if method in ("all", "dixon") and 3 <= n <= 30:
        methods_used.append("Dixon Q")
        dixon_out = _dixon_q(data, alpha=alpha)
        for o in dixon_out:
            if o["index"] not in seen_indices:
                all_outliers.append(o)
                seen_indices.add(o["index"])

    if method in ("all", "esd") and n >= 25:
        methods_used.append("Rosner ESD")
        esd_out = _rosner_esd(data, alpha=alpha)
        for o in esd_out:
            if o["index"] not in seen_indices:
                all_outliers.append(o)
                seen_indices.add(o["index"])

    # Sort by z-score descending
    all_outliers.sort(key=lambda x: x.get("z_score", 0), reverse=True)

    n_out = len(all_outliers)
    verdict = f"{n_out} outlier{'s' if n_out != 1 else ''} detected" if n_out > 0 else "No outliers detected"

    if n_out > 0:
        out_vals = [o["value"] for o in all_outliers]
        summary = (f"{n_out} outlier{'s' if n_out != 1 else ''} found in {column} "
                   f"(n={n}): {out_vals}. "
                   f"Methods: {', '.join(methods_used)}.")
        recommendation = (
            "Each outlier requires physical investigation before removal. "
            "Check for: measurement error, data entry mistake, real process event (PM, material change). "
            "Document investigation result. Never remove outliers automatically."
        )
    else:
        summary = (f"No statistically significant outliers detected in {column} (n={n}). "
                   f"Methods used: {', '.join(methods_used)}.")
        recommendation = "Data appears free of outliers at α={:.2f}. Proceed with capability analysis.".format(alpha)

    return OutlierResult(
        column=column,
        n=n,
        mean=round(mean, 6),
        std=round(std, 6),
        median=round(median, 6),
        methods_used=methods_used,
        outliers=all_outliers,
        n_outliers=n_out,
        data=[round(float(x), 6) for x in data],
        verdict=verdict,
        summary=summary,
        recommendation=recommendation,
    )
