"""
StatMind E3 — Capability Sixpack
All 6 panels in one: Histogram, Normal Prob Plot, I-MR Chart,
Capability Curve, Run Chart, Summary Stats
Mirrors Minitab's Process Capability Sixpack output
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import Optional
import dataclasses


@dataclass
class SixpackResult:
    column: str
    n: int
    usl: float
    lsl: float
    target: Optional[float]
    # Indices
    cp: float
    cpk: float
    pp: float
    ppk: float
    cpm: float
    sigma_level: float
    ppm_within: float
    ppm_overall: float
    # Stats
    mean: float
    std_within: float
    std_overall: float
    # Normality
    normality_verdict: str
    sw_p: float
    # SPC
    chart_type: str
    ucl: float
    cl: float
    lcl: float
    total_alarms: int
    # Verdict
    overall_verdict: str
    verdict_detail: str
    # Chart data (6 panels)
    panel_histogram: dict
    panel_prob_plot: dict
    panel_imr: dict
    panel_capability_curve: dict
    panel_run_chart: dict
    panel_summary: dict


def build_sixpack(data: np.ndarray, column: str,
                  usl: float, lsl: float,
                  target: float = None) -> SixpackResult:
    """Build all 6 panels from raw data + spec limits."""
    import dataclasses as dc

    data = data[~np.isnan(data)].astype(float)
    n    = len(data)
    if n < 10:
        raise ValueError("Need at least 10 data points for a sixpack analysis.")

    # Import engines
    from normality import analyze_column
    from capability import analyze_capability
    from control_charts import auto_select_and_build as analyze_control_chart
    from types import SimpleNamespace as _SimpleNamespace

    norm = analyze_column(data, column)
    cap  = analyze_capability(data, column, usl, lsl, target)
    spc  = analyze_control_chart(data, column, subgroup_size=1)
    # auto_select_and_build() returns a dict; wrap it so the attribute-style
    # access used throughout this function (spc.primary_values, etc.) works.
    if isinstance(spc, dict):
        spc = _SimpleNamespace(**spc)

    # ── Panel 1: Histogram ────────────────────────────────────────────────────
    hd = cap.histogram_data
    panel_histogram = {
        "bin_centers": hd["bin_centers"],
        "counts": hd["counts"],
        "curve_x": hd["curve_x"],
        "curve_within": hd["curve_within"],
        "usl": usl, "lsl": lsl, "mean": float(np.mean(data)),
    }

    # ── Panel 2: Normal Probability Plot ─────────────────────────────────────
    pd_data = norm.probability_plot_data
    panel_prob_plot = {
        "theoretical_quantiles": pd_data["theoretical_quantiles"],
        "sample_values": pd_data["sample_values"],
        "fit_line_x": pd_data["fit_line_x"],
        "fit_line_y": pd_data["fit_line_y"],
        "r_squared": pd_data["r_squared"],
        "normality_verdict": norm.overall_verdict,
        "sw_p": norm.shapiro_wilk.p_value,
    }

    # ── Panel 3: I-MR Chart ───────────────────────────────────────────────────
    all_alarms = spc.western_electric_alarms + spc.nelson_alarms
    alarm_indices = list(set(a["index"] for a in all_alarms))
    panel_imr = {
        "values": spc.primary_values,
        "ucl": spc.primary_ucl, "cl": spc.primary_cl, "lcl": spc.primary_lcl,
        "mr_values": spc.secondary_values,
        "mr_ucl": spc.secondary_ucl, "mr_cl": spc.secondary_cl,
        "alarm_indices": alarm_indices,
        "total_alarms": spc.total_alarms,
        "in_control": spc.in_control,
    }

    # ── Panel 4: Capability Curve ─────────────────────────────────────────────
    x = np.linspace(
        min(data.min(), lsl) - 3*cap.std_overall,
        max(data.max(), usl) + 3*cap.std_overall,
        300
    )
    y_within  = stats.norm.pdf(x, cap.mean, cap.std_within).tolist()
    y_overall = stats.norm.pdf(x, cap.mean, cap.std_overall).tolist()
    panel_capability_curve = {
        "x": x.tolist(), "y_within": y_within, "y_overall": y_overall,
        "usl": usl, "lsl": lsl, "mean": cap.mean,
        "std_within": cap.std_within, "std_overall": cap.std_overall,
    }

    # ── Panel 5: Run Chart (time series) ─────────────────────────────────────
    mean_line = float(np.mean(data))
    ucl_run   = mean_line + 3*cap.std_within
    lcl_run   = mean_line - 3*cap.std_within
    panel_run_chart = {
        "values": data.tolist(),
        "mean": mean_line,
        "ucl": ucl_run, "lcl": lcl_run,
        "usl": usl, "lsl": lsl,
    }

    # ── Panel 6: Summary Table ────────────────────────────────────────────────
    panel_summary = {
        "n": n, "mean": round(cap.mean, 5),
        "std_within": round(cap.std_within, 5),
        "std_overall": round(cap.std_overall, 5),
        "cp": cap.cp, "cpk": cap.cpk, "cpm": cap.cpm,
        "pp": cap.pp, "ppk": cap.ppk,
        "sigma_level": cap.sigma_level,
        "ppm_within": cap.ppm_within,
        "ppm_overall": cap.ppm_overall,
        "normality": norm.overall_verdict,
        "in_control": spc.in_control,
        "total_alarms": spc.total_alarms,
        "verdict": cap.verdict,
    }

    # Overall verdict
    issues = []
    if cap.cpk < 1.33:   issues.append(f"Cpk={cap.cpk:.3f} below 1.33")
    if not spc.in_control: issues.append(f"{spc.total_alarms} SPC alarms")
    if norm.overall_verdict == "Non-Normal": issues.append("Non-normal distribution")
    overall_verdict = "Not Capable" if cap.cpk < 1.0 else "Marginal" if cap.cpk < 1.33 else "Capable" if spc.in_control else "Capable but Unstable"
    verdict_detail  = ". ".join(issues) if issues else "Process is capable and in statistical control."

    return SixpackResult(
        column=column, n=n, usl=usl, lsl=lsl,
        target=target or round((usl+lsl)/2, 6),
        cp=cap.cp, cpk=cap.cpk, pp=cap.pp, ppk=cap.ppk, cpm=cap.cpm,
        sigma_level=cap.sigma_level,
        ppm_within=cap.ppm_within, ppm_overall=cap.ppm_overall,
        mean=cap.mean, std_within=cap.std_within, std_overall=cap.std_overall,
        normality_verdict=norm.overall_verdict, sw_p=norm.shapiro_wilk.p_value,
        chart_type=spc.chart_type, ucl=spc.primary_ucl,
        cl=spc.primary_cl, lcl=spc.primary_lcl,
        total_alarms=spc.total_alarms,
        overall_verdict=overall_verdict, verdict_detail=verdict_detail,
        panel_histogram=panel_histogram,
        panel_prob_plot=panel_prob_plot,
        panel_imr=panel_imr,
        panel_capability_curve=panel_capability_curve,
        panel_run_chart=panel_run_chart,
        panel_summary=panel_summary,
    )
