"""
StatMind N12 — Column Calculator / Formula Engine
Derived columns: formulas, rolling averages, log transforms, ratios.
Safe eval with only math/numpy operations allowed.
"""
import numpy as np
import pandas as pd
import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class CalcResult:
    new_column_name: str
    formula: str
    n_values: int
    sample_values: list   # first 10 values
    mean: float
    std: float
    min_val: float
    max_val: float
    n_nan: int
    success: bool
    error: str
    transformed_data: list  # full result

SAFE_NAMES = {
    "log": np.log, "log10": np.log10, "log2": np.log2,
    "exp": np.exp, "sqrt": np.sqrt, "abs": np.abs,
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "round": np.round, "floor": np.floor, "ceil": np.ceil,
    "mean": np.mean, "std": np.std, "median": np.median,
    "min": np.min, "max": np.max, "sum": np.sum,
    "cumsum": np.cumsum, "diff": np.diff,
    "pi": np.pi, "e": np.e, "nan": np.nan, "inf": np.inf,
    # Rolling helpers
    "rolling_mean": lambda x, w: pd.Series(x).rolling(w, min_periods=1).mean().values,
    "rolling_std":  lambda x, w: pd.Series(x).rolling(w, min_periods=1).std().values,
    "rolling_max":  lambda x, w: pd.Series(x).rolling(w, min_periods=1).max().values,
    "rolling_min":  lambda x, w: pd.Series(x).rolling(w, min_periods=1).min().values,
    "zscore":       lambda x: (x - np.mean(x)) / (np.std(x, ddof=1) + 1e-12),
    "normalize":    lambda x: (x - np.min(x)) / (np.max(x) - np.min(x) + 1e-12),
    "rank":         lambda x: pd.Series(x).rank().values,
    "clip":         np.clip,
    "where":        np.where,
    "power":        np.power,
    "np": np, "pd": pd,
}

def _safe_eval(formula: str, col_data: dict) -> np.ndarray:
    """Safely evaluate a formula with column names as variables."""
    # Check for dangerous patterns
    forbidden = ["import","exec","eval","open","os","sys","__","subprocess","builtins"]
    for f in forbidden:
        if f in formula.lower():
            raise ValueError(f"Forbidden expression: '{f}'")
    namespace = {**SAFE_NAMES, **col_data}
    result = eval(formula, {"__builtins__": {}}, namespace)  # noqa
    if isinstance(result, (int, float)):
        # Scalar — broadcast to array length
        n = max(len(v) for v in col_data.values() if hasattr(v,'__len__')) if col_data else 1
        result = np.full(n, float(result))
    return np.array(result, dtype=float)

def calculate_column(
    df: pd.DataFrame,
    formula: str,
    new_col_name: str = "Calculated",
) -> CalcResult:
    """
    Calculate a new column from a formula referencing existing column names.
    Example formulas:
      "Etch_Rate / Thickness"
      "log(Particle_Count + 1)"
      "rolling_mean(Etch_Rate, 5)"
      "zscore(CD_nm)"
      "(Etch_Rate - 450) / 8"
    """
    col_data = {col: df[col].values.astype(float) for col in df.columns}
    try:
        result = _safe_eval(formula, col_data)
        # Pad or trim to df length
        n = len(df)
        if len(result) < n:
            result = np.pad(result, (0, n - len(result)), constant_values=np.nan)
        elif len(result) > n:
            result = result[:n]
        result = result.astype(float)
        n_nan = int(np.sum(np.isnan(result)))
        clean = result[~np.isnan(result)]
        return CalcResult(
            new_column_name=new_col_name,
            formula=formula,
            n_values=n,
            sample_values=[round(float(v), 6) for v in result[:10]],
            mean=round(float(np.mean(clean)), 6) if len(clean) > 0 else 0,
            std=round(float(np.std(clean, ddof=1)), 6) if len(clean) > 1 else 0,
            min_val=round(float(np.min(clean)), 6) if len(clean) > 0 else 0,
            max_val=round(float(np.max(clean)), 6) if len(clean) > 0 else 0,
            n_nan=n_nan,
            success=True, error="",
            transformed_data=result.tolist(),
        )
    except Exception as e:
        return CalcResult(
            new_column_name=new_col_name, formula=formula, n_values=0,
            sample_values=[], mean=0, std=0, min_val=0, max_val=0, n_nan=0,
            success=False, error=str(e), transformed_data=[],
        )

FORMULA_TEMPLATES = [
    {"name": "Z-score (standardize)", "formula": "zscore({col})", "description": "Center and scale: (x - mean) / std"},
    {"name": "Log transform", "formula": "log({col})", "description": "Natural log — use for right-skewed data"},
    {"name": "Log10", "formula": "log10({col})", "description": "Base-10 log"},
    {"name": "Square root", "formula": "sqrt({col})", "description": "Mild transformation for count data"},
    {"name": "Normalize 0-1", "formula": "normalize({col})", "description": "Scale to [0,1] range"},
    {"name": "Rolling mean (5)", "formula": "rolling_mean({col}, 5)", "description": "5-point moving average"},
    {"name": "Rolling std (5)", "formula": "rolling_std({col}, 5)", "description": "5-point rolling standard deviation"},
    {"name": "Ratio", "formula": "{col1} / {col2}", "description": "Ratio of two columns"},
    {"name": "Percent of mean", "formula": "({col} / mean({col})) * 100", "description": "Express as % of column mean"},
    {"name": "Deviation from target", "formula": "{col} - {target}", "description": "Distance from a target value"},
    {"name": "Clip outliers (3σ)", "formula": "clip({col}, mean({col})-3*std({col}), mean({col})+3*std({col}))", "description": "Clip values beyond ±3σ"},
    {"name": "First difference", "formula": "diff({col})", "description": "Consecutive differences (removes trends)"},
    {"name": "Rank", "formula": "rank({col})", "description": "Rank order (1=smallest)"},
    {"name": "Power", "formula": "power({col}, 0.5)", "description": "Raise to a power (0.5=sqrt, 2=square)"},
]
