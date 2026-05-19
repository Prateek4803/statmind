"""
StatMind — Transformation & Non-Normal Capability Engine
=========================================================
Decision rules (Apple/AIAG aligned):
  p > 0.05              → Normal data. Standard Cp/Cpk valid.
  0.01 < p ≤ 0.05       → Likely non-normal. Try Box-Cox first.
  p ≤ 0.01              → Non-normal. Box-Cox then Johnson SU/SB.
  Box-Cox |λ| > 5       → Extreme. Reject Box-Cox. Use Johnson or Non-Normal.
  Johnson SU p > 0.05   → Proceed with Johnson capability.
  All transforms fail    → Non-normal capability (ISO 22514-2 percentile method).

Johnson SU transform:
  Z = a + b * arcsinh((X - loc) / scale)
  Z is standard-normal. Transform spec limits identically.
  Cpk_J = min( (Z(USL)-Z̄)/(3·Sz), (Z̄-Z(LSL))/(3·Sz) )

Johnson SB transform (for bounded data like proportions, ±tolerances):
  Z = a + b * ln((X - loc) / (loc + scale - X))

Non-normal capability (ISO 22514-2):
  Uses empirical or parametric percentiles at 0.135% and 99.865%.
  Cpk_nn = min((USL - P99.865), (P0.135 - LSL)) / ((P99.865 - P0.135)/2)

Workflow integration:
  auto_transform() returns TransformResult with:
  - decision:         'normal' | 'box_cox' | 'johnson_su' | 'johnson_sb' | 'non_normal'
  - requires_action:  True if user needs to do something before running capability
  - action_message:   Exact instruction shown to user
  - cpk_original:     Cpk assuming normality (flagged as unreliable if non-normal)
  - cpk_transformed:  Cpk in transformed space (reliable)
  - exported_data:    {column: z_values} dict — downloadable transformed dataset
"""

from __future__ import annotations

import warnings
import numpy as np
from dataclasses import dataclass, field
from scipy import stats, optimize
from typing import Optional

warnings.filterwarnings("ignore")


# ── Constants ────────────────────────────────────────────────────────────────

LAMBDA_EXTREME_THRESHOLD = 5.0   # |λ| beyond this → reject Box-Cox
NORMALITY_ALPHA = 0.05


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class TransformResult:
    column: str
    n: int

    # Normality assessment
    original_sw_p: float
    original_sw_stat: float
    original_verdict: str          # 'Normal' | 'Likely Normal' | 'Non-Normal'

    # Decision
    decision: str                  # 'normal' | 'box_cox' | 'johnson_su' | 'johnson_sb' | 'non_normal'
    best_transform: str            # same as decision, kept for API compat
    transform_label: str           # human-readable e.g. "Johnson SU"
    lambda_value: Optional[float]  # Box-Cox λ only; None otherwise
    improvement: str               # 'None' | 'Moderate' | 'Significant'

    # Post-transform normality
    transformed_sw_p: float
    transformed_verdict: str

    # Stats
    transformed_mean: float
    transformed_std: float

    # Capability
    cpk_original: Optional[float]   # Cpk assuming normality (may be unreliable)
    cpk_transformed: Optional[float]  # Cpk in transformed space (reliable)
    cpk_reliable: bool               # True only when transform succeeded
    cp_transformed: Optional[float]
    sigma_level_transformed: Optional[float]
    ppm_transformed: Optional[dict]  # {'above': X, 'below': Y, 'total': Z}

    # Non-normal capability (ISO 22514-2)
    non_normal_capability: Optional[dict]  # when all transforms fail

    # Charts
    original_histogram: dict
    transformed_histogram: dict
    original_prob_plot: dict
    transformed_prob_plot: dict

    # Exported data (for download)
    exported_data: list          # transformed Z-values user can download and run normality on
    exported_column_name: str    # e.g. "Dataset_1_Johnson_SU"

    # User guidance
    requires_action: bool        # True if user must act before trusting Cpk
    action_message: str          # Exact message shown in UI
    recommendation: str          # Full recommendation paragraph
    back_transform_note: str

    # All transforms tried
    all_transforms_tried: list   # [{label, sw_p, lambda, decision}]

    # Johnson SU parameters (for reproducible back-transform)
    johnson_params: Optional[dict]  # {a, b, loc, scale, type}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sw_p(data: np.ndarray) -> tuple:
    try:
        stat, p = stats.shapiro(data[:5000])
        return float(stat), float(p)
    except Exception:
        return 0.0, 0.0


def _verdict(p: float, alpha: float = NORMALITY_ALPHA) -> str:
    if p > alpha:       return "Normal"
    if p > alpha / 5:   return "Likely Normal"
    return "Non-Normal"


def _histogram_data(data: np.ndarray, n_bins: int = 20) -> dict:
    data = data[np.isfinite(data)]
    counts, edges = np.histogram(data, bins=n_bins)
    centers = [(edges[i] + edges[i + 1]) / 2 for i in range(len(edges) - 1)]
    mu, sigma = float(np.mean(data)), float(np.std(data, ddof=1))
    x = np.linspace(mu - 4 * sigma, mu + 4 * sigma, 200)
    y = stats.norm.pdf(x, mu, sigma) * len(data) * (edges[1] - edges[0])
    return {
        "bin_centers": [round(float(c), 6) for c in centers],
        "counts": counts.tolist(),
        "curve_x": [round(float(v), 6) for v in x],
        "curve_y": [round(float(v), 6) for v in y],
    }


def _prob_plot_data(data: np.ndarray) -> dict:
    data = np.sort(data[np.isfinite(data)])
    n = len(data)
    probs = (np.arange(1, n + 1) - 0.375) / (n + 0.25)
    theoretical = stats.norm.ppf(probs)
    slope, intercept, r, *_ = stats.linregress(theoretical, data)
    fit_x = [float(theoretical[0]), float(theoretical[-1])]
    fit_y = [slope * x + intercept for x in fit_x]
    return {
        "theoretical_quantiles": [round(float(q), 5) for q in theoretical],
        "sample_values": [round(float(v), 6) for v in data],
        "fit_line_x": [round(v, 5) for v in fit_x],
        "fit_line_y": [round(v, 6) for v in fit_y],
        "r_squared": round(float(r ** 2), 6),
    }


def _cpk(data: np.ndarray, usl: float, lsl: float) -> tuple:
    """Returns (cp, cpk) or (None, None)."""
    if usl is None or lsl is None or usl <= lsl:
        return None, None
    mean = float(np.mean(data))
    std  = float(np.std(data, ddof=1))
    if std <= 0:
        return None, None
    cp  = round((usl - lsl) / (6 * std), 4)
    cpk = round(min((usl - mean) / (3 * std), (mean - lsl) / (3 * std)), 4)
    return cp, cpk


def _ppm(z_mean: float, z_std: float, z_usl: Optional[float], z_lsl: Optional[float]) -> dict:
    """PPM from Z-space normal model."""
    ppm = {}
    if z_usl is not None:
        ppm["above"] = round(float((1 - stats.norm.cdf((z_usl - z_mean) / z_std)) * 1e6), 1)
    if z_lsl is not None:
        ppm["below"] = round(float(stats.norm.cdf((z_lsl - z_mean) / z_std) * 1e6), 1)
    ppm["total"] = round((ppm.get("above", 0) + ppm.get("below", 0)), 1)
    return ppm


def _sigma_level(cpk: float) -> float:
    return round(cpk * 3, 3)


# ── Johnson SU / SB transforms ───────────────────────────────────────────────

def _johnson_su(data: np.ndarray) -> tuple:
    """
    Fit Johnson SU. Returns (z_transformed, params_dict, sw_p).
    Z = a + b * arcsinh((X - loc) / scale)
    """
    a, b, loc, scale = stats.johnsonsu.fit(data)
    z = a + b * np.arcsinh((data - loc) / scale)
    z_clean = z[np.isfinite(z)]
    if len(z_clean) < 10:
        return None, None, 0.0
    _, p = _sw_p(z_clean)
    params = {"a": round(float(a), 6), "b": round(float(b), 6),
              "loc": round(float(loc), 6), "scale": round(float(scale), 6),
              "type": "SU"}
    return z_clean, params, p


def _johnson_sb(data: np.ndarray) -> tuple:
    """
    Fit Johnson SB (bounded). Returns (z_transformed, params_dict, sw_p).
    Z = a + b * ln((X - loc) / (loc + scale - X))
    """
    try:
        a, b, loc, scale = stats.johnsonsb.fit(data)
        denom = loc + scale - data
        if np.any(denom <= 0) or np.any(data <= loc):
            return None, None, 0.0
        z = a + b * np.log((data - loc) / denom)
        z_clean = z[np.isfinite(z)]
        if len(z_clean) < 10:
            return None, None, 0.0
        _, p = _sw_p(z_clean)
        params = {"a": round(float(a), 6), "b": round(float(b), 6),
                  "loc": round(float(loc), 6), "scale": round(float(scale), 6),
                  "type": "SB"}
        return z_clean, params, p
    except Exception:
        return None, None, 0.0


def _transform_spec_johnson(val: Optional[float], params: dict) -> Optional[float]:
    """Transform a spec limit (USL or LSL) into Johnson Z-space."""
    if val is None or params is None:
        return None
    try:
        a, b, loc, scale = params["a"], params["b"], params["loc"], params["scale"]
        if params["type"] == "SU":
            return a + b * np.arcsinh((val - loc) / scale)
        else:  # SB
            denom = loc + scale - val
            if denom <= 0 or val <= loc:
                return None
            return a + b * np.log((val - loc) / denom)
    except Exception:
        return None


# ── Non-normal capability (ISO 22514-2) ──────────────────────────────────────

def _nonnormal_capability(data: np.ndarray, usl: Optional[float],
                           lsl: Optional[float]) -> Optional[dict]:
    """
    ISO 22514-2 percentile-based capability.
    Fits best distribution, uses 0.135th and 99.865th percentiles.
    """
    if usl is None and lsl is None:
        return None

    data = data[data > 0] if np.all(data >= 0) else data
    best_name, best_dist, best_params, best_aic = None, None, None, np.inf

    for name, dist in [("lognormal", stats.lognorm), ("gamma", stats.gamma),
                        ("weibull_min", stats.weibull_min)]:
        try:
            params = dist.fit(data)
            loglik = float(np.sum(dist.logpdf(data, *params)))
            aic = 2 * len(params) - 2 * loglik
            if aic < best_aic:
                best_aic = aic
                best_name, best_dist, best_params = name, dist, params
        except Exception:
            pass

    if best_dist is None:
        return None

    try:
        p_lo  = float(best_dist.ppf(0.00135, *best_params))
        p_hi  = float(best_dist.ppf(0.99865, *best_params))
        p_50  = float(best_dist.ppf(0.500,   *best_params))
        half  = (p_hi - p_lo) / 2.0
        if half <= 0:
            return None

        cpu_nn = round((usl - p_hi) / half, 4) if usl is not None else None
        cpl_nn = round((p_lo - lsl) / half, 4) if lsl is not None else None

        vals = [v for v in [abs(cpu_nn) if cpu_nn else None,
                             abs(cpl_nn) if cpl_nn else None] if v is not None]
        cpk_nn = round(min(vals), 4) if vals else None

        ppm_above = float((1 - best_dist.cdf(usl, *best_params)) * 1e6) if usl else 0.0
        ppm_below = float(best_dist.cdf(lsl, *best_params) * 1e6) if lsl else 0.0

        return {
            "distribution": best_name,
            "aic": round(best_aic, 1),
            "p0135": round(p_lo, 6),
            "p99865": round(p_hi, 6),
            "p50": round(p_50, 6),
            "cpu_nn": cpu_nn,
            "cpl_nn": cpl_nn,
            "cpk_nn": cpk_nn,
            "ppm_above": round(ppm_above, 1),
            "ppm_below": round(ppm_below, 1),
            "ppm_total": round(ppm_above + ppm_below, 1),
            "note": (f"Non-normal Cpk via ISO 22514-2 using {best_name} distribution. "
                     "Uses 0.135th and 99.865th percentiles instead of ±3σ."),
        }
    except Exception:
        return None


# ── Main public function ──────────────────────────────────────────────────────

def auto_transform(
    data: np.ndarray,
    column: str,
    usl: Optional[float] = None,
    lsl: Optional[float] = None,
    alpha: float = NORMALITY_ALPHA,
) -> TransformResult:
    """
    Auto-select the best transformation for non-normal data.
    Returns full TransformResult including:
      - Cpk in transformed space (reliable)
      - Exported Z-values for download
      - User action message
      - Non-normal capability as fallback

    Decision tree:
      SW p > 0.05         → Normal. No transform needed.
      Box-Cox |λ| ≤ 5     → Apply Box-Cox.
      Box-Cox |λ| > 5     → Try Johnson SU → Johnson SB → Non-Normal.
    """
    data = data[~np.isnan(data)].astype(float)
    n = len(data)
    orig_stat, orig_p = _sw_p(data)
    orig_verdict = _verdict(orig_p, alpha)

    cp_orig, cpk_orig = _cpk(data, usl, lsl)
    all_tried = []

    # ── Case 1: Data is already normal ───────────────────────────────────────
    if orig_p > alpha:
        return TransformResult(
            column=column, n=n,
            original_sw_p=round(orig_p, 6), original_sw_stat=round(orig_stat, 6),
            original_verdict=orig_verdict,
            decision="normal", best_transform="none",
            transform_label="No transformation required",
            lambda_value=None, improvement="None",
            transformed_sw_p=round(orig_p, 6), transformed_verdict=orig_verdict,
            transformed_mean=round(float(data.mean()), 6),
            transformed_std=round(float(data.std(ddof=1)), 6),
            cpk_original=cpk_orig, cpk_transformed=cpk_orig,
            cpk_reliable=True, cp_transformed=cp_orig,
            sigma_level_transformed=_sigma_level(cpk_orig) if cpk_orig else None,
            ppm_transformed=None,
            non_normal_capability=None,
            original_histogram=_histogram_data(data),
            transformed_histogram=_histogram_data(data),
            original_prob_plot=_prob_plot_data(data),
            transformed_prob_plot=_prob_plot_data(data),
            exported_data=[round(float(v), 6) for v in data],
            exported_column_name=f"{column}_original",
            requires_action=False,
            action_message="Data is normally distributed. Standard Cp/Cpk values are reliable.",
            recommendation=("Data passes normality (SW p={:.4f} > 0.05). "
                            "Standard capability indices are valid.".format(orig_p)),
            back_transform_note="",
            all_transforms_tried=[{"label": "Original", "sw_p": round(orig_p, 6),
                                    "lambda": None, "decision": "normal"}],
            johnson_params=None,
        )

    # ── Case 2: Non-normal — try transforms ──────────────────────────────────
    all_tried.append({"label": "Original (no transform)",
                       "sw_p": round(orig_p, 6), "lambda": None, "decision": "rejected"})

    best_decision  = "non_normal"
    best_label     = "Non-Normal (no transform succeeded)"
    best_z         = data.copy()
    best_p         = orig_p
    best_lambda    = None
    best_johnson   = None

    # --- Try Box-Cox ---
    if np.all(data > 0):
        try:
            transformed_bc, lam = stats.boxcox(data)
            _, bc_p = _sw_p(transformed_bc)
            lam_f = round(float(lam), 4)
            rejected = abs(lam_f) > LAMBDA_EXTREME_THRESHOLD
            all_tried.append({
                "label": f"Box-Cox (λ={lam_f})",
                "sw_p": round(bc_p, 6),
                "lambda": lam_f,
                "decision": "rejected — |λ|>5 (extreme)" if rejected else (
                    "selected" if bc_p > best_p else "not best"),
            })
            if not rejected and bc_p > best_p:
                best_decision = "box_cox"
                best_label = f"Box-Cox (λ={lam_f})"
                best_z = transformed_bc
                best_p = bc_p
                best_lambda = lam_f
        except Exception as e:
            all_tried.append({"label": "Box-Cox", "sw_p": 0, "lambda": None,
                               "decision": f"failed: {e}"})

    # --- Log transform ---
    if np.all(data > 0):
        try:
            z_log = np.log(data)
            _, p_log = _sw_p(z_log)
            all_tried.append({"label": "Natural Log", "sw_p": round(p_log, 6),
                               "lambda": None, "decision": "tried"})
            if p_log > best_p:
                best_decision, best_label, best_z, best_p = "log", "Natural Log (ln)", z_log, p_log
        except Exception:
            pass

    # --- Square root ---
    if np.all(data >= 0):
        try:
            z_sqrt = np.sqrt(data)
            _, p_sqrt = _sw_p(z_sqrt)
            all_tried.append({"label": "Square Root", "sw_p": round(p_sqrt, 6),
                               "lambda": None, "decision": "tried"})
            if p_sqrt > best_p:
                best_decision, best_label, best_z, best_p = "sqrt", "Square Root (√)", z_sqrt, p_sqrt
        except Exception:
            pass

    # --- Johnson SU (always tried for extreme non-normality) ---
    z_su, params_su, p_su = _johnson_su(data)
    if z_su is not None:
        all_tried.append({"label": "Johnson SU", "sw_p": round(p_su, 6),
                           "lambda": None, "decision": "tried"})
        if p_su > best_p:
            best_decision, best_label = "johnson_su", "Johnson SU"
            best_z, best_p, best_johnson = z_su, p_su, params_su

    # --- Johnson SB ---
    z_sb, params_sb, p_sb = _johnson_sb(data)
    if z_sb is not None:
        all_tried.append({"label": "Johnson SB", "sw_p": round(p_sb, 6),
                           "lambda": None, "decision": "tried"})
        if p_sb > best_p and best_decision not in ("johnson_su",):
            best_decision, best_label = "johnson_sb", "Johnson SB"
            best_z, best_p, best_johnson = z_sb, p_sb, params_sb

    best_verdict = _verdict(best_p, alpha)
    improvement  = ("Significant" if best_p > alpha else
                    "Moderate" if best_p > orig_p * 5 else "None")

    # ── Capability in transformed space ──────────────────────────────────────
    cp_t, cpk_t = None, None
    sigma_t, ppm_t = None, None
    nn_cap = None
    cpk_reliable = False
    z_usl = z_lsl = None

    if usl is not None or lsl is not None:
        if best_decision in ("johnson_su", "johnson_sb") and best_johnson:
            z_usl = _transform_spec_johnson(usl, best_johnson)
            z_lsl = _transform_spec_johnson(lsl, best_johnson)
            if best_p > alpha:
                cp_t, cpk_t = _cpk(best_z, z_usl or 1e9, z_lsl or -1e9)
                cpk_reliable = True
                if cpk_t is not None:
                    sigma_t = _sigma_level(cpk_t)
                    z_mean, z_std = float(best_z.mean()), float(best_z.std(ddof=1))
                    ppm_t = _ppm(z_mean, z_std, z_usl, z_lsl)
        elif best_decision in ("box_cox", "log", "sqrt"):
            # For simple transforms, transform spec limits analytically
            if best_p > alpha:
                # Only use if transformation actually worked
                cp_t, cpk_t = _cpk(best_z, usl, lsl)  # spec limits in original space
                # For Box-Cox/log/sqrt, we need to transform specs properly
                try:
                    if best_decision == "box_cox" and best_lambda is not None:
                        z_usl_v = ((usl ** best_lambda) - 1) / best_lambda if best_lambda != 0 else np.log(usl)
                        z_lsl_v = ((lsl ** best_lambda) - 1) / best_lambda if best_lambda != 0 else np.log(lsl)
                    elif best_decision == "log":
                        z_usl_v, z_lsl_v = np.log(usl) if usl else None, np.log(lsl) if lsl else None
                    elif best_decision == "sqrt":
                        z_usl_v, z_lsl_v = np.sqrt(usl) if usl else None, np.sqrt(lsl) if lsl else None
                    cp_t, cpk_t = _cpk(best_z,
                                        z_usl_v if usl else 1e9,
                                        z_lsl_v if lsl else -1e9)
                    cpk_reliable = True
                    if cpk_t:
                        sigma_t = _sigma_level(cpk_t)
                except Exception:
                    pass

        # Non-normal capability as fallback or supplement
        nn_cap = _nonnormal_capability(data, usl, lsl)

    # ── Action message ────────────────────────────────────────────────────────
    if best_decision == "normal" or orig_p > alpha:
        requires_action = False
        action_msg = "Data is normally distributed. Standard Cp/Cpk is valid."
    elif best_p > alpha and cpk_reliable:
        requires_action = False
        action_msg = (f"✅ {best_label} normalised your data (p={best_p:.4f}). "
                      "Capability indices below are calculated in transformed space. "
                      "Download the transformed data to run further analyses in StatMind.")
    elif best_p > alpha and not cpk_reliable:
        requires_action = True
        action_msg = (f"⚠️ {best_label} normalised your data (p={best_p:.4f}) but "
                      "spec limits are required to calculate Cpk. "
                      "Enter USL and LSL in the Capability sidebar.")
    else:
        requires_action = True
        action_msg = (f"❌ No transformation achieved normality (best p={best_p:.4f} ≤ 0.05). "
                      "Non-normal capability indices (ISO 22514-2) are shown below. "
                      "These are valid without transformation — do NOT use standard Cpk.")

    rec_lines = [
        f"Original data: {orig_verdict} (SW p={orig_p:.4f}).",
        f"Box-Cox λ={best_lambda:.2f} — {'|λ|>{} extreme, rejected'.format(LAMBDA_EXTREME_THRESHOLD) if best_lambda and abs(best_lambda) > LAMBDA_EXTREME_THRESHOLD else 'applied'}."
        if best_lambda else "Box-Cox: not applicable (data contains non-positive values).",
        f"Best transformation: {best_label} → {best_verdict} (p={best_p:.4f}).",
    ]
    if cpk_t is not None:
        rec_lines.append(f"Cpk ({best_label}): {cpk_t:.4f}. "
                         "This is the statistically reliable capability index.")
    if cpk_orig is not None:
        rel = "valid" if orig_p > alpha else "UNRELIABLE — do not report"
        rec_lines.append(f"Standard Cpk (normal assumption): {cpk_orig:.4f} — {rel}.")
    if nn_cap:
        rec_lines.append(f"Non-normal Cpk (ISO 22514-2 / {nn_cap['distribution']}): {nn_cap['cpk_nn']:.4f}.")
    recommendation = " ".join(rec_lines)

    back_note = {
        "johnson_su": ("Back-transform: X = loc + scale · sinh((Z - a) / b). "
                       "Use this to convert Z-space results back to original units."),
        "johnson_sb": ("Back-transform: X = loc + scale · e^((Z-a)/b) / (1 + e^((Z-a)/b)). "
                       "Use this to convert Z-space results to original units."),
        "box_cox": (f"Back-transform: X = (Z·λ + 1)^(1/λ) where λ={best_lambda}."
                    if best_lambda and best_lambda != 0 else "Back-transform: X = e^Z (λ=0 case)."),
        "log": "Back-transform: X = e^Z.",
        "sqrt": "Back-transform: X = Z².",
        "non_normal": "No back-transform needed — ISO 22514-2 uses original data percentiles.",
        "normal": "",
    }.get(best_decision, "")

    exported_col = f"{column}_{best_decision.replace('_', '')}"

    return TransformResult(
        column=column, n=n,
        original_sw_p=round(orig_p, 6), original_sw_stat=round(orig_stat, 6),
        original_verdict=orig_verdict,
        decision=best_decision, best_transform=best_decision,
        transform_label=best_label,
        lambda_value=best_lambda, improvement=improvement,
        transformed_sw_p=round(best_p, 6), transformed_verdict=best_verdict,
        transformed_mean=round(float(best_z.mean()), 6) if len(best_z) > 0 else 0.0,
        transformed_std=round(float(best_z.std(ddof=1)), 6) if len(best_z) > 1 else 0.0,
        cpk_original=cpk_orig, cpk_transformed=cpk_t,
        cpk_reliable=cpk_reliable, cp_transformed=cp_t,
        sigma_level_transformed=sigma_t, ppm_transformed=ppm_t,
        non_normal_capability=nn_cap,
        original_histogram=_histogram_data(data),
        transformed_histogram=_histogram_data(best_z),
        original_prob_plot=_prob_plot_data(data),
        transformed_prob_plot=_prob_plot_data(best_z),
        exported_data=[round(float(v), 8) for v in best_z],
        exported_column_name=exported_col,
        requires_action=requires_action,
        action_message=action_msg,
        recommendation=recommendation,
        back_transform_note=back_note,
        all_transforms_tried=all_tried,
        johnson_params=best_johnson,
    )
