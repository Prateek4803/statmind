"""
StatMind E2 — Pareto Chart Engine
Defect frequency ranking, 80/20 rule, cumulative % line
Accepts: column of categories, or two columns (category + count)
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParetoResult:
    title: str
    categories: list        # sorted by frequency desc
    counts: list
    percentages: list       # individual %
    cumulative_pct: list    # cumulative %
    vital_few: list         # categories making up ≤80%
    useful_many: list       # the rest
    vital_few_pct: float    # % of total defects from vital few
    total_count: int
    n_categories: int
    conclusion: str
    # Raw data for chart
    chart_data: dict


def analyze_pareto(
    categories: list,          # list of category labels (one per observation)
    counts: list = None,       # optional: pre-aggregated counts per category
    title: str = "Defect / Issue Analysis",
    threshold: float = 80.0,   # vital few threshold (default 80%)
) -> ParetoResult:
    """
    Build a Pareto analysis.
    If counts is None: categories is a raw list of labels (one per defect event).
    If counts provided: categories + counts are pre-aggregated (like a summary table).
    """
    # Build frequency dict
    if counts is not None:
        freq = dict(zip(categories, counts))
    else:
        from collections import Counter
        freq = dict(Counter(categories))

    # Sort descending
    sorted_items = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    cats   = [str(item[0]) for item in sorted_items]
    cnts   = [int(item[1]) for item in sorted_items]
    total  = sum(cnts)

    if total == 0:
        raise ValueError("All counts are zero — nothing to analyze.")

    pcts   = [round(c/total*100, 2) for c in cnts]
    cumul  = []
    running = 0.0
    for p in pcts:
        running += p
        cumul.append(round(running, 2))

    # Vital few (≤threshold%)
    vital_few, useful_many = [], []
    for i, c in enumerate(cumul):
        if c <= threshold or (vital_few == [] and c > threshold):
            vital_few.append(cats[i])
        else:
            useful_many.append(cats[i])

    # Make sure at least 1 in vital few
    if not vital_few and cats:
        vital_few = [cats[0]]
        useful_many = cats[1:]

    vital_count = sum(cnts[cats.index(c)] for c in vital_few)
    vital_pct   = round(vital_count / total * 100, 1)

    conclusion = (
        f"The top {len(vital_few)} {'category' if len(vital_few)==1 else 'categories'} "
        f"({', '.join(vital_few[:3])}{'…' if len(vital_few)>3 else ''}) "
        f"account for {vital_pct:.1f}% of all {total:,} occurrences. "
        f"Focusing corrective actions here will address the majority of the problem."
    )

    return ParetoResult(
        title=title,
        categories=cats, counts=cnts,
        percentages=pcts, cumulative_pct=cumul,
        vital_few=vital_few, useful_many=useful_many,
        vital_few_pct=vital_pct,
        total_count=total, n_categories=len(cats),
        conclusion=conclusion,
        chart_data={
            "categories": cats, "counts": cnts,
            "percentages": pcts, "cumulative_pct": cumul,
            "threshold": threshold,
            "vital_few_boundary": len(vital_few),
            "total": total,
        },
    )


def pareto_from_dataframe(df: pd.DataFrame, category_col: str,
                           count_col: str = None,
                           title: str = "Pareto Analysis",
                           threshold: float = 80.0) -> ParetoResult:
    """Parse a DataFrame for Pareto analysis."""
    if category_col not in df.columns:
        raise ValueError(f"Column '{category_col}' not found")
    if count_col and count_col in df.columns:
        cats   = df[category_col].astype(str).tolist()
        counts = df[count_col].astype(float).tolist()
    else:
        cats   = df[category_col].astype(str).tolist()
        counts = None
    return analyze_pareto(cats, counts, title, threshold)
