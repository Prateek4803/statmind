"""
StatMind E9 — Attribute Agreement Analysis (AAA)
Inspector pass/fail agreement. Kappa statistic.
Fleiss' kappa for multiple appraisers.
References: AIAG MSA 4th Ed, ISO 25178
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from itertools import combinations


@dataclass
class AAAResult:
    # Study design
    n_samples: int
    n_appraisers: int
    n_replicates: int
    appraiser_names: list
    # Cohen's / Fleiss' kappa
    fleiss_kappa: float
    kappa_interpretation: str
    # Per-appraiser stats
    appraiser_stats: list     # [{name, agree_with_ref_pct, agree_within_pct, kappa}]
    # Appraiser vs reference
    within_appraiser: list    # [{name, replicate_agreement_pct}]
    between_appraisers: float # % of samples all appraisers agree
    # Disagreement details
    disagreement_samples: list  # sample indices where appraisers disagree
    # Overall verdict
    verdict: str
    verdict_detail: str
    # Chart data
    chart_data: dict
    conclusion: str


def _cohen_kappa(ratings_a, ratings_b):
    """Cohen's kappa for two raters."""
    n = len(ratings_a)
    if n == 0:
        return 0.0
    categories = list(set(ratings_a) | set(ratings_b))
    # Observed agreement
    p_obs = sum(a == b for a, b in zip(ratings_a, ratings_b)) / n
    # Expected agreement
    p_exp = sum(
        (ratings_a.count(c) / n) * (ratings_b.count(c) / n)
        for c in categories
    )
    if p_exp >= 1.0:
        return 1.0
    return float((p_obs - p_exp) / (1.0 - p_exp))


def _fleiss_kappa(ratings_matrix):
    """
    Fleiss' kappa for multiple raters.
    ratings_matrix: n_samples × n_raters, values are category labels (strings)
    """
    n_samples, n_raters = ratings_matrix.shape
    categories = list(set(ratings_matrix.flatten()))
    k = len(categories)
    if k < 2:
        return 1.0  # perfect agreement if only one category

    # Count matrix: n_samples × n_categories
    count_matrix = np.zeros((n_samples, k))
    for i, cat in enumerate(categories):
        count_matrix[:, i] = (ratings_matrix == cat).sum(axis=1)

    # p_j = proportion of all assignments in category j
    p_j = count_matrix.sum(axis=0) / (n_samples * n_raters)

    # P_i = proportion of rater pairs agreeing for sample i
    P_i = (count_matrix * (count_matrix - 1)).sum(axis=1) / (n_raters * (n_raters - 1))

    P_bar = float(P_i.mean())
    P_e   = float((p_j**2).sum())

    if P_e >= 1.0:
        return 1.0
    return float((P_bar - P_e) / (1.0 - P_e))


def _kappa_interpretation(kappa: float) -> str:
    if kappa < 0:      return "Poor agreement (worse than chance)"
    if kappa < 0.20:   return "Slight agreement"
    if kappa < 0.40:   return "Fair agreement"
    if kappa < 0.60:   return "Moderate agreement"
    if kappa < 0.75:   return "Good agreement"
    if kappa < 0.90:   return "Very good agreement"
    return "Excellent agreement (near perfect)"


def analyze_aaa(
    decisions: np.ndarray,   # shape: (n_samples × n_replicates × n_appraisers) or flat
    sample_ids: np.ndarray,
    appraiser_ids: np.ndarray,
    replicate_ids: np.ndarray,
    reference: np.ndarray = None,  # optional ground truth per sample
) -> AAAResult:
    """
    Attribute Agreement Analysis.
    decisions: array of "Pass"/"Fail" (or any binary/categorical labels)
    """
    decisions    = np.array(decisions,    dtype=str)
    sample_ids   = np.array(sample_ids,   dtype=str)
    appraiser_ids= np.array(appraiser_ids,dtype=str)
    replicate_ids= np.array(replicate_ids,dtype=str)

    unique_samples   = np.unique(sample_ids)
    unique_appraisers= np.unique(appraiser_ids)
    unique_reps      = np.unique(replicate_ids)
    n_s = len(unique_samples)
    n_a = len(unique_appraisers)
    n_r = len(unique_reps)

    # Build matrix: n_samples × (n_appraisers × n_replicates)
    # For Fleiss' kappa use majority vote per appraiser per sample
    # majority_matrix: n_samples × n_appraisers (majority vote of replicates)
    majority_matrix = np.empty((n_s, n_a), dtype=object)
    for i, samp in enumerate(unique_samples):
        for j, app in enumerate(unique_appraisers):
            mask = (sample_ids == samp) & (appraiser_ids == app)
            votes = decisions[mask].tolist()
            if votes:
                from collections import Counter
                majority_matrix[i, j] = Counter(votes).most_common(1)[0][0]
            else:
                majority_matrix[i, j] = "Unknown"

    # Fleiss' kappa across all appraisers
    fk = _fleiss_kappa(majority_matrix)

    # Per-appraiser stats
    appraiser_stats = []
    for j, app in enumerate(unique_appraisers):
        # Within-appraiser: do replicates agree?
        within_agree = 0
        total_samples = 0
        for i, samp in enumerate(unique_samples):
            mask = (sample_ids == samp) & (appraiser_ids == app)
            votes = decisions[mask].tolist()
            if len(votes) > 1:
                total_samples += 1
                if len(set(votes)) == 1:
                    within_agree += 1
        within_pct = round(within_agree / total_samples * 100, 1) if total_samples > 0 else 100.0

        # vs reference
        ref_agree_pct = None
        appraiser_kappa = None
        if reference is not None:
            ref_dict = {str(s): str(r) for s, r in zip(unique_samples, reference[:len(unique_samples)])}
            app_votes = [str(majority_matrix[i, j]) for i in range(n_s)]
            ref_votes = [ref_dict.get(str(s), "Unknown") for s in unique_samples]
            matches = sum(a == r for a, r in zip(app_votes, ref_votes))
            ref_agree_pct = round(matches / n_s * 100, 1)
            appraiser_kappa = round(_cohen_kappa(app_votes, ref_votes), 4)

        appraiser_stats.append({
            "name": str(app),
            "within_agreement_pct": within_pct,
            "vs_reference_pct": ref_agree_pct,
            "kappa": appraiser_kappa,
        })

    # Between appraisers: % of samples where ALL appraisers agree
    all_agree = sum(1 for i in range(n_s) if len(set(majority_matrix[i, :])) == 1)
    between_pct = round(all_agree / n_s * 100, 1)

    # Disagreement samples
    disagree_samples = [str(unique_samples[i]) for i in range(n_s)
                        if len(set(majority_matrix[i, :])) > 1]

    # Verdict
    if fk >= 0.75:
        verdict, detail = "Acceptable", "Appraiser agreement is sufficient for production use."
    elif fk >= 0.60:
        verdict, detail = "Marginal", "Some appraisers or samples show disagreement. Training recommended."
    else:
        verdict, detail = "Unacceptable", "Appraiser agreement is too low. Measurement system is unreliable for attribute decisions."

    # Chart data: agreement matrix heatmap
    agree_matrix = []
    for i in range(n_s):
        row = []
        for j in range(n_a):
            row.append(str(majority_matrix[i, j]))
        agree_matrix.append(row)

    chart_data = {
        "agree_matrix": agree_matrix,
        "sample_labels": unique_samples.tolist(),
        "appraiser_labels": unique_appraisers.tolist(),
        "fleiss_kappa": round(fk, 4),
        "between_agreement_pct": between_pct,
        "appraiser_within_pcts": [s["within_agreement_pct"] for s in appraiser_stats],
    }

    conclusion = (
        f"Fleiss' κ = {fk:.4f} — {_kappa_interpretation(fk)}. "
        f"All-appraiser agreement: {between_pct}% of samples. "
        f"{len(disagree_samples)} of {n_s} samples had appraiser disagreements."
    )

    return AAAResult(
        n_samples=n_s, n_appraisers=n_a, n_replicates=n_r,
        appraiser_names=unique_appraisers.tolist(),
        fleiss_kappa=round(fk, 4),
        kappa_interpretation=_kappa_interpretation(fk),
        appraiser_stats=appraiser_stats,
        within_appraiser=[{"name": s["name"], "within_pct": s["within_agreement_pct"]} for s in appraiser_stats],
        between_appraisers=between_pct,
        disagreement_samples=disagree_samples,
        verdict=verdict, verdict_detail=detail,
        chart_data=chart_data,
        conclusion=conclusion,
    )
