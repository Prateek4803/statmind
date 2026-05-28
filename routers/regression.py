"""
StatMind E4 — Regression Analysis Engine
Simple linear + multiple regression
R², residuals, prediction equation, fitted line data
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RegressionResult:
    model_type: str          # "Simple Linear" or "Multiple"
    y_name: str
    x_names: list
    # Model fit
    r_squared: float
    adj_r_squared: float
    rmse: float
    # F-test
    f_stat: float
    f_p_value: float
    model_significant: bool
    # Coefficients
    intercept: float
    intercept_p: float
    coefficients: list       # [{"name","coef","std_err","t_stat","p_value","significant"}]
    # Equation string
    equation: str
    # Residual diagnostics
    residuals_normal: bool   # SW p-value on residuals
    residuals_sw_p: float
    # Prediction
    prediction_note: str
    # Chart data
    fitted_values: list
    residuals: list
    actual_values: list
    chart_data: dict
    # Plain English
    conclusion: str
    practical_significance: str


def simple_linear_regression(
    x: np.ndarray, y: np.ndarray,
    x_name: str = "X", y_name: str = "Y",
    alpha: float = 0.05,
) -> RegressionResult:
    """Simple linear regression: Y = β₀ + β₁X"""
    mask = ~(np.isnan(x) | np.isnan(y))
    x, y = x[mask].astype(float), y[mask].astype(float)
    n = len(x)
    if n < 5:
        raise ValueError("Need at least 5 data points for regression.")

    slope, intercept, r, p_val, se = stats.linregress(x, y)
    r2 = r**2
    fitted = intercept + slope * x
    residuals = y - fitted
    ss_res = np.sum(residuals**2)
    ss_tot = np.sum((y - np.mean(y))**2)
    rmse = float(np.sqrt(ss_res / (n-2)))
    adj_r2 = 1 - (1-r2)*(n-1)/(n-2)

    # t-stat and p for slope
    t_slope = float(slope / se)
    # F-stat = t² for simple regression
    f_stat  = float(t_slope**2)
    f_p     = float(p_val)

    # Intercept SE
    se_int = rmse * np.sqrt(np.sum(x**2) / (n * np.sum((x-np.mean(x))**2)))
    t_int  = float(intercept / se_int) if se_int > 0 else 0
    p_int  = float(2 * stats.t.sf(abs(t_int), df=n-2))

    # Residual normality
    _, sw_p = stats.shapiro(residuals)
    res_normal = float(sw_p) > alpha

    sign = '+' if slope >= 0 else '-'
    equation = f"{y_name} = {intercept:.4f} {sign} {abs(slope):.4f} × {x_name}"
    sig = float(p_val) < alpha

    conclusion = (
        f"{x_name} IS a significant predictor of {y_name} "
        f"(p={float(p_val):.4f}, R²={r2:.4f}). "
        f"For every 1-unit increase in {x_name}, {y_name} {'increases' if slope>0 else 'decreases'} by {abs(slope):.4f}."
        if sig else
        f"{x_name} is NOT a significant predictor of {y_name} "
        f"(p={float(p_val):.4f}). Insufficient evidence of a linear relationship."
    )
    practical = (
        f"R² = {r2:.4f} — the model explains {r2*100:.1f}% of the variation in {y_name}. "
        + ("Strong fit." if r2>0.7 else "Moderate fit — other factors also influence the response." if r2>0.4 else "Weak fit — consider other predictors or non-linear models.")
    )

    # Fitted line chart data
    x_sorted = np.sort(x)
    y_fitted_sorted = intercept + slope * x_sorted
    ci_band = stats.t.ppf(1-alpha/2, df=n-2) * rmse * np.sqrt(1/n + (x_sorted-np.mean(x))**2/np.sum((x-np.mean(x))**2))

    return RegressionResult(
        model_type="Simple Linear Regression",
        y_name=y_name, x_names=[x_name],
        r_squared=round(r2,5), adj_r_squared=round(adj_r2,5), rmse=round(rmse,5),
        f_stat=round(f_stat,4), f_p_value=round(float(p_val),5),
        model_significant=sig,
        intercept=round(float(intercept),6), intercept_p=round(p_int,5),
        coefficients=[{
            "name": x_name,
            "coef": round(float(slope),6),
            "std_err": round(float(se),6),
            "t_stat": round(t_slope,4),
            "p_value": round(float(p_val),5),
            "significant": sig,
        }],
        equation=equation,
        residuals_normal=res_normal, residuals_sw_p=round(float(sw_p),5),
        prediction_note=f"Prediction interval (95%) width ≈ ±{1.96*rmse:.4f} around fitted line.",
        fitted_values=fitted.tolist(), residuals=residuals.tolist(),
        actual_values=y.tolist(),
        chart_data={
            "type": "simple_linear",
            "x": x.tolist(), "y": y.tolist(),
            "fitted_x": x_sorted.tolist(),
            "fitted_y": y_fitted_sorted.tolist(),
            "ci_upper": (y_fitted_sorted + ci_band).tolist(),
            "ci_lower": (y_fitted_sorted - ci_band).tolist(),
            "residuals": residuals.tolist(),
            "fitted_for_residuals": fitted.tolist(),
            "x_name": x_name, "y_name": y_name,
        },
        conclusion=conclusion, practical_significance=practical,
    )


def multiple_regression(
    X: np.ndarray, y: np.ndarray,
    x_names: list = None, y_name: str = "Y",
    alpha: float = 0.05,
) -> RegressionResult:
    """Multiple linear regression using numpy OLS."""
    # Drop rows with NaN
    mask = ~np.isnan(y)
    for col in range(X.shape[1]):
        mask &= ~np.isnan(X[:, col])
    X, y = X[mask].astype(float), y[mask].astype(float)
    n, k = X.shape
    if x_names is None:
        x_names = [f"X{i+1}" for i in range(k)]
    if n < k + 5:
        raise ValueError(f"Need at least {k+5} observations for {k} predictors.")

    # Add intercept column
    X_aug = np.column_stack([np.ones(n), X])
    # OLS: β = (X'X)⁻¹ X'y
    try:
        beta = np.linalg.lstsq(X_aug, y, rcond=None)[0]
    except Exception as e:
        raise ValueError(f"Regression failed — possible multicollinearity: {e}")

    fitted    = X_aug @ beta
    residuals = y - fitted
    ss_res    = float(np.sum(residuals**2))
    ss_tot    = float(np.sum((y - np.mean(y))**2))
    ss_reg    = ss_tot - ss_res
    r2        = 1 - ss_res/ss_tot if ss_tot > 0 else 0.0
    adj_r2    = 1 - (1-r2)*(n-1)/(n-k-1)
    rmse      = float(np.sqrt(ss_res/(n-k-1)))
    f_stat    = float((ss_reg/k) / (ss_res/(n-k-1))) if ss_res > 0 else 0
    f_p       = float(1 - stats.f.cdf(f_stat, k, n-k-1))

    # SE of coefficients
    try:
        var_beta = rmse**2 * np.linalg.inv(X_aug.T @ X_aug)
        se_beta  = np.sqrt(np.diag(var_beta))
    except Exception:
        se_beta = np.zeros(k+1)

    t_stats = beta / (se_beta + 1e-12)
    p_vals  = [float(2 * stats.t.sf(abs(t), df=n-k-1)) for t in t_stats]

    coefficients = []
    for i in range(k):
        coefficients.append({
            "name":        x_names[i],
            "coef":        round(float(beta[i+1]), 6),
            "std_err":     round(float(se_beta[i+1]), 6),
            "t_stat":      round(float(t_stats[i+1]), 4),
            "p_value":     round(p_vals[i+1], 5),
            "significant": p_vals[i+1] < alpha,
        })

    # Build equation string
    terms = [f"{c['coef']:+.4f}×{c['name']}" for c in coefficients]
    equation = f"{y_name} = {beta[0]:.4f} " + " ".join(terms)

    # Residual normality
    _, sw_p = stats.shapiro(residuals[:min(len(residuals), 5000)])
    res_normal = float(sw_p) > alpha

    sig_predictors = [c["name"] for c in coefficients if c["significant"]]
    conclusion = (
        f"The overall model IS significant (F={f_stat:.3f}, p={f_p:.4f}, R²={r2:.4f}). "
        f"Significant predictors: {', '.join(sig_predictors) if sig_predictors else 'None at α={alpha}'}."
        if f_p < alpha else
        f"The overall model is NOT significant (F={f_stat:.3f}, p={f_p:.4f}). "
        f"None of the predictors explain significant variation in {y_name}."
    )
    practical = (
        f"Adjusted R² = {adj_r2:.4f} — model explains {adj_r2*100:.1f}% of variation. "
        + ("Strong model." if adj_r2>0.7 else "Moderate model." if adj_r2>0.4 else "Weak model — consider adding predictors or transformations.")
    )

    return RegressionResult(
        model_type="Multiple Linear Regression",
        y_name=y_name, x_names=x_names,
        r_squared=round(r2,5), adj_r_squared=round(adj_r2,5), rmse=round(rmse,5),
        f_stat=round(f_stat,4), f_p_value=round(f_p,5),
        model_significant=bool(f_p < alpha),
        intercept=round(float(beta[0]),6), intercept_p=round(p_vals[0],5),
        coefficients=coefficients, equation=equation,
        residuals_normal=res_normal, residuals_sw_p=round(float(sw_p),5),
        prediction_note=f"RMSE = {rmse:.4f}. Use equation above for point predictions.",
        fitted_values=fitted.tolist(), residuals=residuals.tolist(),
        actual_values=y.tolist(),
        chart_data={
            "type": "multiple",
            "fitted": fitted.tolist(), "actual": y.tolist(),
            "residuals": residuals.tolist(), "y_name": y_name,
        },
        conclusion=conclusion, practical_significance=practical,
    )
