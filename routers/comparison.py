"""
StatMind E10 — Multi-Dataset Comparison Engine
Upload multiple datasets and compare them side by side.
Compares: Cpk, normality, SPC, means, variances, distributions.
Use case: Chamber A vs Chamber B, Tool 1 vs Tool 2, Shift 1 vs Shift 2
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


@dataclass
class DatasetStats:
    name: str
    n: int
    mean: float
    std: float
    median: float
    min_val: float
    max_val: float
    cpk: Optional[float]
    cp: Optional[float]
    ppk: Optional[float]
    normality_verdict: str
    sw_p: float
    total_alarms: int
    in_control: bool
    ppm: Optional[float]
    sigma_level: Optional[float]
    histogram: dict
    values: list


@dataclass
class ComparisonResult:
    parameter: str
    datasets: list              # list of DatasetStats
    n_datasets: int
    # Statistical comparisons
    anova_p: float              # one-way ANOVA p-value
    anova_significant: bool
    levene_p: float             # variance equality test
    variances_equal: bool
    kruskal_p: float            # non-parametric
    kruskal_significant: bool
    # Pairwise t-tests
    pairwise: list              # [{pair, t_stat, p_value, significant, mean_diff, effect_size}]
    # Rankings
    best_cpk_dataset: str
    worst_cpk_dataset: str
    most_stable_dataset: str    # fewest SPC alarms
    # Chart data
    chart_data: dict
    # Conclusion
    conclusion: str
    recommendation: str


def compare_datasets(
    datasets: list,             # list of (name, np.ndarray)
    parameter: str = "Measurement",
    usl: float = None,
    lsl: float = None,
    alpha: float = 0.05,
) -> ComparisonResult:
    """
    Compare multiple datasets for the same parameter.
    datasets: [(name, array), (name, array), ...]
    """
    from itertools import combinations

    if len(datasets) < 2:
        raise ValueError("Need at least 2 datasets to compare.")
    if len(datasets) > 10:
        raise ValueError("Maximum 10 datasets for comparison.")

    # Clean data
    clean = [(name, arr[~np.isnan(arr)].astype(float)) for name, arr in datasets]
    groups = [arr for _, arr in clean]
    names  = [name for name, _ in clean]

    # ── Per-dataset stats ─────────────────────────────────────────────────────
    dataset_stats = []
    for name, arr in clean:
        n = len(arr)
        mean = float(np.mean(arr))
        std  = float(np.std(arr, ddof=1)) if n > 1 else 0.0

        # Normality
        sw_stat, sw_p = stats.shapiro(arr[:5000]) if n >= 3 else (0, 0)
        norm_verdict = "Normal" if float(sw_p) > 0.05 else "Likely Normal" if float(sw_p) > 0.01 else "Non-Normal"

        # Capability
        cpk = cp = ppk = ppm = sigma = None
        if usl is not None and lsl is not None and std > 0:
            cpu = (usl - mean) / (3 * std)
            cpl = (mean - lsl) / (3 * std)
            cpk = round(float(min(cpu, cpl)), 4)
            cp  = round(float((usl - lsl) / (6 * std)), 4)
            ppm = round(float(
                (stats.norm.cdf(lsl, mean, std) + (1 - stats.norm.cdf(usl, mean, std))) * 1e6
            ), 1)
            sigma = round(float(min(cpu, cpl) * 3 + 1.5), 3)
            std_overall = float(np.std(arr, ddof=1))
            ppk = round(float(min((usl-mean)/(3*std_overall), (mean-lsl)/(3*std_overall))), 4)

        # SPC: simple I-MR alarms (WE1 only for speed)
        alarms = 0
        in_ctrl = True
        if n >= 8:
            ucl = mean + 3 * std
            lcl = mean - 3 * std
            alarms = int(np.sum((arr > ucl) | (arr < lcl)))
            in_ctrl = alarms == 0

        # Histogram
        counts, edges = np.histogram(arr, bins=min(20, n))
        centers = [(edges[i]+edges[i+1])/2 for i in range(len(edges)-1)]
        bw = float(edges[1] - edges[0])
        x_curve = np.linspace(mean - 4*std, mean + 4*std, 150)
        y_curve  = stats.norm.pdf(x_curve, mean, std) * n * bw if std > 0 else np.zeros(150)

        dataset_stats.append(DatasetStats(
            name=name, n=n,
            mean=round(mean, 5), std=round(std, 5),
            median=round(float(np.median(arr)), 5),
            min_val=round(float(arr.min()), 5), max_val=round(float(arr.max()), 5),
            cpk=cpk, cp=cp, ppk=ppk,
            normality_verdict=norm_verdict, sw_p=round(float(sw_p), 5),
            total_alarms=alarms, in_control=in_ctrl,
            ppm=ppm, sigma_level=sigma,
            histogram={
                "bin_centers": [round(float(c), 5) for c in centers],
                "counts": counts.tolist(),
                "bin_width": round(bw, 6),
                "curve_x": [round(float(v), 5) for v in x_curve],
                "curve_y": [round(float(v), 6) for v in y_curve],
            },
            values=arr.tolist(),
        ))

    # ── Statistical comparisons ───────────────────────────────────────────────
    # ANOVA
    f_stat, anova_p = stats.f_oneway(*groups)
    anova_p = float(anova_p)

    # Levene variance test
    lev_stat, lev_p = stats.levene(*groups)
    lev_p = float(lev_p)

    # Kruskal-Wallis
    h_stat, krus_p = stats.kruskal(*groups)
    krus_p = float(krus_p)

    # Pairwise t-tests
    pairwise = []
    for i, j in combinations(range(len(clean)), 2):
        t, p = stats.ttest_ind(groups[i], groups[j], equal_var=(lev_p >= alpha))
        diff = float(np.mean(groups[i]) - np.mean(groups[j]))
        pooled_std = np.sqrt((np.var(groups[i], ddof=1) + np.var(groups[j], ddof=1)) / 2)
        d = float(diff / pooled_std) if pooled_std > 0 else 0.0
        pairwise.append({
            "pair": f"{names[i]} vs {names[j]}",
            "name_a": names[i], "name_b": names[j],
            "t_stat": round(float(t), 4),
            "p_value": round(float(p), 5),
            "significant": bool(float(p) < alpha),
            "mean_diff": round(diff, 5),
            "effect_size": round(d, 4),
            "effect_label": "Large" if abs(d) > 0.8 else "Medium" if abs(d) > 0.5 else "Small" if abs(d) > 0.2 else "Negligible",
        })

    # Rankings
    cpk_vals = [(ds.name, ds.cpk) for ds in dataset_stats if ds.cpk is not None]
    best_cpk  = max(cpk_vals, key=lambda x: x[1])[0] if cpk_vals else names[0]
    worst_cpk = min(cpk_vals, key=lambda x: x[1])[0] if cpk_vals else names[-1]
    most_stable = min(dataset_stats, key=lambda ds: ds.total_alarms).name

    # ── Chart data ────────────────────────────────────────────────────────────
    colors = ["rgba(45,212,160,0.7)", "rgba(96,165,250,0.7)", "rgba(240,180,41,0.7)",
              "rgba(248,113,113,0.7)", "rgba(167,139,250,0.7)", "rgba(34,211,238,0.7)"]

    chart_data = {
        "names": names,
        "colors": colors[:len(names)],
        "means": [ds.mean for ds in dataset_stats],
        "stds":  [ds.std  for ds in dataset_stats],
        "cpks":  [ds.cpk  for ds in dataset_stats],
        "ppms":  [ds.ppm  for ds in dataset_stats],
        "alarms":[ds.total_alarms for ds in dataset_stats],
        "histograms": [ds.histogram for ds in dataset_stats],
        "usl": usl, "lsl": lsl,
        "pairwise": pairwise,
    }

    # Conclusion
    sig_pairs = [p["pair"] for p in pairwise if p["significant"]]
    conclusion = (
        f"{'Significant' if anova_p < alpha else 'No significant'} difference between datasets "
        f"(ANOVA p={anova_p:.4f}). "
        + (f"Significantly different pairs: {', '.join(sig_pairs)}. " if sig_pairs else "")
        + (f"Best Cpk: {best_cpk}. " if cpk_vals else "")
        + f"Most stable (fewest alarms): {most_stable}."
    )

    rec_parts = []
    if anova_p < alpha:
        rec_parts.append(f"Investigate why {sig_pairs[0]} differ — check recipe, maintenance logs, and material lots.")
    if lev_p < alpha:
        rec_parts.append("Variances differ across datasets — check for inconsistent process conditions.")
    if not rec_parts:
        rec_parts.append("Datasets appear statistically equivalent. Process is consistent across compared conditions.")

    return ComparisonResult(
        parameter=parameter,
        datasets=dataset_stats,
        n_datasets=len(datasets),
        anova_p=round(anova_p, 5),
        anova_significant=bool(anova_p < alpha),
        levene_p=round(lev_p, 5),
        variances_equal=bool(lev_p >= alpha),
        kruskal_p=round(krus_p, 5),
        kruskal_significant=bool(krus_p < alpha),
        pairwise=pairwise,
        best_cpk_dataset=best_cpk,
        worst_cpk_dataset=worst_cpk,
        most_stable_dataset=most_stable,
        chart_data=chart_data,
        conclusion=conclusion,
        recommendation=" ".join(rec_parts),
    )
