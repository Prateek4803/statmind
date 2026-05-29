"""
StatMind N3 — Correlation Matrix + Heatmap
Pearson + Spearman correlation for all numeric columns.
Color-coded matrix, p-value filter, scatter pairs.
"""
import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CorrelationResult:
    columns: list
    n: int
    # Pearson
    pearson_r: list        # n×n matrix (list of lists)
    pearson_p: list        # n×n matrix
    # Spearman
    spearman_r: list
    spearman_p: list
    # Strong correlations
    strong_pairs: list     # [{col_a, col_b, pearson_r, spearman_r, p_value, strength}]
    # Chart data
    chart_data: dict
    # Conclusion
    conclusion: str
    n_significant: int


def correlation_matrix(
    df,            # pandas DataFrame, numeric columns only
    alpha: float = 0.05,
    min_r: float = 0.3,    # minimum |r| to report as noteworthy
) -> CorrelationResult:
    import pandas as pd

    cols = df.columns.tolist()
    k = len(cols)
    n = len(df.dropna())

    pearson_r  = [[0.0]*k for _ in range(k)]
    pearson_p  = [[1.0]*k for _ in range(k)]
    spearman_r = [[0.0]*k for _ in range(k)]
    spearman_p = [[1.0]*k for _ in range(k)]

    strong_pairs = []

    for i in range(k):
        for j in range(k):
            if i == j:
                pearson_r[i][j] = 1.0
                spearman_r[i][j] = 1.0
                pearson_p[i][j] = 0.0
                spearman_p[i][j] = 0.0
                continue
            # Drop rows where either column is NaN
            mask = (~df.iloc[:,i].isna()) & (~df.iloc[:,j].isna())
            x = df.iloc[:,i][mask].values.astype(float)
            y = df.iloc[:,j][mask].values.astype(float)
            if len(x) < 5:
                continue
            pr, pp = stats.pearsonr(x, y)
            sr, sp = stats.spearmanr(x, y)
            pearson_r[i][j]  = round(float(pr), 4)
            pearson_p[i][j]  = round(float(pp), 5)
            spearman_r[i][j] = round(float(sr), 4)
            spearman_p[i][j] = round(float(sp), 5)

            if i < j and abs(pr) >= min_r:
                strength = "Very Strong" if abs(pr)>=0.9 else "Strong" if abs(pr)>=0.7 else "Moderate" if abs(pr)>=0.5 else "Weak"
                direction = "positive" if pr > 0 else "negative"
                strong_pairs.append({
                    "col_a": cols[i], "col_b": cols[j],
                    "pearson_r": round(float(pr), 4),
                    "spearman_r": round(float(sr), 4),
                    "p_value": round(float(pp), 5),
                    "significant": bool(pp < alpha),
                    "strength": strength,
                    "direction": direction,
                    "interpretation": f"{strength} {direction} correlation (r={pr:.3f}, p={pp:.4f}). {'Statistically significant.' if pp < alpha else 'Not statistically significant.'}"
                })

    strong_pairs.sort(key=lambda x: abs(x["pearson_r"]), reverse=True)
    n_sig = sum(1 for p in strong_pairs if p["significant"])

    conclusion = (
        f"Correlation analysis of {k} variables (n={n}). "
        f"{len(strong_pairs)} pairs with |r| ≥ {min_r}. "
        f"{n_sig} statistically significant correlations (α={alpha}). "
        + (f"Strongest: {strong_pairs[0]['col_a']} ↔ {strong_pairs[0]['col_b']} (r={strong_pairs[0]['pearson_r']})." if strong_pairs else "No notable correlations found.")
    )

    chart_data = {
        "columns": cols,
        "pearson_r": pearson_r,
        "pearson_p": pearson_p,
        "spearman_r": spearman_r,
        "strong_pairs": strong_pairs[:10],
        "alpha": alpha,
        "min_r": min_r,
    }

    return CorrelationResult(
        columns=cols, n=n,
        pearson_r=pearson_r, pearson_p=pearson_p,
        spearman_r=spearman_r, spearman_p=spearman_p,
        strong_pairs=strong_pairs,
        chart_data=chart_data,
        conclusion=conclusion,
        n_significant=n_sig,
    )
