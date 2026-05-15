"""
StatMind E7 — Design of Experiments (DOE)
Full factorial, fractional factorial (half, quarter), Taguchi L arrays
Run matrix generator + main effects + interaction analysis + optimal settings
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from itertools import product as iproduct


@dataclass
class DOEResult:
    design_type: str         # "Full Factorial", "Half Fraction", "Quarter Fraction"
    n_factors: int
    n_runs: int
    factor_names: list
    factor_levels: dict      # {name: [low, high]}
    # Run matrix
    run_matrix: list         # [{run, factor_cols, response}]
    # Effects (after response data entered)
    main_effects: list       # [{factor, effect, pct_contribution, significant}]
    interactions: list       # [{factors, effect, pct_contribution, significant}]
    # Optimal settings
    optimal_settings: dict   # {factor: level}
    predicted_optimal: Optional[float]
    # ANOVA-style summary
    ss_total: float
    ss_error: float
    r_squared: float
    # Chart data
    chart_data: dict
    # Verdict
    conclusion: str
    generator: str           # defining relation for fractional designs


def _hadamard_matrix(n):
    """Generate Hadamard matrix of order n (must be power of 2)."""
    if n == 1:
        return np.array([[1]])
    H = _hadamard_matrix(n // 2)
    return np.block([[H, H], [H, -H]])


def generate_design(
    factor_names: list,
    factor_levels: dict,   # {name: [low, high]}
    design_type: str = "auto",  # "full", "half", "quarter", "auto"
    responses: list = None,     # optional: list of response values matching run order
) -> DOEResult:
    """
    Generate a 2-level factorial design and analyze effects.
    design_type="auto" selects full for k≤4, half for k=5-6, quarter for k=7-8.
    """
    k = len(factor_names)
    if k < 2:
        raise ValueError("Need at least 2 factors for a DOE.")
    if k > 8:
        raise ValueError("StatMind DOE supports up to 8 factors. Use screening designs for more.")

    # Auto-select resolution
    if design_type == "auto":
        if k <= 4:    design_type = "full"
        elif k <= 6:  design_type = "half"
        else:         design_type = "quarter"

    # Build coded design matrix (±1)
    if design_type == "full":
        n_runs = 2**k
        coded  = np.array(list(iproduct([-1,1], repeat=k)))
        generator = "Full 2^k factorial"
        design_label = f"Full 2^{k} Factorial ({n_runs} runs)"

    elif design_type == "half":
        # 2^(k-1) half fraction
        k_base  = k - 1
        n_runs  = 2**k_base
        coded   = np.array(list(iproduct([-1,1], repeat=k_base)))
        # Generator: last factor = product of all others
        last_col = np.prod(coded, axis=1, keepdims=True)
        coded    = np.hstack([coded, last_col])
        generator = f"I = {''.join(factor_names)}"
        design_label = f"2^({k}-1) Half Fraction ({n_runs} runs)"

    else:  # quarter
        k_base  = k - 2
        n_runs  = 2**k_base
        coded   = np.array(list(iproduct([-1,1], repeat=k_base)))
        # Two generators
        gen1 = np.prod(coded[:, :k_base//2+1], axis=1, keepdims=True)
        gen2 = np.prod(coded[:, k_base//2:],   axis=1, keepdims=True)
        coded= np.hstack([coded, gen1, gen2])[:, :k]
        generator = f"Quarter fraction with 2 generators"
        design_label = f"2^({k}-2) Quarter Fraction ({n_runs} runs)"

    n_runs = len(coded)

    # Build run matrix (decode ±1 to actual factor levels)
    run_matrix = []
    for i, row in enumerate(coded):
        run = {"run": i+1, "coded": row.tolist()}
        for j, fname in enumerate(factor_names):
            levels = factor_levels[fname]
            run[fname] = levels[0] if row[j] < 0 else levels[1]
        if responses and i < len(responses):
            run["response"] = float(responses[i])
        run_matrix.append(run)

    # Effect analysis (if responses provided)
    main_effects, interactions, optimal_settings, predicted_opt = [], [], {}, None
    ss_total, ss_error, r_squared = 0.0, 0.0, 0.0

    if responses and len(responses) >= n_runs:
        y = np.array([float(r) for r in responses[:n_runs]])
        grand_mean = float(np.mean(y))
        ss_total = float(np.sum((y - grand_mean)**2))

        # Main effects
        for j, fname in enumerate(factor_names):
            col = coded[:, j]
            effect = float(2 * np.mean(y * col))   # contrast / n * 2
            ss_eff = float(n_runs * effect**2 / 4)
            main_effects.append({
                "factor": fname,
                "effect": round(effect, 5),
                "ss": round(ss_eff, 5),
                "pct_contribution": round(ss_eff / ss_total * 100, 1) if ss_total > 0 else 0.0,
                "significant": abs(effect) > 2 * np.std(y, ddof=1) / np.sqrt(n_runs),
            })

        # Two-factor interactions
        from itertools import combinations
        for i1, i2 in combinations(range(k), 2):
            inter_col = coded[:, i1] * coded[:, i2]
            effect = float(2 * np.mean(y * inter_col))
            ss_eff = float(n_runs * effect**2 / 4)
            interactions.append({
                "factors": f"{factor_names[i1]}×{factor_names[i2]}",
                "effect": round(effect, 5),
                "ss": round(ss_eff, 5),
                "pct_contribution": round(ss_eff / ss_total * 100, 1) if ss_total > 0 else 0.0,
                "significant": abs(effect) > 2 * np.std(y, ddof=1) / np.sqrt(n_runs),
            })

        # Sort by |effect|
        main_effects.sort(key=lambda x: abs(x["effect"]), reverse=True)
        interactions.sort(key=lambda x: abs(x["effect"]), reverse=True)

        # Optimal settings: set each factor to level that maximizes response
        for j, fname in enumerate(factor_names):
            col = coded[:, j]
            mean_low  = float(np.mean(y[col < 0]))
            mean_high = float(np.mean(y[col > 0]))
            levels = factor_levels[fname]
            optimal_settings[fname] = levels[1] if mean_high >= mean_low else levels[0]

        # Predicted optimal (simple main effect model)
        predicted_opt = grand_mean + sum(
            abs(e["effect"]) / 2 for e in main_effects if e["significant"]
        )

        # SS residual (approximate as sum of non-significant effects)
        ss_model = sum(e["ss"] for e in main_effects + interactions if e["significant"])
        ss_error = max(0.0, ss_total - ss_model)
        r_squared = round(float(ss_model / ss_total), 4) if ss_total > 0 else 0.0

    # Chart data
    factor_labels = factor_names
    me_values = [e["effect"] for e in main_effects]
    int_values = [i["effect"] for i in interactions[:6]]  # top 6 interactions

    chart_data = {
        "run_matrix": run_matrix,
        "factor_names": factor_names,
        "n_runs": n_runs,
        "main_effects": main_effects,
        "interactions": interactions[:6],
        "main_effect_plot": {
            "factors": [e["factor"] for e in main_effects],
            "effects": [e["effect"] for e in main_effects],
            "low_means": [],
            "high_means": [],
        },
        "pareto_effects": {
            "names": [e["factor"] for e in main_effects] + [i["factors"] for i in interactions[:4]],
            "values": [abs(e["effect"]) for e in main_effects] + [abs(i["effect"]) for i in interactions[:4]],
        }
    }

    # Add low/high means for main effect plot
    if responses and len(responses) >= n_runs:
        y = np.array([float(r) for r in responses[:n_runs]])
        for j, fname in enumerate(factor_names):
            col = coded[:, j]
            chart_data["main_effect_plot"]["low_means"].append(round(float(np.mean(y[col < 0])),5))
            chart_data["main_effect_plot"]["high_means"].append(round(float(np.mean(y[col > 0])),5))

    sig_main = [e["factor"] for e in main_effects if e["significant"]]
    sig_int  = [i["factors"] for i in interactions if i["significant"]]

    if responses:
        conclusion = (
            f"Significant main effects: {', '.join(sig_main) if sig_main else 'None detected'}. "
            f"Significant interactions: {', '.join(sig_int[:3]) if sig_int else 'None'}. "
            f"R² = {r_squared:.4f} — model explains {r_squared*100:.1f}% of variation. "
            f"Optimal settings: {optimal_settings}. Predicted optimum: {predicted_opt:.4f}."
            if predicted_opt else ""
        )
    else:
        conclusion = (
            f"{design_label} generated. {n_runs} runs required. "
            f"Enter response data to calculate effects."
        )

    return DOEResult(
        design_type=design_label, n_factors=k, n_runs=n_runs,
        factor_names=factor_names, factor_levels=factor_levels,
        run_matrix=run_matrix,
        main_effects=main_effects, interactions=interactions,
        optimal_settings=optimal_settings,
        predicted_optimal=round(predicted_opt,5) if predicted_opt else None,
        ss_total=round(ss_total,5), ss_error=round(ss_error,5),
        r_squared=r_squared, chart_data=chart_data,
        conclusion=conclusion, generator=generator,
    )
