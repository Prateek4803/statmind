"""
StatMind N7 — Measurement Uncertainty Calculator (ISO GUM)
Type A (statistical) + Type B (non-statistical) uncertainty
Combined uncertainty + Expanded uncertainty (k=2 → 95% confidence)
ISO/IEC Guide 98-3:2008 (GUM) compliant
"""
import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class UncertaintyComponent:
    name: str
    type: str              # "A" or "B"
    value: float           # standard uncertainty u_i
    unit: str
    distribution: str      # "normal", "rectangular", "triangular"
    coverage_factor: float # k used to convert to std uncertainty
    sensitivity: float     # c_i (partial derivative / influence coefficient)
    contribution: float    # (c_i * u_i)^2 — variance contribution
    percent_contribution: float

@dataclass
class UncertaintyResult:
    measurand: str
    unit: str
    # Type A
    type_a_components: list
    # Type B
    type_b_components: list
    all_components: list
    # Combined uncertainty
    u_combined: float
    u_combined_relative: float   # as % of mean
    # Effective degrees of freedom (Welch-Satterthwaite)
    nu_eff: float
    # Expanded uncertainty
    k_factor: float              # coverage factor (k=2 for ~95%)
    U_expanded: float
    confidence_level: float      # ~95% for k=2
    # Result expression
    result_mean: float
    result_string: str           # "450.2 ± 1.4 nm (k=2, 95%)"
    # Dominant source
    dominant_source: str
    # Chart data
    chart_data: dict
    conclusion: str

def _type_b_to_std(half_width: float, distribution: str) -> float:
    """Convert Type B uncertainty to standard uncertainty."""
    if distribution == "rectangular":
        return half_width / np.sqrt(3)
    elif distribution == "triangular":
        return half_width / np.sqrt(6)
    elif distribution == "normal":
        return half_width   # already std dev
    elif distribution == "u_shaped":
        return half_width / np.sqrt(2)
    return half_width / np.sqrt(3)  # default rectangular

def calculate_uncertainty(
    measurand: str = "Measurement",
    unit: str = "",
    mean_value: float = 0.0,
    # Type A: provide raw repeated measurements
    type_a_data: list = None,    # repeated measurements list
    # Type B: provide list of dicts
    type_b_inputs: list = None,  # [{"name", "half_width", "distribution", "sensitivity"}]
    k_expanded: float = 2.0,     # coverage factor (2 ≈ 95%, 3 ≈ 99%)
) -> UncertaintyResult:
    """
    Calculate combined and expanded measurement uncertainty per ISO GUM.
    """
    components = []
    type_a_comps = []
    type_b_comps = []

    # ── Type A uncertainty ───────────────────────────────────────────────────
    if type_a_data and len(type_a_data) >= 2:
        arr = np.array(type_a_data, dtype=float)
        n = len(arr)
        mean_a = float(np.mean(arr))
        std_a = float(np.std(arr, ddof=1))
        u_a = std_a / np.sqrt(n)   # standard uncertainty = std error of mean
        comp = UncertaintyComponent(
            name="Repeatability (Type A)",
            type="A",
            value=round(u_a, 8),
            unit=unit,
            distribution="normal",
            coverage_factor=1.0,
            sensitivity=1.0,
            contribution=u_a**2,
            percent_contribution=0.0,  # will be updated
        )
        type_a_comps.append(comp)
        components.append(comp)
        if mean_value == 0.0:
            mean_value = mean_a

    # ── Type B uncertainties ─────────────────────────────────────────────────
    for inp in (type_b_inputs or []):
        hw = inp.get("half_width", 0)
        dist = inp.get("distribution", "rectangular")
        sens = inp.get("sensitivity", 1.0)
        u_b = _type_b_to_std(hw, dist)
        contrib = (sens * u_b)**2
        comp = UncertaintyComponent(
            name=inp.get("name", "Type B component"),
            type="B",
            value=round(u_b, 8),
            unit=unit,
            distribution=dist,
            coverage_factor={"rectangular": np.sqrt(3), "triangular": np.sqrt(6), "normal": 1.0}.get(dist, np.sqrt(3)),
            sensitivity=float(sens),
            contribution=contrib,
            percent_contribution=0.0,
        )
        type_b_comps.append(comp)
        components.append(comp)

    if not components:
        raise ValueError("Provide at least one Type A dataset or Type B component.")

    # ── Combined uncertainty (RSS) ────────────────────────────────────────────
    u_c = float(np.sqrt(sum(c.contribution for c in components)))
    total_var = sum(c.contribution for c in components)

    for c in components:
        c.percent_contribution = round(c.contribution / max(total_var, 1e-30) * 100, 1)

    # ── Effective degrees of freedom (Welch-Satterthwaite) ────────────────────
    numerator = u_c**4
    denom = 0.0
    for c in components:
        if c.type == "A" and len(type_a_data or []) >= 2:
            nu = len(type_a_data) - 1
        else:
            nu = 50  # conservative large DOF for Type B
        denom += (c.contribution)**2 / max(nu, 1)
    nu_eff = round(float(numerator / max(denom, 1e-30)), 1)
    nu_eff = min(nu_eff, 1e6)

    # ── Expanded uncertainty ──────────────────────────────────────────────────
    # Use t-distribution for small dof, normal for large
    if nu_eff < 30:
        actual_k = float(stats.t.ppf(0.975, df=nu_eff))
        conf_level = 0.95
    else:
        actual_k = k_expanded
        conf_level = float(2 * stats.norm.cdf(k_expanded) - 1)

    U = round(float(actual_k * u_c), 8)
    u_rel = round(float(u_c / abs(mean_value) * 100), 4) if mean_value != 0 else 0.0

    # Result string
    result_str = f"{mean_value:.6g} ± {U:.4g} {unit} (k={actual_k:.2f}, {conf_level*100:.0f}%)"

    # Dominant source
    dominant = max(components, key=lambda c: c.contribution)

    # Chart data — pie chart of contributions
    chart_data = {
        "components": [{"name": c.name, "type": c.type, "u": round(c.value, 8),
                        "contribution_pct": c.percent_contribution} for c in components],
        "u_combined": round(u_c, 8),
        "U_expanded": round(U, 8),
        "k": round(actual_k, 4),
        "confidence": conf_level,
        "measurand": measurand,
        "mean_value": mean_value,
    }

    conclusion = (
        f"Combined uncertainty u_c = {u_c:.4g} {unit} ({u_rel:.2f}% relative). "
        f"Expanded uncertainty U = {U:.4g} {unit} (k={actual_k:.2f}, {conf_level*100:.0f}% confidence, ν_eff={nu_eff:.0f}). "
        f"Dominant source: {dominant.name} ({dominant.percent_contribution:.0f}% of variance). "
        f"Result: {result_str}"
    )

    return UncertaintyResult(
        measurand=measurand, unit=unit,
        type_a_components=type_a_comps,
        type_b_components=type_b_comps,
        all_components=components,
        u_combined=round(u_c, 8),
        u_combined_relative=u_rel,
        nu_eff=nu_eff,
        k_factor=round(actual_k, 4),
        U_expanded=round(U, 8),
        confidence_level=conf_level,
        result_mean=mean_value,
        result_string=result_str,
        dominant_source=dominant.name,
        chart_data=chart_data,
        conclusion=conclusion,
    )
