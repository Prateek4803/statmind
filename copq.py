"""
StatMind — Cost of Poor Quality (COPQ) Calculator
Calculates prevention, appraisal, internal failure, and external failure costs.
"""

def calculate_copq(data: dict) -> dict:
    """Calculate COPQ breakdown from input cost data."""
    prevention     = float(data.get("prevention_cost",     0))
    appraisal      = float(data.get("appraisal_cost",      0))
    internal_fail  = float(data.get("internal_failure",    0))
    external_fail  = float(data.get("external_failure",    0))
    revenue        = float(data.get("annual_revenue",      1))

    total = prevention + appraisal + internal_fail + external_fail
    pct_revenue = round(total / revenue * 100, 2) if revenue > 0 else 0

    return {
        "prevention_cost":     prevention,
        "appraisal_cost":      appraisal,
        "internal_failure":    internal_fail,
        "external_failure":    external_fail,
        "total_copq":          round(total, 2),
        "pct_of_revenue":      pct_revenue,
        "conformance_cost":    round(prevention + appraisal, 2),
        "nonconformance_cost": round(internal_fail + external_fail, 2),
        "benchmark_pct":       "World-class: <1% | Typical: 5–15% | Poor: >20%",
    }
