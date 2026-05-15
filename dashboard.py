"""
StatMind E12 — Process Dashboard Engine
All parameters in one executive view.
Traffic light status, trend arrows, threshold alerts.
Aggregates results from all sessions into a single summary.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ParameterStatus:
    name: str
    # Latest values
    cpk: Optional[float]
    ppk: Optional[float]
    mean: Optional[float]
    std: Optional[float]
    ppm: Optional[float]
    sigma_level: Optional[float]
    # SPC
    in_control: bool
    total_alarms: int
    # GRR
    grr_pct: Optional[float]
    ndc: Optional[int]
    # Normality
    normality_verdict: str
    # Traffic light
    status: str          # "green", "amber", "red"
    status_reason: str
    # Trend
    trend: str           # "improving", "stable", "degrading"
    # Spec limits
    usl: Optional[float]
    lsl: Optional[float]
    # Timestamps
    last_updated: str


@dataclass
class DashboardResult:
    title: str
    generated_at: str
    n_parameters: int
    parameters: list          # list of ParameterStatus
    # Summary counts
    green_count: int
    amber_count: int
    red_count: int
    # Overall health score 0-100
    health_score: float
    health_label: str         # "Excellent", "Good", "At Risk", "Critical"
    # Top issues
    top_issues: list          # [{parameter, issue, severity}]
    # Chart data
    chart_data: dict


def _traffic_light(cpk, in_control, grr_pct, normality) -> tuple:
    """Return (status, reason) for a parameter."""
    if cpk is not None and cpk < 1.0:
        return "red", f"Cpk={cpk:.3f} < 1.00 — defects being produced"
    if not in_control:
        return "red", "SPC alarms detected — process out of control"
    if grr_pct is not None and grr_pct > 30:
        return "red", f"%GRR={grr_pct:.1f}% — measurement system unacceptable"
    if cpk is not None and cpk < 1.33:
        return "amber", f"Cpk={cpk:.3f} between 1.00–1.33 — marginal capability"
    if grr_pct is not None and grr_pct > 10:
        return "amber", f"%GRR={grr_pct:.1f}% — marginal measurement system"
    if normality == "Non-Normal":
        return "amber", "Non-normal distribution — verify capability method"
    return "green", "Process capable and in control"


def build_dashboard(
    session_results: list,    # list of dicts from any session
    title: str = "StatMind Process Dashboard",
) -> DashboardResult:
    """
    Build a dashboard from a list of session result dicts.
    Each item: {"name": str, "capability": dict, "spc": dict, "grr": dict, "normality": dict}
    """
    parameters = []
    issues = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for item in session_results:
        name   = item.get("name", "Parameter")
        cap    = item.get("capability") or {}
        spc    = item.get("spc") or {}
        grr    = item.get("grr") or {}
        norm   = item.get("normality") or {}

        cpk    = cap.get("cpk")
        ppk    = cap.get("ppk")
        mean   = cap.get("mean")
        std    = cap.get("std_within") or cap.get("std_overall")
        ppm    = cap.get("ppm_within")
        sigma  = cap.get("sigma_level")
        usl    = cap.get("usl")
        lsl    = cap.get("lsl")
        in_ctrl= spc.get("in_control", True)
        alarms = spc.get("total_alarms", 0)
        grr_pct= grr.get("gauge_rr", {}).get("pct_study_var") if grr else None
        ndc    = grr.get("ndc") if grr else None
        norm_v = norm.get("overall_verdict", "Unknown") if norm else "Unknown"

        status, reason = _traffic_light(cpk, in_ctrl, grr_pct, norm_v)

        # Trend: heuristic based on Cp-Cpk gap and alarms
        trend = "stable"
        if cpk and cap.get("cp"):
            gap = cap.get("cp", 0) - cpk
            if gap > 0.5:     trend = "degrading"
            elif gap < 0.1:   trend = "improving"
        if alarms > 5:        trend = "degrading"

        param = ParameterStatus(
            name=name, cpk=cpk, ppk=ppk, mean=mean, std=std,
            ppm=ppm, sigma_level=sigma,
            in_control=in_ctrl, total_alarms=alarms,
            grr_pct=grr_pct, ndc=ndc,
            normality_verdict=norm_v,
            status=status, status_reason=reason,
            trend=trend, usl=usl, lsl=lsl,
            last_updated=now,
        )
        parameters.append(param)

        if status in ("red", "amber"):
            issues.append({
                "parameter": name, "issue": reason,
                "severity": "Critical" if status == "red" else "Major",
            })

    # Summary
    green = sum(1 for p in parameters if p.status == "green")
    amber = sum(1 for p in parameters if p.status == "amber")
    red   = sum(1 for p in parameters if p.status == "red")
    n     = len(parameters)

    health_score = round((green * 100 + amber * 60 + red * 10) / max(n, 1), 1)
    health_label = (
        "Excellent" if health_score >= 90 else
        "Good"      if health_score >= 70 else
        "At Risk"   if health_score >= 50 else
        "Critical"
    )

    # Chart data
    chart_data = {
        "parameter_names": [p.name for p in parameters],
        "cpks":   [p.cpk   for p in parameters],
        "ppks":   [p.ppk   for p in parameters],
        "statuses": [p.status for p in parameters],
        "alarms": [p.total_alarms for p in parameters],
        "grr_pcts": [p.grr_pct for p in parameters],
        "health_score": health_score,
        "traffic_lights": {
            "green": green, "amber": amber, "red": red
        },
    }

    return DashboardResult(
        title=title, generated_at=now,
        n_parameters=n, parameters=parameters,
        green_count=green, amber_count=amber, red_count=red,
        health_score=health_score, health_label=health_label,
        top_issues=sorted(issues, key=lambda x: 0 if x["severity"]=="Critical" else 1)[:10],
        chart_data=chart_data,
    )
