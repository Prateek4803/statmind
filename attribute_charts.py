"""
StatMind S3-C — Attribute Control Charts (p, np, u, c)
Per AIAG SPC Manual 2nd Ed. and Montgomery Statistical Quality Control.
  p chart  — proportion defective (variable subgroup size)
  np chart — number defective (constant subgroup size)
  u chart  — defects per unit (variable subgroup size)
  c chart  — count of defects (constant subgroup size)
"""
import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional
import warnings; warnings.filterwarnings("ignore")


@dataclass
class AttributeAlarm:
    index: int
    value: float
    ucl: float
    lcl: float
    rule: str
    description: str


@dataclass
class AttributeChartResult:
    chart_type: str          # 'p'|'np'|'u'|'c'
    n: int                   # number of subgroups
    values: list             # proportions/counts per subgroup
    subgroup_sizes: list     # ni per subgroup
    cl: float                # centre line
    ucl: list                # per-subgroup UCL (list for variable n)
    lcl: list                # per-subgroup LCL
    # Alarms
    alarms: list             # List[AttributeAlarm]
    total_alarms: int
    in_control: bool
    # Summary
    overall_rate: float      # p-bar or u-bar or c-bar
    sigma: float             # estimated sigma
    verdict: str
    interpretation: str
    # Phase II limits (for future monitoring)
    phase2_cl: float
    phase2_ucl: float        # based on average subgroup size
    phase2_lcl: float


def build_p_chart(
    defectives: np.ndarray,   # number of defectives per subgroup
    subgroup_sizes: np.ndarray,  # subgroup size ni
    column: str = "Defectives",
) -> AttributeChartResult:
    """p chart — fraction defective."""
    n_sub = len(defectives)
    if n_sub < 5:
        raise ValueError(f"p chart requires at least 5 subgroups. Got {n_sub}.")

    p = defectives / subgroup_sizes
    p_bar = float(defectives.sum() / subgroup_sizes.sum())

    ucl_list = []
    lcl_list = []
    for ni in subgroup_sizes:
        sigma_i = np.sqrt(p_bar * (1 - p_bar) / ni)
        ucl_list.append(min(float(p_bar + 3 * sigma_i), 1.0))
        lcl_list.append(max(float(p_bar - 3 * sigma_i), 0.0))

    alarms = _detect_alarms(p, p_bar, ucl_list, lcl_list, "p")
    avg_n = float(subgroup_sizes.mean())
    sigma_avg = np.sqrt(p_bar * (1 - p_bar) / avg_n)

    return _build_result(
        "p", n_sub, p, subgroup_sizes, p_bar, ucl_list, lcl_list,
        alarms, p_bar, float(sigma_avg),
        f"p-bar = {p_bar:.4f} ({p_bar*100:.2f}% average fraction defective)",
        p_bar, min(p_bar+3*sigma_avg,1.0), max(p_bar-3*sigma_avg,0.0)
    )


def build_np_chart(
    defectives: np.ndarray,  # count of defectives per subgroup
    subgroup_size: int,      # constant subgroup size
    column: str = "Defectives",
) -> AttributeChartResult:
    """np chart — number defective (constant n)."""
    n_sub = len(defectives)
    if n_sub < 5:
        raise ValueError(f"np chart requires at least 5 subgroups.")
    n_arr = np.full(n_sub, subgroup_size)
    p_bar = float(defectives.mean()) / subgroup_size
    np_bar = float(defectives.mean())
    sigma = float(np.sqrt(np_bar * (1 - p_bar)))
    ucl = float(np_bar + 3 * sigma)
    lcl = float(max(np_bar - 3 * sigma, 0.0))
    ucl_list = [ucl] * n_sub
    lcl_list = [lcl] * n_sub
    alarms = _detect_alarms(defectives, np_bar, ucl_list, lcl_list, "np")
    return _build_result(
        "np", n_sub, defectives, n_arr, np_bar, ucl_list, lcl_list,
        alarms, np_bar, sigma,
        f"np-bar = {np_bar:.2f} average defectives per subgroup (n={subgroup_size})",
        np_bar, ucl, lcl
    )


def build_u_chart(
    defects: np.ndarray,        # total defects per subgroup
    subgroup_sizes: np.ndarray,
    column: str = "Defects",
) -> AttributeChartResult:
    """u chart — defects per unit (variable subgroup size)."""
    n_sub = len(defects)
    if n_sub < 5:
        raise ValueError(f"u chart requires at least 5 subgroups.")
    u = defects / subgroup_sizes
    u_bar = float(defects.sum() / subgroup_sizes.sum())
    ucl_list, lcl_list = [], []
    for ni in subgroup_sizes:
        sigma_i = np.sqrt(u_bar / ni)
        ucl_list.append(float(u_bar + 3 * sigma_i))
        lcl_list.append(float(max(u_bar - 3 * sigma_i, 0.0)))
    alarms = _detect_alarms(u, u_bar, ucl_list, lcl_list, "u")
    avg_n = float(subgroup_sizes.mean())
    sigma_avg = np.sqrt(u_bar / avg_n)
    return _build_result(
        "u", n_sub, u, subgroup_sizes, u_bar, ucl_list, lcl_list,
        alarms, u_bar, float(sigma_avg),
        f"u-bar = {u_bar:.4f} average defects per unit",
        u_bar, float(u_bar+3*sigma_avg), float(max(u_bar-3*sigma_avg,0.0))
    )


def build_c_chart(
    defects: np.ndarray,
    column: str = "Defects",
) -> AttributeChartResult:
    """c chart — count of defects per subgroup (constant area of opportunity)."""
    n_sub = len(defects)
    if n_sub < 5:
        raise ValueError(f"c chart requires at least 5 subgroups.")
    c_bar = float(defects.mean())
    sigma = float(np.sqrt(c_bar))
    ucl = float(c_bar + 3 * sigma)
    lcl = float(max(c_bar - 3 * sigma, 0.0))
    n_arr = np.ones(n_sub)
    ucl_list = [ucl] * n_sub
    lcl_list = [lcl] * n_sub
    alarms = _detect_alarms(defects, c_bar, ucl_list, lcl_list, "c")
    return _build_result(
        "c", n_sub, defects, n_arr, c_bar, ucl_list, lcl_list,
        alarms, c_bar, sigma,
        f"c-bar = {c_bar:.2f} average defects per subgroup",
        c_bar, ucl, lcl
    )


def _detect_alarms(values, cl, ucl_list, lcl_list, chart_type) -> list:
    alarms = []
    for i, v in enumerate(values):
        if v > ucl_list[i]:
            alarms.append(AttributeAlarm(
                index=i, value=round(float(v),6),
                ucl=round(ucl_list[i],6), lcl=round(lcl_list[i],6),
                rule="OOC1", description=f"Point {i+1} above UCL ({v:.4f} > {ucl_list[i]:.4f})"
            ))
        elif v < lcl_list[i] and lcl_list[i] > 0:
            alarms.append(AttributeAlarm(
                index=i, value=round(float(v),6),
                ucl=round(ucl_list[i],6), lcl=round(lcl_list[i],6),
                rule="OOC2", description=f"Point {i+1} below LCL"
            ))
    # Run rules: 8+ consecutive on same side
    for start in range(len(values)-7):
        window = [values[j] > cl for j in range(start, start+8)]
        if all(window) or not any(window):
            side = "above" if all(window) else "below"
            alarms.append(AttributeAlarm(
                index=start+4, value=round(float(values[start+4]),6),
                ucl=round(ucl_list[start+4],6), lcl=round(lcl_list[start+4],6),
                rule="OOC3", description=f"8+ consecutive points {side} centre line (run rule)"
            ))
            break
    return alarms


def _build_result(chart_type, n_sub, values, subgroup_sizes, cl,
                  ucl_list, lcl_list, alarms, overall_rate, sigma,
                  interpretation, p2_cl, p2_ucl, p2_lcl) -> AttributeChartResult:
    in_ctrl = len(alarms) == 0
    if in_ctrl:
        verdict = f"{chart_type.upper()} chart: Process in statistical control. Overall rate = {overall_rate:.4f}."
    else:
        verdict = f"{chart_type.upper()} chart: {len(alarms)} alarm(s). Process NOT in statistical control."
    return AttributeChartResult(
        chart_type=chart_type, n=n_sub,
        values=[round(float(v),6) for v in values],
        subgroup_sizes=[int(s) for s in subgroup_sizes],
        cl=round(float(cl),6),
        ucl=[round(u,6) for u in ucl_list],
        lcl=[round(l,6) for l in lcl_list],
        alarms=[{'index':a.index,'value':a.value,'ucl':a.ucl,'lcl':a.lcl,
                 'rule':a.rule,'description':a.description} for a in alarms],
        total_alarms=len(alarms), in_control=in_ctrl,
        overall_rate=round(float(overall_rate),6),
        sigma=round(float(sigma),6),
        verdict=verdict, interpretation=interpretation,
        phase2_cl=round(p2_cl,6),
        phase2_ucl=round(p2_ucl,6),
        phase2_lcl=round(p2_lcl,6),
    )
