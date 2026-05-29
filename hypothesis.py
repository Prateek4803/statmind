"""
StatMind E1 — Hypothesis Testing Engine
Tests: 2-sample t, paired t, 1-way ANOVA, 2-way ANOVA,
       Chi-square, Mann-Whitney, Kruskal-Wallis, F-test (variance equality)
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


@dataclass
class HypothesisResult:
    test_name: str
    test_statistic: float
    p_value: float
    alpha: float
    reject_null: bool
    # Plain English
    null_hypothesis: str
    alt_hypothesis: str
    conclusion: str          # plain English verdict
    practical_significance: str
    effect_size: Optional[float]
    effect_size_label: str   # "Cohen's d", "eta²", "Cramér's V" etc
    effect_interpretation: str  # "small / medium / large"
    # Extra details
    confidence_interval: Optional[tuple]
    ci_label: str
    group_stats: list        # [{"name","n","mean","std","median"}]
    # Chart data
    chart_data: dict


def _cohen_d(a, b):
    """Cohen's d effect size for two groups."""
    na, nb = len(a), len(b)
    pooled = np.sqrt(((na-1)*np.var(a,ddof=1) + (nb-1)*np.var(b,ddof=1)) / (na+nb-2))
    return float((np.mean(a) - np.mean(b)) / pooled) if pooled > 0 else 0.0

def _eta_squared(groups):
    """Eta² effect size for ANOVA."""
    all_data = np.concatenate(groups)
    grand_mean = np.mean(all_data)
    ss_between = sum(len(g)*(np.mean(g)-grand_mean)**2 for g in groups)
    ss_total   = np.sum((all_data - grand_mean)**2)
    return float(ss_between / ss_total) if ss_total > 0 else 0.0

def _effect_label(val, thresholds):
    """Label effect size as small/medium/large."""
    abs_val = abs(val)
    if abs_val < thresholds[0]:   return "Negligible"
    elif abs_val < thresholds[1]: return "Small"
    elif abs_val < thresholds[2]: return "Medium"
    else:                          return "Large"

def _group_stats(groups, names):
    return [{"name": names[i], "n": int(len(g)),
             "mean": round(float(np.mean(g)), 5),
             "std":  round(float(np.std(g, ddof=1)), 5),
             "median": round(float(np.median(g)), 5),
             "min": round(float(np.min(g)), 5),
             "max": round(float(np.max(g)), 5)}
            for i, g in enumerate(groups)]

def _boxplot_data(groups, names):
    """Compute box plot quartiles for chart rendering."""
    result = []
    for i, g in enumerate(groups):
        q1, med, q3 = np.percentile(g, [25, 50, 75])
        iqr = q3 - q1
        whisker_lo = float(np.min(g[g >= q1 - 1.5*iqr])) if any(g >= q1 - 1.5*iqr) else float(np.min(g))
        whisker_hi = float(np.max(g[g <= q3 + 1.5*iqr])) if any(g <= q3 + 1.5*iqr) else float(np.max(g))
        outliers   = g[(g < q1 - 1.5*iqr) | (g > q3 + 1.5*iqr)].tolist()
        result.append({"name": names[i], "q1": float(q1), "median": float(med),
                       "q3": float(q3), "whisker_lo": whisker_lo,
                       "whisker_hi": whisker_hi, "outliers": outliers,
                       "mean": float(np.mean(g))})
    return result


# ── 2-Sample t-test ───────────────────────────────────────────────────────────

def two_sample_t(a: np.ndarray, b: np.ndarray,
                 name_a="Group A", name_b="Group B",
                 alpha=0.05, equal_var=False) -> HypothesisResult:
    """Welch t-test (default) or pooled t-test."""
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    t, p = stats.ttest_ind(a, b, equal_var=equal_var)
    reject = p < alpha
    d = _cohen_d(a, b)
    diff = float(np.mean(a) - np.mean(b))
    # CI on difference
    se = np.sqrt(np.var(a,ddof=1)/len(a) + np.var(b,ddof=1)/len(b))
    t_crit = stats.t.ppf(1-alpha/2, df=len(a)+len(b)-2)
    ci = (round(diff - t_crit*se, 5), round(diff + t_crit*se, 5))

    test_type = "Pooled 2-Sample t-Test" if equal_var else "Welch 2-Sample t-Test"
    conclusion = (
        f"There IS a statistically significant difference between {name_a} and {name_b} "
        f"(p={p:.4f} < α={alpha}). Mean difference = {diff:+.4f}."
        if reject else
        f"There is NO statistically significant difference between {name_a} and {name_b} "
        f"(p={p:.4f} ≥ α={alpha}). Insufficient evidence to reject H₀."
    )
    practical = (
        f"Effect size (Cohen's d = {abs(d):.3f}) is {_effect_label(d,[0.2,0.5,0.8])}. "
        + ("Practically meaningful difference." if abs(d) > 0.5 else "May not be practically significant even if statistically significant." if abs(d) > 0.2 else "Practically negligible difference.")
    )
    return HypothesisResult(
        test_name=test_type, test_statistic=round(float(t),5),
        p_value=round(float(p),5), alpha=alpha, reject_null=bool(reject),
        null_hypothesis=f"μ({name_a}) = μ({name_b})  (no difference)",
        alt_hypothesis=f"μ({name_a}) ≠ μ({name_b})  (two-tailed)",
        conclusion=conclusion, practical_significance=practical,
        effect_size=round(d,4), effect_size_label="Cohen's d",
        effect_interpretation=_effect_label(d,[0.2,0.5,0.8]),
        confidence_interval=ci,
        ci_label=f"{int((1-alpha)*100)}% CI on mean difference ({name_a}−{name_b})",
        group_stats=_group_stats([a,b],[name_a,name_b]),
        chart_data={"type":"boxplot","groups":_boxplot_data([a,b],[name_a,name_b]),
                    "raw":{"a":a.tolist(),"b":b.tolist()}},
    )


# ── Paired t-test ─────────────────────────────────────────────────────────────

def paired_t(a: np.ndarray, b: np.ndarray,
             name_a="Before", name_b="After", alpha=0.05) -> HypothesisResult:
    mask = ~(np.isnan(a) | np.isnan(b))
    a, b = a[mask], b[mask]
    diff_data = a - b
    t, p = stats.ttest_rel(a, b)
    reject = p < alpha
    mean_diff = float(np.mean(diff_data))
    se_diff = float(np.std(diff_data,ddof=1)/np.sqrt(len(diff_data)))
    t_crit = stats.t.ppf(1-alpha/2, df=len(diff_data)-1)
    ci = (round(mean_diff - t_crit*se_diff,5), round(mean_diff + t_crit*se_diff,5))
    d = float(mean_diff / np.std(diff_data,ddof=1)) if np.std(diff_data,ddof=1)>0 else 0.0
    conclusion = (
        f"The {name_a} vs {name_b} difference IS statistically significant "
        f"(p={p:.4f} < α={alpha}). Mean change = {mean_diff:+.4f}."
        if reject else
        f"No statistically significant change detected between {name_a} and {name_b} "
        f"(p={p:.4f} ≥ α={alpha})."
    )
    return HypothesisResult(
        test_name="Paired t-Test",
        test_statistic=round(float(t),5), p_value=round(float(p),5),
        alpha=alpha, reject_null=bool(reject),
        null_hypothesis=f"μ(difference) = 0  (no change)",
        alt_hypothesis=f"μ(difference) ≠ 0  (two-tailed)",
        conclusion=conclusion,
        practical_significance=f"Cohen's d = {abs(d):.3f} ({_effect_label(d,[0.2,0.5,0.8])} effect). n={len(diff_data)} pairs.",
        effect_size=round(d,4), effect_size_label="Cohen's d",
        effect_interpretation=_effect_label(d,[0.2,0.5,0.8]),
        confidence_interval=ci,
        ci_label=f"{int((1-alpha)*100)}% CI on mean difference ({name_a}−{name_b})",
        group_stats=_group_stats([a,b,diff_data],[name_a,name_b,"Difference"]),
        chart_data={"type":"paired","before":a.tolist(),"after":b.tolist(),"diff":diff_data.tolist()},
    )


# ── One-way ANOVA ─────────────────────────────────────────────────────────────

def one_way_anova(groups: list, names: list, alpha=0.05) -> HypothesisResult:
    """One-way ANOVA with Tukey HSD post-hoc."""
    clean = [g[~np.isnan(g)] for g in groups]
    f, p = stats.f_oneway(*clean)
    reject = p < alpha
    eta2 = _eta_squared(clean)
    k = len(clean)
    n_total = sum(len(g) for g in clean)

    # Tukey HSD post-hoc
    from itertools import combinations
    tukey_results = []
    mse = sum((len(g)-1)*np.var(g,ddof=1) for g in clean) / (n_total - k)
    for i, j in combinations(range(k), 2):
        diff = float(np.mean(clean[i]) - np.mean(clean[j]))
        se = np.sqrt(mse * (1/len(clean[i]) + 1/len(clean[j])))
        q = abs(diff) / se if se > 0 else 0
        # Approximate p-value using studentized range
        p_tukey = float(stats.studentized_range.sf(q*np.sqrt(2), k, n_total-k))
        tukey_results.append({
            "group_a": names[i], "group_b": names[j],
            "diff": round(diff, 5),
            "p_value": round(p_tukey, 5),
            "significant": bool(p_tukey < alpha),
        })

    means = [float(np.mean(g)) for g in clean]
    best = names[int(np.argmax(means))]
    worst = names[int(np.argmin(means))]
    sig_pairs = [f"{r['group_a']}≠{r['group_b']}" for r in tukey_results if r["significant"]]

    conclusion = (
        f"At least one group mean is significantly different (F={f:.3f}, p={p:.4f} < α={alpha}). "
        f"Post-hoc (Tukey): {', '.join(sig_pairs) if sig_pairs else 'No pairs differ after correction'}."
        if reject else
        f"No significant difference between any group means (F={f:.3f}, p={p:.4f} ≥ α={alpha})."
    )
    return HypothesisResult(
        test_name="One-Way ANOVA",
        test_statistic=round(float(f),5), p_value=round(float(p),5),
        alpha=alpha, reject_null=bool(reject),
        null_hypothesis="All group means are equal (μ₁ = μ₂ = … = μₖ)",
        alt_hypothesis="At least one group mean differs",
        conclusion=conclusion,
        practical_significance=f"η² = {eta2:.4f} ({_effect_label(eta2,[0.01,0.06,0.14])} effect). Explains {eta2*100:.1f}% of total variation.",
        effect_size=round(eta2,4), effect_size_label="η² (eta squared)",
        effect_interpretation=_effect_label(eta2,[0.01,0.06,0.14]),
        confidence_interval=None, ci_label="",
        group_stats=_group_stats(clean, names),
        chart_data={"type":"boxplot","groups":_boxplot_data(clean,names),
                    "tukey":tukey_results},
    )


# ── Two-way ANOVA ─────────────────────────────────────────────────────────────

def two_way_anova(data: np.ndarray, factor_a: np.ndarray, factor_b: np.ndarray,
                  name_a="Factor A", name_b="Factor B", alpha=0.05) -> HypothesisResult:
    """Two-way ANOVA using OLS."""
    try:
        import pandas as pd
        from statsmodels.formula.api import ols
        from statsmodels.stats.anova import anova_lm
        df = pd.DataFrame({"y": data, "A": factor_a.astype(str), "B": factor_b.astype(str)})
        model = ols("y ~ C(A) + C(B) + C(A):C(B)", data=df).fit()
        table = anova_lm(model, typ=2)
        p_a   = float(table.loc["C(A)", "PR(>F)"])
        p_b   = float(table.loc["C(B)", "PR(>F)"])
        p_int = float(table.loc["C(A):C(B)", "PR(>F)"])
        f_a   = float(table.loc["C(A)", "F"])
        f_b   = float(table.loc["C(B)", "F"])
        f_int = float(table.loc["C(A):C(B)", "F"])
        ss_total = float(table["sum_sq"].sum())
        eta2_a = float(table.loc["C(A)","sum_sq"]/ss_total)
        eta2_b = float(table.loc["C(B)","sum_sq"]/ss_total)
        eta2_int = float(table.loc["C(A):C(B)","sum_sq"]/ss_total)

        lines = []
        if p_a < alpha:   lines.append(f"{name_a} is significant (F={f_a:.3f}, p={p_a:.4f})")
        if p_b < alpha:   lines.append(f"{name_b} is significant (F={f_b:.3f}, p={p_b:.4f})")
        if p_int < alpha: lines.append(f"Interaction {name_a}×{name_b} is significant (F={f_int:.3f}, p={p_int:.4f}) — effect of one factor depends on level of the other")
        conclusion = ". ".join(lines) if lines else "No significant main effects or interaction detected."

        anova_table = [
            {"source": name_a, "ss": round(float(table.loc["C(A)","sum_sq"]),5), "df": int(table.loc["C(A)","df"]), "f": round(f_a,4), "p": round(p_a,5), "eta2": round(eta2_a,4)},
            {"source": name_b, "ss": round(float(table.loc["C(B)","sum_sq"]),5), "df": int(table.loc["C(B)","df"]), "f": round(f_b,4), "p": round(p_b,5), "eta2": round(eta2_b,4)},
            {"source": f"{name_a}×{name_b}", "ss": round(float(table.loc["C(A):C(B)","sum_sq"]),5), "df": int(table.loc["C(A):C(B)","df"]), "f": round(f_int,4), "p": round(p_int,5), "eta2": round(eta2_int,4)},
        ]
        overall_p = min(p_a, p_b, p_int)
        return HypothesisResult(
            test_name="Two-Way ANOVA",
            test_statistic=round(f_a,5), p_value=round(overall_p,5),
            alpha=alpha, reject_null=bool(overall_p < alpha),
            null_hypothesis=f"No main effects of {name_a}, {name_b}, or their interaction",
            alt_hypothesis=f"At least one main effect or interaction is significant",
            conclusion=conclusion,
            practical_significance=f"η²: {name_a}={eta2_a:.3f}, {name_b}={eta2_b:.3f}, Interaction={eta2_int:.3f}",
            effect_size=round(max(eta2_a,eta2_b,eta2_int),4),
            effect_size_label="η² (largest)",
            effect_interpretation=_effect_label(max(eta2_a,eta2_b,eta2_int),[0.01,0.06,0.14]),
            confidence_interval=None, ci_label="",
            group_stats=[],
            chart_data={"type":"two_way_anova","anova_table":anova_table},
        )
    except Exception as e:
        raise ValueError(f"Two-way ANOVA failed: {e}")


# ── Mann-Whitney U (non-parametric 2-sample) ──────────────────────────────────

def mann_whitney(a: np.ndarray, b: np.ndarray,
                 name_a="Group A", name_b="Group B", alpha=0.05) -> HypothesisResult:
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    u, p = stats.mannwhitneyu(a, b, alternative='two-sided')
    reject = p < alpha
    # rank-biserial correlation as effect size
    r = 1 - (2*u)/(len(a)*len(b))
    conclusion = (
        f"Medians of {name_a} and {name_b} ARE significantly different (U={u:.1f}, p={p:.4f} < α={alpha}). "
        f"Median({name_a})={np.median(a):.4f}, Median({name_b})={np.median(b):.4f}."
        if reject else
        f"No significant difference in medians between {name_a} and {name_b} (U={u:.1f}, p={p:.4f} ≥ α={alpha})."
    )
    return HypothesisResult(
        test_name="Mann-Whitney U Test (non-parametric)",
        test_statistic=round(float(u),3), p_value=round(float(p),5),
        alpha=alpha, reject_null=bool(reject),
        null_hypothesis=f"Distributions of {name_a} and {name_b} are identical",
        alt_hypothesis=f"Distributions differ (two-tailed)",
        conclusion=conclusion,
        practical_significance=f"Rank-biserial r = {r:.3f} ({_effect_label(r,[0.1,0.3,0.5])} effect). Use when data is non-normal.",
        effect_size=round(float(r),4), effect_size_label="Rank-biserial r",
        effect_interpretation=_effect_label(r,[0.1,0.3,0.5]),
        confidence_interval=None, ci_label="",
        group_stats=_group_stats([a,b],[name_a,name_b]),
        chart_data={"type":"boxplot","groups":_boxplot_data([a,b],[name_a,name_b])},
    )


# ── Kruskal-Wallis (non-parametric k-sample) ──────────────────────────────────

def kruskal_wallis(groups: list, names: list, alpha=0.05) -> HypothesisResult:
    clean = [g[~np.isnan(g)] for g in groups]
    h, p = stats.kruskal(*clean)
    reject = p < alpha
    k, n = len(clean), sum(len(g) for g in clean)
    eta2_h = (h - k + 1) / (n - k)
    conclusion = (
        f"At least one group distribution differs significantly (H={h:.3f}, p={p:.4f} < α={alpha})."
        if reject else
        f"No significant difference between group distributions (H={h:.3f}, p={p:.4f} ≥ α={alpha})."
    )
    return HypothesisResult(
        test_name="Kruskal-Wallis Test (non-parametric)",
        test_statistic=round(float(h),5), p_value=round(float(p),5),
        alpha=alpha, reject_null=bool(reject),
        null_hypothesis="All group distributions are identical",
        alt_hypothesis="At least one group distribution differs",
        conclusion=conclusion,
        practical_significance=f"η²H = {eta2_h:.4f}. Use when normality assumption cannot be met.",
        effect_size=round(float(eta2_h),4), effect_size_label="η²H",
        effect_interpretation=_effect_label(eta2_h,[0.01,0.06,0.14]),
        confidence_interval=None, ci_label="",
        group_stats=_group_stats(clean,names),
        chart_data={"type":"boxplot","groups":_boxplot_data(clean,names)},
    )


# ── F-test (variance equality / Levene) ──────────────────────────────────────

def variance_test(groups: list, names: list, alpha=0.05) -> HypothesisResult:
    """Levene's test for equality of variances (robust to non-normality)."""
    clean = [g[~np.isnan(g)] for g in groups]
    stat, p = stats.levene(*clean)
    reject = p < alpha
    variances = [round(float(np.var(g,ddof=1)),6) for g in clean]
    conclusion = (
        f"Variances are NOT equal across groups (Levene W={stat:.4f}, p={p:.4f} < α={alpha}). "
        f"Use Welch t-test or non-parametric tests. Variances: {dict(zip(names,variances))}."
        if reject else
        f"Variances are equal across groups (Levene W={stat:.4f}, p={p:.4f} ≥ α={alpha}). "
        f"Pooled t-test assumption is met."
    )
    return HypothesisResult(
        test_name="Levene's Test (Variance Equality)",
        test_statistic=round(float(stat),5), p_value=round(float(p),5),
        alpha=alpha, reject_null=bool(reject),
        null_hypothesis="All group variances are equal (σ₁² = σ₂² = … = σₖ²)",
        alt_hypothesis="At least one group variance differs",
        conclusion=conclusion,
        practical_significance=f"Variance ratio (max/min) = {max(variances)/min(variances):.2f}." if min(variances)>0 else "",
        effect_size=None, effect_size_label="",
        effect_interpretation="",
        confidence_interval=None, ci_label="",
        group_stats=_group_stats(clean,names),
        chart_data={"type":"variance","groups":names,"variances":variances,
                    "std_devs":[round(float(np.std(g,ddof=1)),6) for g in clean]},
    )


# ── Chi-square test of independence ──────────────────────────────────────────

def chi_square(observed: np.ndarray, row_labels=None, col_labels=None, alpha=0.05) -> HypothesisResult:
    """Chi-square test on a contingency table."""
    chi2, p, dof, expected = stats.chi2_contingency(observed)
    reject = p < alpha
    n = observed.sum()
    cramers_v = float(np.sqrt(chi2 / (n * (min(observed.shape) - 1)))) if min(observed.shape)>1 else 0
    conclusion = (
        f"There IS a significant association between the variables (χ²={chi2:.4f}, df={dof}, p={p:.4f} < α={alpha})."
        if reject else
        f"No significant association detected (χ²={chi2:.4f}, df={dof}, p={p:.4f} ≥ α={alpha})."
    )
    return HypothesisResult(
        test_name="Chi-Square Test of Independence",
        test_statistic=round(float(chi2),5), p_value=round(float(p),5),
        alpha=alpha, reject_null=bool(reject),
        null_hypothesis="The two categorical variables are independent",
        alt_hypothesis="The variables are associated (not independent)",
        conclusion=conclusion,
        practical_significance=f"Cramér's V = {cramers_v:.4f} ({_effect_label(cramers_v,[0.1,0.3,0.5])} association).",
        effect_size=round(cramers_v,4), effect_size_label="Cramér's V",
        effect_interpretation=_effect_label(cramers_v,[0.1,0.3,0.5]),
        confidence_interval=None, ci_label="",
        group_stats=[],
        chart_data={"type":"contingency","observed":observed.tolist(),"expected":expected.round(2).tolist(),
                    "row_labels":row_labels,"col_labels":col_labels},
    )
