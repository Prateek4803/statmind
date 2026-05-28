"""
StatMind P2-C — MSA Linearity & Bias Study (AIAG MSA 4th Ed)
Gauge linearity across measurement range + bias vs reference standard.
Required for CMM and dimensional gauge qualification.
"""
import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import Optional

@dataclass
class LinearityBiasResult:
    gauge_name: str
    n_parts: int
    n_replicates: int
    # Bias study
    biases: list           # bias at each reference value [{ref, mean_meas, bias, bias_pct}]
    overall_bias: float
    bias_significant: bool
    bias_p_value: float
    # Linearity study
    linearity_slope: float       # slope of bias vs reference
    linearity_intercept: float
    linearity_r_squared: float
    linearity_p_value: float
    linearity_significant: bool  # non-zero slope = linearity error
    # Linearity as % of process variation
    linearity_pct_pv: float
    bias_pct_pv: float
    # Verdict
    verdict: str
    aiag_interpretation: str
    # Chart data
    chart_data: dict
    conclusion: str

def analyze_linearity_bias(
    reference_values: list,   # list of reference (master) values
    measurements: list,       # list of lists: measurements[i] = replicates for part i
    gauge_name: str = "Gauge",
    process_variation: float = None,  # 6σ of process (for %PV calculation)
    alpha: float = 0.05,
) -> LinearityBiasResult:
    """
    AIAG MSA 4th Ed linearity and bias study.
    reference_values: [ref1, ref2, ...] - reference/master values per part
    measurements: [[m1, m2, m3], [m1, m2, m3], ...] - repeated measurements per part
    """
    ref = np.array(reference_values, dtype=float)
    n_parts = len(ref)
    
    # Compute bias per part
    part_means = np.array([np.mean(m) for m in measurements])
    biases_arr = part_means - ref
    n_replicates = max(len(m) for m in measurements) if measurements else 1
    
    # Overall bias (t-test: is mean bias ≠ 0?)
    overall_bias = float(np.mean(biases_arr))
    bias_std = float(np.std(biases_arr, ddof=1))
    if bias_std > 0:
        t_stat = overall_bias / (bias_std / np.sqrt(n_parts))
        bias_p = float(2 * stats.t.sf(abs(t_stat), df=n_parts-1))
    else:
        t_stat, bias_p = 0.0, 1.0
    bias_sig = bias_p < alpha
    
    # Linearity: regress bias vs reference value
    slope, intercept, r, lin_p, se = stats.linregress(ref, biases_arr)
    lin_sig = lin_p < alpha  # non-zero slope = linearity problem
    
    # % of process variation
    pv = process_variation if process_variation else (6 * np.std(np.concatenate(measurements), ddof=1))
    lin_pct_pv  = round(abs(slope) * float(np.ptp(ref)) / pv * 100, 2) if pv > 0 else 0.0
    bias_pct_pv = round(abs(overall_bias) / pv * 100, 2) if pv > 0 else 0.0
    
    # Bias detail per part
    biases_detail = []
    for i in range(n_parts):
        biases_detail.append({
            "part": i+1,
            "reference": round(float(ref[i]), 5),
            "mean_measurement": round(float(part_means[i]), 5),
            "bias": round(float(biases_arr[i]), 5),
            "bias_pct_pv": round(abs(float(biases_arr[i])) / pv * 100, 2) if pv > 0 else 0,
        })
    
    # Verdict
    if not bias_sig and not lin_sig:
        verdict = "Acceptable"
        interp = "No significant bias or linearity error detected. Gauge is accurate across its range."
    elif bias_sig and not lin_sig:
        verdict = "Bias — adjust zero"
        interp = f"Significant overall bias of {overall_bias:.5f} ({bias_pct_pv:.1f}% of PV). The gauge reads consistently high or low. Adjust the zero/offset calibration."
    elif not bias_sig and lin_sig:
        verdict = "Linearity error — recalibrate span"
        interp = f"Significant linearity (slope={slope:.5f}/unit, R²={r**2:.4f}). Gauge accuracy changes across its range. Multi-point calibration required."
    else:
        verdict = "Both bias and linearity — full recalibration"
        interp = "Both bias and linearity errors detected. Full multi-point calibration required before this gauge can be used for production."
    
    # Chart data
    ref_line = float(ref.min()), float(ref.max())
    fitted_bias = [float(slope*r_val + intercept) for r_val in [ref_line[0], ref_line[1]]]
    zero_line_y = [0.0, 0.0]
    
    chart_data = {
        "reference": ref.tolist(),
        "biases": biases_arr.tolist(),
        "part_means": part_means.tolist(),
        "fitted_x": list(ref_line),
        "fitted_y": fitted_bias,
        "zero_y": zero_line_y,
        "zero_x": list(ref_line),
        "overall_bias": overall_bias,
        "upper_ci": overall_bias + stats.t.ppf(0.975, n_parts-1) * bias_std / np.sqrt(n_parts),
        "lower_ci": overall_bias - stats.t.ppf(0.975, n_parts-1) * bias_std / np.sqrt(n_parts),
    }
    
    conclusion = (
        f"Linearity & Bias Study for {gauge_name}. "
        f"n={n_parts} reference values, {n_replicates} replicates each. "
        f"Overall bias = {overall_bias:.5f} ({bias_pct_pv:.1f}% of PV, {'significant' if bias_sig else 'not significant'}). "
        f"Linearity slope = {slope:.5f}/unit (R²={r**2:.4f}, {'significant' if lin_sig else 'not significant'}). "
        f"Verdict: {verdict}."
    )
    
    return LinearityBiasResult(
        gauge_name=gauge_name,
        n_parts=n_parts, n_replicates=n_replicates,
        biases=biases_detail,
        overall_bias=round(overall_bias, 6),
        bias_significant=bias_sig, bias_p_value=round(bias_p, 5),
        linearity_slope=round(float(slope), 6),
        linearity_intercept=round(float(intercept), 6),
        linearity_r_squared=round(float(r**2), 5),
        linearity_p_value=round(float(lin_p), 5),
        linearity_significant=lin_sig,
        linearity_pct_pv=lin_pct_pv,
        bias_pct_pv=bias_pct_pv,
        verdict=verdict,
        aiag_interpretation=interp,
        chart_data=chart_data,
        conclusion=conclusion,
    )
