import pandas as pd
"""
StatMind N13 — Time Series Analysis
Trend detection, seasonality decomposition, autocorrelation plots,
Moving average, exponential smoothing (simple + Holt-Winters).
References: Box-Jenkins, Cleveland STL decomposition
"""
import numpy as np
from scipy import stats, signal
from dataclasses import dataclass
from typing import Optional
import warnings; warnings.filterwarnings("ignore")

@dataclass
class TimeSeriesResult:
    column: str
    n: int
    # Trend
    trend_slope: float          # units per observation
    trend_slope_sigma: float    # in sigma units per 10 obs
    trend_p_value: float
    trend_significant: bool
    trend_direction: str        # "Increasing","Decreasing","No trend"
    trend_magnitude: str        # "Strong","Moderate","Weak"
    # Decomposition (STL-style additive)
    trend_component: list
    seasonal_component: list
    residual_component: list
    period_estimate: int        # estimated season length
    # Autocorrelation
    acf: list                   # autocorrelation function values
    pacf: list                  # partial ACF values
    acf_lags: list
    acf_ci: float               # 95% CI bound = 1.96/sqrt(n)
    # Stationarity
    adf_stat: float             # Augmented Dickey-Fuller test statistic
    adf_p: float
    is_stationary: bool
    # Forecasting (simple exponential smoothing)
    alpha_ses: float
    ses_fitted: list
    ses_forecast: list          # next 10 points
    # Moving average
    ma_period: int
    ma_values: list
    # Chart data
    chart_data: dict
    conclusion: str

def _acf_values(x, max_lag=20):
    """Compute ACF and PACF."""
    n = len(x)
    x_c = x - np.mean(x)
    var = np.var(x_c)
    acf = []
    for lag in range(max_lag+1):
        if lag == 0:
            acf.append(1.0)
        else:
            c = float(np.mean(x_c[:n-lag] * x_c[lag:]) / (var + 1e-12))
            acf.append(round(c, 5))
    # PACF via Yule-Walker (simplified)
    pacf = [1.0]
    for k in range(1, min(max_lag, n//3)):
        try:
            R = np.array([[acf[abs(i-j)] for j in range(k)] for i in range(k)])
            r = np.array([acf[i+1] for i in range(k)])
            phi = np.linalg.solve(R + np.eye(k)*1e-9, r)
            pacf.append(round(float(phi[-1]), 5))
        except Exception:
            pacf.append(0.0)
    while len(pacf) <= max_lag:
        pacf.append(0.0)
    return acf, pacf

def _adf_test(x):
    """Simplified ADF test (regression-based)."""
    n = len(x)
    dx = np.diff(x)
    xlag = x[:-1]
    # Regress Δx on x_{t-1}
    A = np.column_stack([xlag, np.ones(n-1)])
    try:
        b, res, *_ = np.linalg.lstsq(A, dx, rcond=None)
        e = dx - A @ b
        se = np.sqrt(np.sum(e**2) / (n-3) * np.linalg.inv(A.T @ A)[0,0])
        t_stat = float(b[0] / (se + 1e-12))
        # Approximate p-value (MacKinnon critical values approximation)
        # ADF critical values for no trend, n→∞: -3.43 (1%), -2.86 (5%), -2.57 (10%)
        if t_stat < -3.43: p = 0.01
        elif t_stat < -2.86: p = 0.05
        elif t_stat < -2.57: p = 0.10
        else: p = 0.50
        return t_stat, p
    except Exception:
        return 0.0, 0.5

def _seasonal_decompose(x, period):
    """Additive decomposition."""
    n = len(x)
    # Trend: centered moving average
    if period % 2 == 0:
        w = np.concatenate([[0.5], np.ones(period-1), [0.5]]) / period
    else:
        w = np.ones(period) / period
    trend = np.convolve(x, w, mode='same')
    # Smooth ends
    half = period // 2
    for i in range(half): trend[i] = np.mean(x[:i*2+1]) if i > 0 else x[0]
    for i in range(half): trend[n-1-i] = np.mean(x[n-i*2-1:]) if i > 0 else x[-1]
    # Seasonal: average detrended by phase
    detrended = x - trend
    seasonal = np.zeros(n)
    for phase in range(period):
        indices = np.arange(phase, n, period)
        avg = float(np.mean(detrended[indices]))
        for idx in indices:
            seasonal[idx] = avg
    residual = x - trend - seasonal
    return trend, seasonal, residual

def _ses_forecast(x, alpha=None, n_ahead=10):
    """Simple exponential smoothing with optional alpha optimization."""
    if alpha is None:
        # Optimize alpha by minimizing SSE
        best_alpha, best_sse = 0.2, float('inf')
        for a in np.arange(0.05, 1.0, 0.05):
            level = x[0]
            sse = 0
            for xt in x[1:]:
                err = xt - level
                sse += err**2
                level = a * xt + (1-a) * level
            if sse < best_sse:
                best_sse = sse
                best_alpha = float(a)
        alpha = best_alpha

    fitted = [float(x[0])]
    level = float(x[0])
    for xt in x[1:]:
        level = alpha * float(xt) + (1-alpha) * level
        fitted.append(round(level, 6))
    forecast = [round(level, 6)] * n_ahead
    return fitted, forecast, alpha

def analyze_timeseries(
    data: np.ndarray,
    column: str = "Measurement",
    period: int = None,     # seasonal period (None = auto-detect)
    n_forecast: int = 10,
) -> TimeSeriesResult:
    data = data[~np.isnan(data)].astype(float)
    n = len(data)
    if n < 10: raise ValueError("Need ≥ 10 data points for time series analysis.")

    # ── Trend ─────────────────────────────────────────────────────────────────
    x_idx = np.arange(n)
    slope, intercept, r, p, se = stats.linregress(x_idx, data)
    slope_sigma = float(slope * 10 / (np.std(data, ddof=1) + 1e-12))
    trend_sig = bool(p < 0.05)
    trend_dir = "No trend" if not trend_sig else ("Increasing" if slope > 0 else "Decreasing")
    trend_mag = "Strong" if abs(slope_sigma) > 1 else "Moderate" if abs(slope_sigma) > 0.3 else "Weak"

    # ── Period estimation ─────────────────────────────────────────────────────
    if period is None and n >= 20:
        # FFT-based period estimate
        fft = np.abs(np.fft.fft(data - np.mean(data)))
        freqs = np.fft.fftfreq(n)
        pos_mask = freqs > 0
        dominant_freq = float(freqs[pos_mask][np.argmax(fft[pos_mask])])
        period_est = int(round(1/dominant_freq)) if dominant_freq > 0 else n
        period = max(2, min(period_est, n//4))
    elif period is None:
        period = 4

    # ── Decomposition ─────────────────────────────────────────────────────────
    trend_comp, seasonal_comp, residual_comp = _seasonal_decompose(data, period)

    # ── ACF / PACF ────────────────────────────────────────────────────────────
    max_lag = min(20, n//3)
    acf, pacf = _acf_values(data, max_lag)
    acf_ci = float(1.96 / np.sqrt(n))

    # ── ADF stationarity test ─────────────────────────────────────────────────
    adf_stat, adf_p = _adf_test(data)
    is_stationary = bool(adf_p < 0.05)

    # ── Simple Exponential Smoothing ─────────────────────────────────────────
    ses_fitted, ses_forecast, alpha_ses = _ses_forecast(data, None, n_forecast)

    # ── Moving average ────────────────────────────────────────────────────────
    ma_p = max(3, min(period, n//5))
    import pandas as _pd
    ma_vals = _pd.Series(data).rolling(ma_p, min_periods=1).mean().tolist()

    # Chart data
    chart_data = {
        "values": data.tolist(),
        "index": list(range(n)),
        "trend_line": (slope * x_idx + intercept).tolist(),
        "trend_component": trend_comp.tolist(),
        "seasonal_component": seasonal_comp.tolist(),
        "residual_component": residual_comp.tolist(),
        "acf": acf, "pacf": pacf[:max_lag+1],
        "acf_lags": list(range(max_lag+1)),
        "acf_ci": acf_ci,
        "ses_fitted": ses_fitted,
        "ses_forecast_start": n,
        "ses_forecast": ses_forecast,
        "ma_values": [round(float(v),5) for v in ma_vals],
        "ma_period": ma_p,
        "period_estimate": period,
        "slope": round(float(slope),6),
        "trend_significant": trend_sig,
    }

    # Import pandas here since it's used for rolling
    import pandas as pd
    import pandas as _pd
    ma_vals = list(_pd.Series(data).rolling(ma_p, min_periods=1).mean().round(5))
    chart_data['ma_values'] = [float(v) for v in ma_vals]

    conclusion = (
        f"Time series of {n} observations. "
        f"Trend: {trend_dir} ({trend_mag}, slope={slope:+.4f}/obs, p={p:.4f}). "
        f"Seasonality period estimate: {period} obs. "
        f"Stationarity: {'Stationary' if is_stationary else 'Non-stationary'} (ADF p={adf_p:.3f}). "
        f"SES α={alpha_ses:.2f}, 10-step forecast: {ses_forecast[0]:.4f}. "
        + (f"Significant autocorrelation at lag 1 (r={acf[1]:.3f}) — consider differencing." if abs(acf[1]) > acf_ci else "No significant autocorrelation at lag 1.")
    )

    return TimeSeriesResult(
        column=column, n=n,
        trend_slope=round(float(slope),6),
        trend_slope_sigma=round(slope_sigma,4),
        trend_p_value=round(float(p),5),
        trend_significant=trend_sig,
        trend_direction=trend_dir,
        trend_magnitude=trend_mag,
        trend_component=[round(float(v),5) for v in trend_comp],
        seasonal_component=[round(float(v),5) for v in seasonal_comp],
        residual_component=[round(float(v),5) for v in residual_comp],
        period_estimate=period,
        acf=[round(float(v),5) for v in acf],
        pacf=[round(float(v),5) for v in pacf[:max_lag+1]],
        acf_lags=list(range(max_lag+1)),
        acf_ci=round(acf_ci,5),
        adf_stat=round(float(adf_stat),5),
        adf_p=round(float(adf_p),4),
        is_stationary=is_stationary,
        alpha_ses=round(alpha_ses,4),
        ses_fitted=[round(float(v),5) for v in ses_fitted],
        ses_forecast=[round(float(v),5) for v in ses_forecast],
        ma_period=ma_p,
        ma_values=[round(float(v),5) for v in ma_vals],
        chart_data=chart_data,
        conclusion=conclusion,
    )


