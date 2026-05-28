"""
StatMind — Reliability Prediction (MTBF / FIT rate / Bathtub Curve)
Google: "develop predictive failure models", "reliability prediction tools"
Amazon Kuiper: aerospace reliability requirements
Different from Weibull (which analyzes measured failure times) —
this predicts reliability FROM component count and usage profile.
References: MIL-HDBK-217, Telcordia SR-332, IEC 62380
"""
import numpy as np
from scipy import stats
from dataclasses import dataclass
from typing import Optional

@dataclass
class ComponentReliability:
    name: str
    category: str          # "IC","Resistor","Capacitor","Connector","Mechanical","Software"
    quantity: int
    fit_rate_base: float   # base FIT rate (failures per 1e9 hours)
    pi_quality: float      # quality factor (0.5 = hi-rel, 1.0 = commercial, 2.0 = lower)
    pi_environment: float  # environment factor (1.0=ground, 2.0=mobile, 5.0=airborne)
    pi_temperature: float  # temperature factor (1.0 at 25°C)
    fit_rate_adjusted: float  # FIT × πQ × πE × πT
    fit_total: float          # fit_rate_adjusted × quantity
    mtbf_contribution: float  # hours

@dataclass
class ReliabilityPrediction:
    system_name: str
    components: list        # list of ComponentReliability
    # System-level metrics
    total_fit_rate: float   # sum of all component FIT rates
    system_mtbf_hours: float   # 1e9 / total_FIT
    system_mttf_hours: float   # same for non-repairable
    # Reliability at target times
    reliability_1000h: float
    reliability_8760h: float   # 1 year
    reliability_target: float
    target_hours: float
    # Bathtub curve zones
    bathtub_early_pct: float  # % of failures in infant mortality zone
    bathtub_random_pct: float
    bathtub_wearout_pct: float
    early_life_end_hours: float
    wearout_start_hours: float
    # Top contributors (by FIT)
    top_contributors: list    # [{name, fit, pct}]
    # Predictions
    expected_failures_per_year_per_1000units: float
    field_return_rate_pct: float
    # Chart data
    chart_data: dict
    conclusion: str

# Base FIT rates (simplified — real tools use full MIL-HDBK-217 tables)
BASE_FIT_RATES = {
    "Microprocessor":       50.0,
    "FPGA":                 80.0,
    "Memory (DRAM)":        25.0,
    "Memory (Flash)":       15.0,
    "Linear IC":            20.0,
    "Logic IC":             15.0,
    "Resistor":              1.5,
    "Capacitor (ceramic)":   2.0,
    "Capacitor (electro)":  10.0,
    "Inductor":              3.0,
    "Diode":                 3.5,
    "Transistor":            4.0,
    "Connector":            15.0,
    "Switch/Button":        20.0,
    "Motor/Actuator":       50.0,
    "Mechanical (bearing)": 80.0,
    "PCB":                   5.0,
    "Battery/Cell":        100.0,
    "Display":              30.0,
    "Sensor":               25.0,
    "Crystal/Oscillator":   10.0,
    "Thermal component":    20.0,
    "Power supply":         40.0,
    "Custom/Unknown":       25.0,
}

ENVIRONMENT_FACTORS = {
    "Ground Benign":    1.0,
    "Ground Fixed":     2.0,
    "Ground Mobile":    4.0,
    "Naval Sheltered":  5.0,
    "Airborne":        10.0,
    "Space":           20.0,
}

def temperature_factor(temp_c: float) -> float:
    """Arrhenius temperature acceleration factor relative to 25°C."""
    ea = 0.7  # eV activation energy (typical electronics)
    k  = 8.617e-5  # Boltzmann constant eV/K
    t_ref = 25 + 273.15
    t_use = temp_c + 273.15
    return float(np.exp(ea/k * (1/t_ref - 1/t_use)))

def predict_reliability(
    system_name: str,
    component_list: list,    # [{name, category, quantity, temperature_c, quality_level, environment}]
    environment: str = "Ground Fixed",
    target_hours: float = 8760.0,
    early_life_end_h: float = 500.0,
    wearout_start_h: float = 50000.0,
) -> ReliabilityPrediction:
    """
    System-level reliability prediction using part-count method.
    component_list items: {name, category, quantity, temperature_c=25, quality_level="commercial"}
    quality_level: "hi-rel"(0.5), "commercial"(1.0), "standard"(2.0)
    """
    pi_env = ENVIRONMENT_FACTORS.get(environment, 2.0)
    quality_map = {"hi-rel": 0.5, "military": 0.5, "commercial": 1.0, "standard": 2.0, "consumer": 3.0}

    components = []
    for c in component_list:
        cat = c.get("category","Custom/Unknown")
        base_fit = BASE_FIT_RATES.get(cat, 25.0)
        qty = int(c.get("quantity", 1))
        temp = float(c.get("temperature_c", 25))
        pi_q = quality_map.get(c.get("quality_level","commercial"), 1.0)
        pi_t = temperature_factor(temp)
        adj_fit = base_fit * pi_q * pi_env * pi_t
        total_fit = adj_fit * qty
        comp = ComponentReliability(
            name=c.get("name", cat), category=cat, quantity=qty,
            fit_rate_base=round(base_fit, 3), pi_quality=round(pi_q, 3),
            pi_environment=round(pi_env, 3), pi_temperature=round(pi_t, 3),
            fit_rate_adjusted=round(adj_fit, 4), fit_total=round(total_fit, 4),
            mtbf_contribution=round(1e9/total_fit, 1) if total_fit > 0 else float('inf'),
        )
        components.append(comp)

    total_fit = sum(c.fit_total for c in components)
    sys_mtbf  = 1e9 / total_fit if total_fit > 0 else float('inf')
    lam = total_fit / 1e9

    r1000 = float(np.exp(-lam * 1000))
    r8760 = float(np.exp(-lam * 8760))
    r_tgt = float(np.exp(-lam * target_hours))

    # Bathtub curve zones (simplified)
    early_pct  = round(1 - float(np.exp(-lam * early_life_end_h * 3)), 3)  # higher rate early
    random_pct = round(float(np.exp(-lam * early_life_end_h)) - float(np.exp(-lam * wearout_start_h)), 3)
    wear_pct   = round(1 - early_pct - max(0, random_pct), 3)

    # Top contributors
    sorted_c = sorted(components, key=lambda x: x.fit_total, reverse=True)
    top = [{"name": c.name, "fit_total": c.fit_total,
             "pct": round(c.fit_total/total_fit*100, 1)} for c in sorted_c[:5]]

    # Bathtub curve data
    t_plot = np.linspace(0, wearout_start_h * 1.5, 300)
    # Early (decreasing): λ(t) = λ * (early_factor * e^(-t/early_tau) + 1)
    early_tau = early_life_end_h / 3
    haz = lam * (1 + 3 * np.exp(-t_plot/early_tau) + (t_plot/wearout_start_h)**3)

    chart_data = {
        "component_names": [c.name for c in sorted_c[:10]],
        "component_fit": [c.fit_total for c in sorted_c[:10]],
        "component_pct": [round(c.fit_total/total_fit*100,1) for c in sorted_c[:10]],
        "bathtub_t": t_plot[::10].tolist(),
        "bathtub_hazard": haz[::10].tolist(),
        "reliability_t": [target_hours*i/100 for i in range(101)],
        "reliability_r": [float(np.exp(-lam*target_hours*i/100)) for i in range(101)],
        "total_fit": round(total_fit, 3),
        "system_mtbf": round(sys_mtbf, 1),
    }

    conclusion = (
        f"System reliability prediction for {system_name} ({environment}). "
        f"Total FIT={total_fit:.1f}, MTBF={sys_mtbf:.0f}h. "
        f"R(1000h)={r1000:.4f}, R(8760h/1yr)={r8760:.4f}. "
        f"Top contributor: {top[0]['name']} ({top[0]['pct']}% of failures). "
        f"Expected {total_fit/1e6*8760:.1f} failures/1000 units/year."
    )

    return ReliabilityPrediction(
        system_name=system_name, components=components,
        total_fit_rate=round(total_fit, 4),
        system_mtbf_hours=round(sys_mtbf, 2),
        system_mttf_hours=round(sys_mtbf, 2),
        reliability_1000h=round(r1000, 6),
        reliability_8760h=round(r8760, 6),
        reliability_target=round(r_tgt, 6),
        target_hours=target_hours,
        bathtub_early_pct=early_pct, bathtub_random_pct=random_pct,
        bathtub_wearout_pct=wear_pct,
        early_life_end_hours=early_life_end_h,
        wearout_start_hours=wearout_start_h,
        top_contributors=top,
        expected_failures_per_year_per_1000units=round(total_fit/1e6*8760, 3),
        field_return_rate_pct=round((1-r8760)*100, 4),
        chart_data=chart_data, conclusion=conclusion,
    )

def list_categories() -> list:
    return [{"category": k, "base_fit": v, "description": f"Base FIT rate = {v}"} for k,v in BASE_FIT_RATES.items()]
