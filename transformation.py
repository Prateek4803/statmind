"""
StatMind E5 — Box-Cox / Johnson Transformation Engine
Auto-finds best transformation for non-normal data
Re-runs capability on transformed data
"""

import numpy as np
from scipy import stats, optimize
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


@dataclass
class TransformResult:
    column: str
    original_verdict: str
    original_sw_p: float
    best_transform: str          # "box_cox", "log", "sqrt", "reflect_log", "johnson", "none"
    transform_label: str         # human-readable
    lambda_value: Optional[float]
    transformed_verdict: str
    transformed_sw_p: float
    improvement: str             # "Significant", "Moderate", "None"
    # Transformed data stats
    transformed_mean: float
    transformed_std: float
    # Capability on transformed data
    cpk_original: Optional[float]
    cpk_transformed: Optional[float]
    # Chart data
    original_histogram: dict
    transformed_histogram: dict
    original_prob_plot: dict
    transformed_prob_plot: dict
    # Guidance
    recommendation: str
    back_transform_note: str
    all_transforms_tried: list   # [{name, sw_p, lambda}]


def _sw_p(data):
    """Shapiro-Wilk p-value."""
    try:
        _, p = stats.shapiro(data[:5000])
        return float(p)
    except Exception:
        return 0.0


def _histogram_data(data, n_bins=20):
    counts, edges = np.histogram(data, bins=n_bins)
    centers = [(edges[i]+edges[i+1])/2 for i in range(len(edges)-1)]
    mu, sigma = np.mean(data), np.std(data, ddof=1)
    x = np.linspace(mu-4*sigma, mu+4*sigma, 200)
    y = stats.norm.pdf(x, mu, sigma) * len(data) * (edges[1]-edges[0])
    return {"bin_centers": [round(float(c),6) for c in centers],
            "counts": counts.tolist(),
            "curve_x": [round(float(v),6) for v in x],
            "curve_y": [round(float(v),6) for v in y],
            "mean": round(float(mu),6)}


def _prob_plot_data(data):
    n = len(data)
    sorted_data = np.sort(data)
    theoretical = [float(stats.norm.ppf((i+0.5)/n)) for i in range(n)]
    slope, intercept, r, _, _ = stats.linregress(theoretical, sorted_data.tolist())
    fl_x = [theoretical[0], theoretical[-1]]
    fl_y = [slope*theoretical[0]+intercept, slope*theoretical[-1]+intercept]
    return {"theoretical_quantiles": [round(float(v),5) for v in theoretical],
            "sample_values": [round(float(v),5) for v in sorted_data],
            "fit_line_x": [round(float(v),5) for v in fl_x],
            "fit_line_y": [round(float(v),5) for v in fl_y],
            "r_squared": round(float(r**2),6)}


def auto_transform(data: np.ndarray, column: str,
                   usl: float = None, lsl: float = None,
                   alpha: float = 0.05) -> TransformResult:
    """
    Try multiple transformations, pick the one that best normalizes data.
    Returns full result with capability comparison.
    """
    data = data[~np.isnan(data)].astype(float)
    n = len(data)
    orig_sw_p = _sw_p(data)
    orig_verdict = "Normal" if orig_sw_p > alpha else "Likely Normal" if orig_sw_p > 0.01 else "Non-Normal"

    # Capability on original
    cpk_orig = None
    if usl is not None and lsl is not None:
        mean, std = np.mean(data), np.std(data, ddof=1)
        if std > 0:
            cpk_orig = round(float(min((usl-mean)/(3*std), (mean-lsl)/(3*std))), 4)

    all_tried = []

    def try_transform(name, label, transform_fn, inverse_note):
        try:
            transformed = transform_fn(data)
            if transformed is None or np.any(~np.isfinite(transformed)):
                return None
            sw_p = _sw_p(transformed)
            lam = None
            if name == "box_cox":
                lam = transform_fn._lambda if hasattr(transform_fn, '_lambda') else None
            all_tried.append({"name": name, "label": label, "sw_p": round(sw_p,5), "lambda": lam})
            return transformed, sw_p, lam, inverse_note
        except Exception:
            return None

    results = []

    # 1. Log transform (for right-skewed, all positive)
    if np.all(data > 0):
        log_data = np.log(data)
        sw_p = _sw_p(log_data)
        all_tried.append({"name": "log", "label": "Natural Log (ln)", "sw_p": round(sw_p,5), "lambda": None})
        results.append(("log", "Natural Log (ln)", log_data, sw_p, None,
                        "Back-transform: exp(result) = original scale"))

    # 2. Square root (for count/Poisson data, all non-negative)
    if np.all(data >= 0):
        sqrt_data = np.sqrt(data)
        sw_p = _sw_p(sqrt_data)
        all_tried.append({"name": "sqrt", "label": "Square Root (√)", "sw_p": round(sw_p,5), "lambda": None})
        results.append(("sqrt", "Square Root (√)", sqrt_data, sw_p, None,
                        "Back-transform: result² = original scale"))

    # 3. Box-Cox (handles positive data with optimal lambda)
    if np.all(data > 0):
        try:
            transformed_bc, lam = stats.boxcox(data)
            sw_p = _sw_p(transformed_bc)
            all_tried.append({"name": "box_cox", "label": f"Box-Cox (λ={lam:.4f})", "sw_p": round(sw_p,5), "lambda": round(float(lam),6)})
            back = (f"Back-transform: result × λ + 1)^(1/λ) with λ={lam:.4f}"
                    if abs(lam) > 0.01 else "Back-transform: exp(result) (λ≈0)")
            results.append(("box_cox", f"Box-Cox (λ={lam:.4f})", transformed_bc, sw_p, float(lam), back))
        except Exception:
            pass

    # 4. Reciprocal (for severely right-skewed)
    if np.all(data > 0):
        recip_data = 1.0 / data
        sw_p = _sw_p(recip_data)
        all_tried.append({"name": "reciprocal", "label": "Reciprocal (1/x)", "sw_p": round(sw_p,5), "lambda": None})
        results.append(("reciprocal", "Reciprocal (1/x)", recip_data, sw_p, None,
                        "Back-transform: 1/result = original scale. Note: reverses direction."))

    # 5. Reflect + log (for left-skewed)
    skew = float(stats.skew(data))
    if skew < -0.5:
        max_val = np.max(data)
        reflected = max_val - data + 1
        if np.all(reflected > 0):
            ref_log = np.log(reflected)
            sw_p = _sw_p(ref_log)
            all_tried.append({"name": "reflect_log", "label": "Reflect + Log", "sw_p": round(sw_p,5), "lambda": None})
            results.append(("reflect_log", "Reflect + Log", ref_log, sw_p, None,
                            f"Back-transform: exp(result) subtracted from max({max_val:.4f})"))

    # Pick best (highest SW p-value)
    if not results:
        # No transformation helped or applicable
        return TransformResult(
            column=column, original_verdict=orig_verdict, original_sw_p=round(orig_sw_p,5),
            best_transform="none", transform_label="No transformation applicable",
            lambda_value=None,
            transformed_verdict=orig_verdict, transformed_sw_p=round(orig_sw_p,5),
            improvement="None",
            transformed_mean=round(float(np.mean(data)),5),
            transformed_std=round(float(np.std(data,ddof=1)),5),
            cpk_original=cpk_orig, cpk_transformed=None,
            original_histogram=_histogram_data(data),
            transformed_histogram=_histogram_data(data),
            original_prob_plot=_prob_plot_data(data),
            transformed_prob_plot=_prob_plot_data(data),
            recommendation="Data cannot be transformed. Use non-parametric methods (Mann-Whitney, Kruskal-Wallis) or percentile-based capability indices.",
            back_transform_note="",
            all_transforms_tried=all_tried,
        )

    best = max(results, key=lambda x: x[3])
    best_name, best_label, best_data, best_sw_p, best_lam, back_note = best

    best_verdict = "Normal" if best_sw_p > alpha else "Likely Normal" if best_sw_p > 0.01 else "Non-Normal"

    # Improvement assessment
    improvement = ("Significant" if best_sw_p > 0.05 and orig_sw_p < 0.01
                   else "Moderate" if best_sw_p > orig_sw_p * 3
                   else "None")

    # Capability on transformed data
    cpk_trans = None
    if usl is not None and lsl is not None and best_sw_p > 0.01:
        try:
            # Transform spec limits too (approximate)
            if best_name == "log":
                t_usl, t_lsl = np.log(usl) if usl > 0 else None, np.log(lsl) if lsl > 0 else None
            elif best_name == "sqrt":
                t_usl, t_lsl = np.sqrt(abs(usl)), np.sqrt(abs(lsl))
            elif best_name == "box_cox" and best_lam is not None:
                t_usl = (usl**best_lam - 1)/best_lam if abs(best_lam) > 0.01 else np.log(usl)
                t_lsl = (lsl**best_lam - 1)/best_lam if abs(best_lam) > 0.01 else np.log(lsl)
            else:
                t_usl, t_lsl = None, None
            if t_usl and t_lsl:
                m = np.mean(best_data)
                s = np.std(best_data, ddof=1)
                if s > 0:
                    cpk_trans = round(float(min((t_usl-m)/(3*s), (m-t_lsl)/(3*s))), 4)
        except Exception:
            pass

    recommendation = (
        f"The {best_label} transformation normalizes the data (SW p={best_sw_p:.4f}). "
        f"{'Capability analysis on transformed data is now valid.' if cpk_trans else 'Apply transformation before running capability analysis.'} "
        f"{'Cpk improved from ' + str(cpk_orig) + ' to ' + str(cpk_trans) + '.' if cpk_orig and cpk_trans else ''}"
    )

    return TransformResult(
        column=column, original_verdict=orig_verdict, original_sw_p=round(orig_sw_p,5),
        best_transform=best_name, transform_label=best_label,
        lambda_value=round(best_lam,6) if best_lam else None,
        transformed_verdict=best_verdict, transformed_sw_p=round(best_sw_p,5),
        improvement=improvement,
        transformed_mean=round(float(np.mean(best_data)),5),
        transformed_std=round(float(np.std(best_data,ddof=1)),5),
        cpk_original=cpk_orig, cpk_transformed=cpk_trans,
        original_histogram=_histogram_data(data),
        transformed_histogram=_histogram_data(best_data),
        original_prob_plot=_prob_plot_data(data),
        transformed_prob_plot=_prob_plot_data(best_data),
        recommendation=recommendation,
        back_transform_note=back_note,
        all_transforms_tried=all_tried,
    )
