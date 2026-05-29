"""
StatMind E6 — Multi-Vari Chart Engine
Visualises 3 sources of variation: part-to-part, within-part, time-to-time
Critical for DMAIC Measure phase
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MultiVariResult:
    column: str
    # Sources of variation
    sources: dict            # {within_part, part_to_part, time_to_time, total}
    dominant_source: str
    # Variance components
    var_within: float
    var_part: float
    var_time: float
    var_total: float
    pct_within: float
    pct_part: float
    pct_time: float
    # Group stats
    part_stats: list         # per-part stats
    time_stats: list         # per-time-period stats
    # Chart data
    chart_data: dict
    # Conclusions
    conclusion: str
    recommended_action: str


def analyze_multivari(
    values: np.ndarray,
    parts: np.ndarray,
    positions: np.ndarray = None,   # within-part position (top/middle/bottom, loc1/loc2, etc.)
    time_periods: np.ndarray = None, # time / lot / shift
    column: str = "Measurement",
) -> MultiVariResult:
    """
    Multi-Vari analysis.
    Minimum: values + parts.
    Optional: positions (within-part), time_periods (between-time).
    """
    values = np.array(values, dtype=float)
    parts  = np.array(parts,  dtype=str)

    # Default positions and time periods if not provided
    if positions is None:
        positions = np.array(["Pos1"] * len(values))
    else:
        positions = np.array(positions, dtype=str)

    if time_periods is None:
        # Treat each part as its own time period for within/between split
        time_periods = parts.copy()
    else:
        time_periods = np.array(time_periods, dtype=str)

    unique_parts   = np.unique(parts)
    unique_times   = np.unique(time_periods)
    unique_pos     = np.unique(positions)
    grand_mean     = float(np.mean(values))

    # ── Variance components ───────────────────────────────────────────────────
    # Within-part variation (variation across positions within same part)
    within_vars = []
    for p in unique_parts:
        mask = parts == p
        if mask.sum() > 1:
            within_vars.append(float(np.var(values[mask], ddof=1)))
    var_within = float(np.mean(within_vars)) if within_vars else 0.0

    # Part-to-part variation (variation in part means)
    part_means = [float(np.mean(values[parts == p])) for p in unique_parts]
    var_part   = float(np.var(part_means, ddof=1)) if len(part_means) > 1 else 0.0

    # Time-to-time variation (variation in time period means)
    time_means = [float(np.mean(values[time_periods == t])) for t in unique_times]
    var_time   = float(np.var(time_means, ddof=1)) if len(time_means) > 1 else 0.0

    var_total  = var_within + var_part + var_time
    if var_total == 0:
        var_total = 1.0  # prevent division by zero

    pct_within = round(var_within / var_total * 100, 1)
    pct_part   = round(var_part   / var_total * 100, 1)
    pct_time   = round(var_time   / var_total * 100, 1)

    # Dominant source
    dominant = max(
        [("Within-Part", pct_within), ("Part-to-Part", pct_part), ("Time-to-Time", pct_time)],
        key=lambda x: x[1]
    )[0]

    # ── Part stats ────────────────────────────────────────────────────────────
    part_stats = []
    for p in unique_parts:
        mask = parts == p
        vs = values[mask]
        part_stats.append({
            "part": str(p), "n": int(mask.sum()),
            "mean": round(float(np.mean(vs)), 5),
            "min":  round(float(np.min(vs)), 5),
            "max":  round(float(np.max(vs)), 5),
            "range": round(float(np.ptp(vs)), 5),
        })

    # ── Time stats ────────────────────────────────────────────────────────────
    time_stats = []
    for t in unique_times:
        mask = time_periods == t
        vs = values[mask]
        time_stats.append({
            "period": str(t), "n": int(mask.sum()),
            "mean": round(float(np.mean(vs)), 5),
            "std":  round(float(np.std(vs, ddof=1)), 5),
        })

    # ── Chart data ────────────────────────────────────────────────────────────
    # For each part, collect (position, value) pairs — plotted as vertical ranges
    chart_groups = []
    for p in unique_parts:
        mask = parts == p
        pts  = []
        for pos in unique_pos:
            pos_mask = mask & (positions == pos)
            if pos_mask.sum() > 0:
                pts.append({"position": str(pos), "values": values[pos_mask].tolist()})
        chart_groups.append({
            "part": str(p),
            "mean": round(float(np.mean(values[mask])), 5),
            "min":  round(float(np.min(values[mask])), 5),
            "max":  round(float(np.max(values[mask])), 5),
            "points": pts,
            "all_values": values[mask].tolist(),
        })

    # Grand mean line + part mean trend line
    chart_data = {
        "groups": chart_groups,
        "grand_mean": round(grand_mean, 5),
        "part_means": [round(float(np.mean(values[parts == p])), 5) for p in unique_parts],
        "part_labels": unique_parts.tolist(),
        "time_means": [round(float(np.mean(values[time_periods == t])), 5) for t in unique_times],
        "time_labels": unique_times.tolist(),
        "var_components": {
            "within": round(pct_within, 1),
            "part":   round(pct_part,   1),
            "time":   round(pct_time,   1),
        }
    }

    # Conclusions
    action_map = {
        "Within-Part": "Focus on within-part consistency. Common causes: fixturing variation, tool runout, measurement technique, local material variation. Check within-part measurement method.",
        "Part-to-Part": "Focus on part-to-part consistency. Common causes: incoming material variation, batch-to-batch differences, process centering drift. Check material lot tracking and process SPC.",
        "Time-to-Time": "Focus on temporal stability. Common causes: shift-to-shift differences, warm-up effects, consumable wear, environmental drift. Check time-based SPC and shift changeover procedures.",
    }

    conclusion = (
        f"Dominant source of variation: {dominant} ({max(pct_within, pct_part, pct_time):.1f}% of total). "
        f"Breakdown — Within-Part: {pct_within}%, Part-to-Part: {pct_part}%, Time-to-Time: {pct_time}%."
    )

    return MultiVariResult(
        column=column,
        sources={"within_part": pct_within, "part_to_part": pct_part, "time_to_time": pct_time},
        dominant_source=dominant,
        var_within=round(var_within, 8), var_part=round(var_part, 8),
        var_time=round(var_time, 8), var_total=round(var_total, 8),
        pct_within=pct_within, pct_part=pct_part, pct_time=pct_time,
        part_stats=part_stats, time_stats=time_stats,
        chart_data=chart_data,
        conclusion=conclusion,
        recommended_action=action_map.get(dominant, ""),
    )
