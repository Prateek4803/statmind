"""
StatMind — Session 1: Normality Testing Engine
Tests: Anderson-Darling, Shapiro-Wilk, Ryan-Joiner
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import anderson, shapiro
from dataclasses import dataclass, asdict
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


def _welford_std(data: np.ndarray, ddof: int = 1) -> float:
    """Numerically stable one-pass variance (Welford 1962)."""
    n_pts = len(data)
    if n_pts <= 1:
        return 0.0
    if n_pts > 50_000:
        shift = float(data[0])
        shifted = data.astype(np.float64) - shift
        mean_s = float(shifted.mean())
        M2 = float(np.sum((shifted - mean_s) ** 2))
        return float(np.sqrt(M2 / max(n_pts - ddof, 1)))
    n, mean, M2 = 0, 0.0, 0.0
    for x in data:
        n += 1
        delta = x - mean
        mean += delta / n
        M2 += delta * (x - mean)
    return float(np.sqrt(M2 / max(n - ddof, 1)))


@dataclass
class NormalityTestResult:
    test_name: str
    statistic: float
    p_value: Optional[float]
    critical_value: Optional[float]
    alpha: float
    reject_null: bool  # True = NOT normal
    interpretation: str


@dataclass
class CapabilityHint:
    recommended_approach: str
    reason: str
    downstream_notes: list[str]


@dataclass
class NormalityReport:
    column: str
    n: int
    mean: float
    std: float
    min_val: float
    max_val: float
    skewness: float
    kurtosis: float
    shapiro_wilk: NormalityTestResult
    anderson_darling: NormalityTestResult
    ryan_joiner: NormalityTestResult
    overall_verdict: str        # "Normal", "Likely Normal", "Non-Normal"
    confidence: str             # "High", "Medium", "Low"
    capability_hint: CapabilityHint
    histogram_data: dict
    probability_plot_data: dict


def run_shapiro_wilk(data: np.ndarray, alpha=0.05) -> NormalityTestResult:
    # Shapiro-Wilk is unreliable for n > 5000 — sample for large datasets
    test_data = data
    n_full = len(data)
    sampled = False
    if n_full > 5000:
        rng = np.random.default_rng(42)
        test_data = rng.choice(data, size=5000, replace=False)
        sampled = True
    stat, p = shapiro(test_data)
    reject = p < alpha
    note = f" (test used random sample n=5000 of {n_full})" if sampled else ""
    interp = (
        f"p={p:.4f} {'< ' if reject else '>= '}{alpha}{note}: "
        + ("Evidence AGAINST normality." if reject else "No evidence against normality.")
    )
    return NormalityTestResult(
        test_name="Shapiro-Wilk",
        statistic=round(float(stat), 5),
        p_value=round(float(p), 5),
        critical_value=None,
        alpha=alpha,
        reject_null=bool(reject),
        interpretation=interp
    )


def run_anderson_darling(data: np.ndarray, alpha=0.05) -> NormalityTestResult:
    result = anderson(data, dist='norm')
    # Map alpha to index: 15%, 10%, 5%, 2.5%, 1%
    alpha_map = {0.15: 0, 0.10: 1, 0.05: 2, 0.025: 3, 0.01: 4}
    idx = alpha_map.get(alpha, 2)
    critical = result.critical_values[idx]
    reject = result.statistic > critical
    p_approx = _ad_p_value(result.statistic)
    interp = (
        f"A²={result.statistic:.4f}, CV={critical:.4f} at {alpha*100:.0f}%: "
        + ("Evidence AGAINST normality." if reject else "No evidence against normality.")
    )
    return NormalityTestResult(
        test_name="Anderson-Darling",
        statistic=round(float(result.statistic), 5),
        p_value=round(float(p_approx), 5),
        critical_value=round(float(critical), 5),
        alpha=alpha,
        reject_null=bool(reject),
        interpretation=interp
    )


def _ad_p_value(A2: float) -> float:
    """Approximate p-value for Anderson-Darling statistic."""
    if A2 >= 0.6:
        p = np.exp(1.2937 - 5.709 * A2 + 0.0186 * A2**2)
    elif A2 >= 0.34:
        p = np.exp(0.9177 - 4.279 * A2 - 1.38 * A2**2)
    elif A2 >= 0.2:
        p = 1 - np.exp(-8.318 + 42.796 * A2 - 59.938 * A2**2)
    else:
        p = 1 - np.exp(-13.436 + 101.14 * A2 - 223.73 * A2**2)
    return float(np.clip(p, 0.0001, 0.9999))


def run_ryan_joiner(data: np.ndarray, alpha=0.05) -> NormalityTestResult:
    """
    Ryan-Joiner test (similar to Shapiro-Francia for n>50).
    Correlation between ordered data and normal scores.
    """
    n = len(data)
    sorted_data = np.sort(data)
    # Normal scores (Blom formula)
    i = np.arange(1, n + 1)
    p_i = (i - 0.375) / (n + 0.25)
    normal_scores = stats.norm.ppf(p_i)
    # Correlation coefficient
    rj_stat = float(np.corrcoef(sorted_data, normal_scores)[0, 1])
    # Critical value approximation (Looney & Gulledge 1985)
    critical = _rj_critical(n, alpha)
    reject = rj_stat < critical
    # Approximate p-value
    p_approx = _rj_p_value(rj_stat, n)
    interp = (
        f"RJ={rj_stat:.5f}, CV={critical:.5f} at {alpha*100:.0f}%: "
        + ("Evidence AGAINST normality." if reject else "No evidence against normality.")
    )
    return NormalityTestResult(
        test_name="Ryan-Joiner",
        statistic=round(rj_stat, 5),
        p_value=round(p_approx, 5),
        critical_value=round(critical, 5),
        alpha=alpha,
        reject_null=bool(reject),
        interpretation=interp
    )


def _rj_critical(n: int, alpha: float) -> float:
    """Critical values for Ryan-Joiner test."""
    # Coefficients from Looney & Gulledge (1985)
    if alpha == 0.05:
        return 1.0 - (1.671 / (n**0.5)) + (0.459 / n) - (0.069 / (n**1.5))
    elif alpha == 0.01:
        return 1.0 - (2.273 / (n**0.5)) + (0.459 / n) - (0.069 / (n**1.5))
    else:  # 0.10
        return 1.0 - (1.341 / (n**0.5)) + (0.459 / n) - (0.069 / (n**1.5))


def _rj_p_value(rj: float, n: int) -> float:
    """Approximate p-value using normal approximation."""
    mu = 1.0 - 0.93 / (n**0.5)
    sigma = 0.12 / (n**0.5)
    z = (rj - mu) / sigma
    p = float(stats.norm.cdf(z))
    return float(np.clip(p, 0.0001, 0.9999))


def build_histogram_data(data: np.ndarray) -> dict:
    """Compute histogram bins and normal curve overlay."""
    counts, bin_edges = np.histogram(data, bins='auto')
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    bin_width = bin_edges[1] - bin_edges[0]
    # Normal curve scaled to histogram
    mu, sigma = data.mean(), data.std()
    x_curve = np.linspace(data.min() - sigma, data.max() + sigma, 200)
    y_curve = stats.norm.pdf(x_curve, mu, sigma) * len(data) * bin_width
    return {
        "bin_centers": bin_centers.tolist(),
        "counts": counts.tolist(),
        "bin_width": float(bin_width),
        "curve_x": x_curve.tolist(),
        "curve_y": y_curve.tolist(),
        "mean": float(mu),
        "std": float(sigma),
    }


def build_probability_plot_data(data: np.ndarray) -> dict:
    """Normal probability plot (Q-Q plot) data."""
    n = len(data)
    sorted_data = np.sort(data)
    # Blom plotting positions
    i = np.arange(1, n + 1)
    p_i = (i - 0.375) / (n + 0.25)
    theoretical_quantiles = stats.norm.ppf(p_i)
    # Fit line
    slope, intercept, r, _, _ = stats.linregress(theoretical_quantiles, sorted_data)
    line_x = np.array([theoretical_quantiles[0], theoretical_quantiles[-1]])
    line_y = slope * line_x + intercept
    return {
        "theoretical_quantiles": theoretical_quantiles.tolist(),
        "sample_values": sorted_data.tolist(),
        "fit_line_x": line_x.tolist(),
        "fit_line_y": line_y.tolist(),
        "r_squared": round(float(r**2), 5),
    }


def determine_verdict(sw: NormalityTestResult, ad: NormalityTestResult, rj: NormalityTestResult,
                      n: int, skewness: float, kurtosis: float) -> tuple[str, str]:
    """Aggregate verdict from all three tests."""
    rejections = sum([sw.reject_null, ad.reject_null, rj.reject_null])
    # For small n, tests have low power — be more conservative
    if n < 20:
        if rejections == 0:
            return "Likely Normal", "Medium"
        elif rejections <= 1:
            return "Likely Normal", "Low"
        else:
            return "Non-Normal", "Medium"
    elif n < 50:
        if rejections == 0:
            return "Normal", "High"
        elif rejections == 1:
            return "Likely Normal", "Medium"
        else:
            return "Non-Normal", "High"
    else:
        if rejections == 0:
            if abs(skewness) < 0.5 and abs(kurtosis - 3) < 1:
                return "Normal", "High"
            else:
                return "Likely Normal", "Medium"
        elif rejections == 1:
            return "Likely Normal", "Low"
        else:
            return "Non-Normal", "High"


def build_capability_hint(verdict: str, skewness: float, kurtosis: float, n: int) -> CapabilityHint:
    if verdict == "Normal":
        return CapabilityHint(
            recommended_approach="Standard Cp/Cpk (parametric)",
            reason="Data passes normality tests. Classical capability indices are valid.",
            downstream_notes=[
                "Cp/Cpk and Pp/Ppk calculations are appropriate",
                "Xbar-R or Xbar-S control charts are appropriate",
                "Standard confidence intervals on Cpk are valid",
            ]
        )
    elif verdict == "Likely Normal":
        return CapabilityHint(
            recommended_approach="Standard Cp/Cpk with caution",
            reason=f"Mixed normality results (n={n}). Proceed but verify with larger sample.",
            downstream_notes=[
                "Cp/Cpk likely valid but interpret conservatively",
                "Consider collecting more data to confirm normality",
                "Watch for outliers that may be skewing results",
            ]
        )
    else:
        hints = []
        if abs(skewness) > 1:
            hints.append(f"High skewness ({skewness:.2f}) — consider Box-Cox or log transformation")
        if abs(kurtosis - 3) > 2:
            hints.append(f"Heavy tails (excess kurtosis={kurtosis-3:.2f}) — outlier investigation recommended")
        hints += [
            "Use non-parametric capability (Pp percentile method)",
            "Consider transformation (Box-Cox, Johnson) before classical analysis",
            "I-MR or EWMA charts are robust to non-normality",
        ]
        return CapabilityHint(
            recommended_approach="Non-parametric or transformation required",
            reason="Data is non-normal. Standard Cp/Cpk indices will be misleading.",
            downstream_notes=hints
        )


def analyze_column(data: np.ndarray, column_name: str, alpha=0.05) -> NormalityReport:
    """Run full normality analysis on a single column."""
    data = data[~np.isnan(data)]  # drop NaN
    n = len(data)
    if n < 7:
        raise ValueError(
            f"Column '{column_name}' has only {n} valid data points. "
            "Normality tests require at least 7 observations to be meaningful. "
            "Shapiro-Wilk has very low power below n=7 and will produce unreliable results."
        )

    sw = run_shapiro_wilk(data, alpha)
    ad = run_anderson_darling(data, alpha)
    rj = run_ryan_joiner(data, alpha)

    skewness = float(stats.skew(data))
    kurt = float(stats.kurtosis(data, fisher=False))  # Pearson kurtosis (normal=3)

    verdict, confidence = determine_verdict(sw, ad, rj, n, skewness, kurt)
    cap_hint = build_capability_hint(verdict, skewness, kurt, n)
    hist_data = build_histogram_data(data)
    prob_data = build_probability_plot_data(data)

    return NormalityReport(
        column=column_name,
        n=n,
        mean=round(float(data.mean()), 6),
        std=round(_welford_std(data, ddof=1), 6),
        min_val=round(float(data.min()), 6),
        max_val=round(float(data.max()), 6),
        skewness=round(skewness, 4),
        kurtosis=round(kurt, 4),
        shapiro_wilk=sw,
        anderson_darling=ad,
        ryan_joiner=rj,
        overall_verdict=verdict,
        confidence=confidence,
        capability_hint=cap_hint,
        histogram_data=hist_data,
        probability_plot_data=prob_data,
    )


def parse_uploaded_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Auto-detect and parse Excel or CSV."""
    import io
    buf = io.BytesIO(file_bytes)
    if filename.lower().endswith(('.xlsx', '.xls')):
        df = pd.read_excel(buf, header=0)
    else:
        # Try to auto-detect delimiter
        sample = file_bytes[:2048].decode('utf-8', errors='replace')
        if '\t' in sample:
            sep = '\t'
        elif ';' in sample:
            sep = ';'
        else:
            sep = ','
        buf.seek(0)
        df = pd.read_csv(buf, sep=sep, header=0)
    # Keep only numeric columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    return df[numeric_cols]
