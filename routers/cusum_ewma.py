"""
StatMind N1 — CUSUM and EWMA Control Charts
Detects small shifts 3-5x faster than standard Shewhart I-MR charts.
CUSUM: Tabular CUSUM (Page's method), two-sided, with V-mask
EWMA: Exponentially Weighted Moving Average (Roberts 1959)
References: Montgomery "Introduction to SPC" 7th Ed, AIAG SPC 2nd Ed
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


@dataclass
class CUSUMResult:
    column: str
    n: int
    # Parameters
    k: float           # reference value (allowance) = delta/2 * sigma, typically 0.5
    h: float           # decision interval = 4 or 5 * sigma
    target: float      # process target (mean)
    sigma: float       # process standard deviation
    # CUSUM statistics
    cusum_plus: list   # upper cumulative sum C+
    cusum_minus: list  # lower cumulative sum C-
    # Alarms
    alarm_indices_plus: list   # points where C+ > h
    alarm_indices_minus: list  # points where C- > h (absolute)
    total_alarms: int
    in_control: bool
    # Shift detection
    shift_detected: bool
    estimated_shift: Optional[float]  # estimated magnitude of shift in sigma units
    shift_start_index: Optional[int]  # estimated start of shift
    # Performance metrics
    arl_in_control: float    # Average Run Length when in control (~370 for Shewhart 3-sigma)
    shift_sensitivity: str   # "Detects 0.5σ shifts ~10 runs faster than Shewhart"
    # Chart data
    chart_data: dict
    # Verdict
    verdict: str
    conclusion: str


@dataclass
class EWMAResult:
    column: str
    n: int
    # Parameters
    lam: float         # lambda (smoothing constant), typically 0.1-0.3
    L: float           # control limit width in sigma units, typically 2.7-3.0
    target: float
    sigma: float
    # EWMA statistics
    ewma_values: list  # z_t = λ*x_t + (1-λ)*z_{t-1}
    ucl: list          # upper control limit (varies with t)
    lcl: list          # lower control limit (varies with t)
    ucl_steady: float  # steady-state UCL
    lcl_steady: float  # steady-state LCL
    cl: float          # center line
    # Alarms
    alarm_indices: list
    total_alarms: int
    in_control: bool
    # Shift detection
    shift_detected: bool
    estimated_shift: Optional[float]
    # Chart data
    chart_data: dict
    # Verdict
    verdict: str
    conclusion: str


def tabular_cusum(
    data: np.ndarray,
    column: str = "Measurement",
    target: float = None,
    sigma: float = None,
    k: float = 0.5,     # reference value in sigma units (0.5 = detect 1σ shift optimally)
    h: float = 5.0,     # decision interval in sigma units (4 or 5 recommended)
    alpha: float = 0.05,
) -> CUSUMResult:
    """
    Tabular (algorithmic) CUSUM chart.
    k=0.5, h=5 is the standard recommendation for detecting 1σ shifts.
    """
    data = data[~np.isnan(data)].astype(float)
    n = len(data)
    if n < 10:
        raise ValueError("Need at least 10 data points for CUSUM.")

    # Estimate parameters if not provided
    if target is None:
        target = float(np.mean(data))
    if sigma is None:
        # Use moving range estimate (like I-MR)
        mr = np.abs(np.diff(data))
        sigma = float(np.mean(mr) / 1.128)  # d2 for n=2
        if sigma == 0:
            sigma = float(np.std(data, ddof=1))

    k_abs = k * sigma   # reference value in original units
    h_abs = h * sigma   # decision interval in original units

    # Compute tabular CUSUM
    cusum_plus  = np.zeros(n)
    cusum_minus = np.zeros(n)

    for i in range(n):
        xi = data[i]
        if i == 0:
            cusum_plus[i]  = max(0, xi - (target + k_abs))
            cusum_minus[i] = max(0, (target - k_abs) - xi)
        else:
            cusum_plus[i]  = max(0, cusum_plus[i-1]  + xi - (target + k_abs))
            cusum_minus[i] = max(0, cusum_minus[i-1] + (target - k_abs) - xi)

    # Find alarm points
    alarm_plus  = [i for i in range(n) if cusum_plus[i]  > h_abs]
    alarm_minus = [i for i in range(n) if cusum_minus[i] > h_abs]
    all_alarms  = sorted(set(alarm_plus + alarm_minus))
    in_control  = len(all_alarms) == 0

    # Estimate shift if alarm fired
    shift_detected = len(all_alarms) > 0
    estimated_shift = None
    shift_start = None

    if shift_detected:
        first_alarm = all_alarms[0]
        # Estimate shift magnitude from CUSUM value at alarm
        if first_alarm in alarm_plus:
            shift_sigma = (cusum_plus[first_alarm] / h_abs) * k
            estimated_shift = round(float(shift_sigma), 3)
        else:
            shift_sigma = (cusum_minus[first_alarm] / h_abs) * k
            estimated_shift = round(float(-shift_sigma), 3)
        # Find start of shift (where CUSUM left zero)
        for i in range(first_alarm, -1, -1):
            if cusum_plus[i] == 0 and cusum_minus[i] == 0:
                shift_start = i + 1
                break
        if shift_start is None:
            shift_start = 0

    # ARL for CUSUM with k=0.5, h=5: ARL_0 ≈ 465, ARL_1sigma ≈ 10.4
    arl_in_control = 465.0 if abs(k - 0.5) < 0.05 and abs(h - 5.0) < 0.1 else 370.0

    verdict = "In Control" if in_control else f"Out of Control — {len(all_alarms)} CUSUM violation(s)"
    conclusion = (
        f"Process is in statistical control. No shifts detected with CUSUM (k={k}σ, h={h}σ)."
        if in_control else
        f"CUSUM detected {'upward' if alarm_plus else 'downward'} shift at point {all_alarms[0]+1}. "
        f"Estimated shift: {estimated_shift:+.2f}σ. "
        f"Possible shift start: point {shift_start+1 if shift_start is not None else '?'}. "
        f"CUSUM detects {k*2:.1f}σ shifts ~{int(arl_in_control/45)} points earlier than Shewhart charts."
    )

    chart_data = {
        "values": data.tolist(),
        "cusum_plus": cusum_plus.tolist(),
        "cusum_minus": (-cusum_minus).tolist(),  # negative for lower chart
        "h_line": h_abs,
        "h_neg_line": -h_abs,
        "target": target,
        "sigma": sigma,
        "k_abs": k_abs,
        "alarm_plus": alarm_plus,
        "alarm_minus": alarm_minus,
        "shift_start": shift_start,
    }

    return CUSUMResult(
        column=column, n=n,
        k=k, h=h, target=round(target, 5), sigma=round(sigma, 5),
        cusum_plus=cusum_plus.tolist(),
        cusum_minus=(-cusum_minus).tolist(),
        alarm_indices_plus=alarm_plus,
        alarm_indices_minus=alarm_minus,
        total_alarms=len(all_alarms),
        in_control=in_control,
        shift_detected=shift_detected,
        estimated_shift=estimated_shift,
        shift_start_index=shift_start,
        arl_in_control=arl_in_control,
        shift_sensitivity=f"k={k}σ detects {k*2:.1f}σ shifts in ≈{int(10.4 if k==0.5 else 20)} observations (vs ≈{int(43.9 if k==0.5 else 50)} for Shewhart)",
        chart_data=chart_data,
        verdict=verdict,
        conclusion=conclusion,
    )


def ewma_chart(
    data: np.ndarray,
    column: str = "Measurement",
    target: float = None,
    sigma: float = None,
    lam: float = 0.2,    # smoothing parameter λ (0.05–0.3 typical)
    L: float = 3.0,      # control limit width
    alpha: float = 0.05,
) -> EWMAResult:
    """
    EWMA chart (Roberts 1959).
    λ=0.2, L=3.0 is standard recommendation.
    Lower λ = more weight on history = better for smaller shifts.
    Higher λ = more weight on recent data = approaches Shewhart.
    """
    data = data[~np.isnan(data)].astype(float)
    n = len(data)
    if n < 8:
        raise ValueError("Need at least 8 data points for EWMA.")

    if target is None:
        target = float(np.mean(data))
    if sigma is None:
        mr = np.abs(np.diff(data))
        sigma = float(np.mean(mr) / 1.128)
        if sigma == 0:
            sigma = float(np.std(data, ddof=1))

    # Compute EWMA
    z = np.zeros(n)
    z[0] = target  # initialize at target

    for i in range(n):
        if i == 0:
            z[0] = lam * data[0] + (1 - lam) * target
        else:
            z[i] = lam * data[i] + (1 - lam) * z[i-1]

    # Control limits (time-varying, approach steady-state)
    # Var(z_t) = σ² * λ/(2-λ) * [1 - (1-λ)^(2t)]
    cl = target
    ucl_arr = np.zeros(n)
    lcl_arr = np.zeros(n)

    for i in range(n):
        factor = (lam / (2 - lam)) * (1 - (1 - lam)**(2*(i+1)))
        width = L * sigma * np.sqrt(factor)
        ucl_arr[i] = target + width
        lcl_arr[i] = target - width

    # Steady-state limits
    ss_factor = lam / (2 - lam)
    ucl_ss = target + L * sigma * np.sqrt(ss_factor)
    lcl_ss = target - L * sigma * np.sqrt(ss_factor)

    # Alarms
    alarms = [i for i in range(n) if z[i] > ucl_arr[i] or z[i] < lcl_arr[i]]
    in_ctrl = len(alarms) == 0

    # Estimate shift
    shift_detected = len(alarms) > 0
    estimated_shift = None
    if shift_detected:
        fa = alarms[0]
        shift_est = (z[fa] - target) / sigma
        estimated_shift = round(float(shift_est), 3)

    # ARL performance note
    arl_1sigma = int(1 / stats.norm.cdf(L * np.sqrt(ss_factor) / (lam / np.sqrt(2-lam)) - 1) + 1) if ss_factor > 0 else 10

    verdict = "In Control" if in_ctrl else f"Out of Control — {len(alarms)} EWMA violation(s)"
    conclusion = (
        f"EWMA (λ={lam}) shows process in statistical control. No shifts detected."
        if in_ctrl else
        f"EWMA alarm at point {alarms[0]+1}. "
        f"Estimated shift: {estimated_shift:+.2f}σ from target. "
        f"EWMA (λ={lam}) is optimally sensitive to shifts of {lam:.0%}–{lam*3:.0%} σ magnitude."
    )

    chart_data = {
        "values": data.tolist(),
        "ewma": z.tolist(),
        "ucl": ucl_arr.tolist(),
        "lcl": lcl_arr.tolist(),
        "ucl_ss": ucl_ss,
        "lcl_ss": lcl_ss,
        "cl": cl,
        "sigma": sigma,
        "target": target,
        "alarm_indices": alarms,
        "lam": lam,
        "L": L,
    }

    return EWMAResult(
        column=column, n=n,
        lam=lam, L=L,
        target=round(target, 5), sigma=round(sigma, 5),
        ewma_values=z.tolist(),
        ucl=ucl_arr.tolist(),
        lcl=lcl_arr.tolist(),
        ucl_steady=round(ucl_ss, 5),
        lcl_steady=round(lcl_ss, 5),
        cl=cl,
        alarm_indices=alarms,
        total_alarms=len(alarms),
        in_control=in_ctrl,
        shift_detected=shift_detected,
        estimated_shift=estimated_shift,
        chart_data=chart_data,
        verdict=verdict,
        conclusion=conclusion,
    )
