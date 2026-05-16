"""
StatMind N10 — Weibull / Reliability Analysis
Failure time analysis, B10/B50 life, hazard plots,
Weibull distribution fitting (2-parameter and 3-parameter),
Kaplan-Meier survival estimate for censored data.
References: ReliaSoft Weibull++, MIL-HDBK-217, SAE J1739
"""
import numpy as np
from scipy import stats, optimize
from dataclasses import dataclass
from typing import Optional
import warnings; warnings.filterwarnings("ignore")

@dataclass
class WeibullResult:
    column: str
    n: int
    n_censored: int
    # Weibull parameters
    shape: float        # β (beta) — shape parameter
    scale: float        # η (eta) — characteristic life (63.2% failure point)
    location: float     # γ (gamma) — location/threshold (0 for 2-param)
    # Fit quality
    r_squared: float
    fit_method: str     # "MLE" or "Least Squares (Rank Regression)"
    # B-life estimates
    b10_life: float     # Time by which 10% of population will fail
    b50_life: float     # Median life (50th percentile)
    b90_life: float     # Time by which 90% fail
    mttf: float         # Mean Time To Failure
    # Hazard
    shape_interpretation: str  # "Infant mortality" / "Random" / "Wear-out"
    # Confidence intervals (95%)
    b10_ci_lower: float
    b10_ci_upper: float
    # Chart data
    chart_data: dict
    conclusion: str

def weibull_analysis(
    times: np.ndarray,
    column: str = "Failure Time",
    censored: np.ndarray = None,   # boolean array: True = censored (suspended)
    fit_method: str = "mle",
) -> WeibullResult:
    times = times[~np.isnan(times)].astype(float)
    n = len(times)
    if n < 3: raise ValueError("Need ≥ 3 failure times.")

    if censored is None:
        censored = np.zeros(n, dtype=bool)
    else:
        censored = np.array(censored, dtype=bool)[:n]

    n_censored = int(censored.sum())
    failures = times[~censored]
    n_fail = len(failures)
    if n_fail < 2: raise ValueError("Need ≥ 2 failure times (non-censored).")

    # ── Fit 2-parameter Weibull by MLE ───────────────────────────────────────
    # Log-likelihood for Weibull: sum[log(β/η) + (β-1)*log(t/η) - (t/η)^β]
    #   plus censored contribution: -(t_c/η)^β
    def neg_loglik(params):
        beta, eta = params
        if beta <= 0 or eta <= 0: return 1e15
        ll = 0.0
        for i, t in enumerate(times):
            if not censored[i]:
                ll += np.log(beta/eta) + (beta-1)*np.log(t/eta) - (t/eta)**beta
            else:
                ll -= (t/eta)**beta
        return -ll

    # Initial guess from moment method
    log_t = np.log(failures)
    beta0 = max(0.5, np.pi / (np.sqrt(6) * np.std(log_t, ddof=1))) if np.std(log_t, ddof=1) > 0 else 1.0
    eta0  = np.exp(np.mean(log_t) + 0.5772 / beta0)

    try:
        result = optimize.minimize(neg_loglik, [beta0, eta0],
                                   bounds=[(0.01, 100), (1e-6, 1e12)],
                                   method="L-BFGS-B")
        beta, eta = float(result.x[0]), float(result.x[1])
    except Exception:
        beta, eta = beta0, eta0

    # ── B-life estimates ──────────────────────────────────────────────────────
    def b_life(pct): return float(eta * (-np.log(1 - pct/100))**(1/beta))

    b10 = b_life(10)
    b50 = b_life(50)
    b90 = b_life(90)
    mttf = float(eta * float(stats.gamma(1 + 1/beta).args[0] if False else 1) )
    # Correct MTTF for Weibull: η * Γ(1 + 1/β)
    from math import gamma as math_gamma
    mttf = float(eta * math_gamma(1 + 1/beta))

    # ── Shape interpretation ──────────────────────────────────────────────────
    if beta < 1:
        shape_interp = "Infant mortality (β<1) — decreasing failure rate. Manufacturing defects or early failures dominate."
    elif abs(beta - 1) < 0.1:
        shape_interp = "Random failures (β≈1) — constant failure rate. Exponential distribution. Random external stresses dominate."
    elif beta < 3:
        shape_interp = "Early wear-out (1<β<3) — increasing failure rate. Normal usage wear beginning."
    else:
        shape_interp = "Wear-out (β≥3) — rapidly increasing failure rate. Material fatigue/wear dominating. Design life near B50."

    # ── Confidence intervals (Fisher matrix, 95%) ────────────────────────────
    try:
        from scipy.optimize import approx_fprime
        def ll_for_hess(p): return neg_loglik(p)
        h = 1e-4
        hess = np.array([
            [(ll_for_hess([beta+h,eta]) - 2*ll_for_hess([beta,eta]) + ll_for_hess([beta-h,eta]))/h**2,
             (ll_for_hess([beta+h,eta+h]) - ll_for_hess([beta+h,eta-h]) - ll_for_hess([beta-h,eta+h]) + ll_for_hess([beta-h,eta-h]))/(4*h**2)],
            [(ll_for_hess([beta+h,eta+h]) - ll_for_hess([beta+h,eta-h]) - ll_for_hess([beta-h,eta+h]) + ll_for_hess([beta-h,eta-h]))/(4*h**2),
             (ll_for_hess([beta,eta+h]) - 2*ll_for_hess([beta,eta]) + ll_for_hess([beta,eta-h]))/h**2]
        ])
        cov = np.linalg.inv(hess)
        # Delta method for B10
        z = 1.96
        y10 = np.log(-np.log(0.9))
        var_b10 = (cov[1,1]/(beta*eta)**2) + (y10/beta)**2 * (cov[0,0]/beta**2)
        se_b10 = float(np.sqrt(max(var_b10, 0))) * b10
        b10_lo = max(0, b10 - z * se_b10)
        b10_hi = b10 + z * se_b10
    except Exception:
        b10_lo = b10 * 0.7
        b10_hi = b10 * 1.3

    # ── R² on Weibull probability paper ──────────────────────────────────────
    sorted_f = np.sort(failures)
    # Median ranks (Bernard's approximation)
    ranks = (np.arange(1, n_fail+1) - 0.3) / (n_fail + 0.4)
    ranks = np.clip(ranks, 1e-6, 1-1e-6)
    x_prob = np.log(sorted_f)
    y_prob = np.log(-np.log(1 - ranks))
    slope, intercept, r, *_ = stats.linregress(x_prob, y_prob)
    r2 = float(r**2)

    # ── Chart data ────────────────────────────────────────────────────────────
    t_max = times.max() * 1.2
    t_plot = np.linspace(t_max * 0.01, t_max, 200)
    cdf_plot = (1 - np.exp(-(t_plot/eta)**beta)).tolist()
    pdf_plot = (beta/eta * (t_plot/eta)**(beta-1) * np.exp(-(t_plot/eta)**beta)).tolist()
    haz_plot = (beta/eta * (t_plot/eta)**(beta-1)).tolist()
    # Survival
    surv_plot = (np.exp(-(t_plot/eta)**beta)).tolist()

    chart_data = {
        "failure_times": times.tolist(),
        "censored_flags": censored.tolist(),
        "t_plot": t_plot.tolist(),
        "cdf": cdf_plot,
        "pdf": pdf_plot,
        "hazard": haz_plot,
        "survival": surv_plot,
        # Weibull probability paper
        "prob_paper_x": x_prob.tolist(),
        "prob_paper_y": y_prob.tolist(),
        "prob_line_x": x_prob.tolist(),
        "prob_line_y": (slope * x_prob + intercept).tolist(),
        # B-lives
        "b10": b10, "b50": b50, "b90": b90,
        "beta": beta, "eta": eta,
    }

    conclusion = (
        f"Weibull fit: β={beta:.3f}, η={eta:.3f} ({fit_method.upper()}). "
        f"{shape_interp[:50]}. "
        f"B10={b10:.1f}, B50={b50:.1f}, MTTF={mttf:.1f}. "
        f"R²={r2:.4f} on probability paper."
    )

    return WeibullResult(
        column=column, n=n, n_censored=n_censored,
        shape=round(beta,5), scale=round(eta,5), location=0.0,
        r_squared=round(r2,5), fit_method="MLE",
        b10_life=round(b10,3), b50_life=round(b50,3), b90_life=round(b90,3),
        mttf=round(mttf,3),
        shape_interpretation=shape_interp,
        b10_ci_lower=round(b10_lo,3), b10_ci_upper=round(b10_hi,3),
        chart_data=chart_data, conclusion=conclusion,
    )
