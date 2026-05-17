"""
equivalence_test.py — StatMind TOST Equivalence Testing
Two One-Sided Tests (Schuirmann 1987)
Used for: supplier qualification, process transfer, method comparison
"""

import dataclasses
from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np
from scipy import stats


@dataclass
class TostGroupStats:
    name: str
    n: int
    mean: float
    std: float
    sem: float
    ci_lo: float   # 95% CI lower
    ci_hi: float   # 95% CI upper


@dataclass
class TostTest:
    name: str         # "Lower bound" | "Upper bound"
    hypothesis: str   # H0 statement
    t_stat: float
    df: float
    p_value: float
    passed: bool


@dataclass
class EquivalenceResult:
    name_a: str
    name_b: str
    n_a: int
    n_b: int
    delta: float               # equivalence margin (absolute)
    delta_pct: float           # delta as % of reference mean
    alpha: float
    group_a: TostGroupStats
    group_b: TostGroupStats
    observed_difference: float  # mean_b - mean_a
    tost_tests: List[TostTest]
    equivalent: bool
    confidence_interval: dict   # 90% CI on difference (for TOST at alpha=0.05)
    conclusion: str
    interpretation: str


def tost_equivalence(
    data_a: np.ndarray,
    data_b: np.ndarray,
    delta: float = None,
    alpha: float = 0.05,
    name_a: str = "Reference",
    name_b: str = "Test",
) -> EquivalenceResult:
    """
    Two One-Sided Tests (TOST) for equivalence.
    
    H0_lower: μ_B - μ_A ≤ -δ  (test process is inferior)
    H0_upper: μ_B - μ_A ≥ +δ  (test process is superior/different)
    
    Equivalence is declared when BOTH H0s are rejected (both p < alpha).
    This is the same as checking whether the (1-2α)×100% CI for (μ_B - μ_A)
    falls entirely within (-δ, +δ).
    
    If delta is None, defaults to 5% of the reference mean (industry standard).
    """
    data_a = np.array(data_a, dtype=float)
    data_b = np.array(data_b, dtype=float)
    data_a = data_a[~np.isnan(data_a)]
    data_b = data_b[~np.isnan(data_b)]

    n_a, n_b = len(data_a), len(data_b)
    mean_a, mean_b = float(data_a.mean()), float(data_b.mean())
    std_a = float(data_a.std(ddof=1)) if n_a > 1 else 0.0
    std_b = float(data_b.std(ddof=1)) if n_b > 1 else 0.0

    # Default delta: 5% of reference mean (common for process transfer)
    if delta is None:
        delta = abs(mean_a) * 0.05
    delta = abs(float(delta))

    # Standard error of difference (Welch)
    se = float(np.sqrt(std_a ** 2 / n_a + std_b ** 2 / n_b))
    if se == 0:
        se = 1e-10

    # Welch-Satterthwaite degrees of freedom
    if std_a == 0 and std_b == 0:
        df = n_a + n_b - 2
    else:
        numerator = (std_a ** 2 / n_a + std_b ** 2 / n_b) ** 2
        denominator = ((std_a ** 2 / n_a) ** 2 / max(n_a - 1, 1) +
                       (std_b ** 2 / n_b) ** 2 / max(n_b - 1, 1))
        # Use 1e-300 floor (not 1e-10!) to avoid destroying the Welch df calculation
        df = float(numerator / max(denominator, 1e-300))
        # Cap at n_a+n_b-2 for numerical stability with large samples
        df = min(df, float(n_a + n_b - 2))

    observed_diff = mean_b - mean_a

    # TOST: two one-sided t-tests
    # Test 1 (lower): H0: diff <= -delta  →  reject if t1 > t_crit
    t1 = (observed_diff - (-delta)) / se
    p1 = float(1 - stats.t.cdf(t1, df=df))   # one-sided p-value (upper tail)

    # Test 2 (upper): H0: diff >= +delta  →  reject if t2 < -t_crit
    t2 = (observed_diff - delta) / se
    p2 = float(stats.t.cdf(t2, df=df))        # one-sided p-value (lower tail)

    t_crit = float(stats.t.ppf(1 - alpha, df=df))

    test_lower = TostTest(
        name="Lower bound test",
        hypothesis=f"H₀: {name_b} − {name_a} ≤ −δ (inferiority)",
        t_stat=round(t1, 4),
        df=round(df, 1),
        p_value=round(p1, 5),
        passed=p1 < alpha,
    )
    test_upper = TostTest(
        name="Upper bound test",
        hypothesis=f"H₀: {name_b} − {name_a} ≥ +δ (superiority/difference)",
        t_stat=round(t2, 4),
        df=round(df, 1),
        p_value=round(p2, 5),
        passed=p2 < alpha,
    )

    equivalent = test_lower.passed and test_upper.passed

    # (1−2α)×100% CI on the difference (= 90% CI when α=0.05)
    # This is the standard presentation for TOST
    t_ci = float(stats.t.ppf(1 - alpha, df=df))
    ci_lo = round(observed_diff - t_ci * se, 6)
    ci_hi = round(observed_diff + t_ci * se, 6)
    ci_level = f"{int((1 - 2*alpha)*100)}%"

    # 95% CIs on individual means
    t95 = float(stats.t.ppf(0.975, df=n_a - 1))
    sem_a = std_a / np.sqrt(n_a)
    group_a = TostGroupStats(
        name=name_a, n=n_a, mean=round(mean_a, 6), std=round(std_a, 6),
        sem=round(sem_a, 6),
        ci_lo=round(mean_a - t95 * sem_a, 6),
        ci_hi=round(mean_a + t95 * sem_a, 6),
    )
    t95b = float(stats.t.ppf(0.975, df=max(n_b - 1, 1)))
    sem_b = std_b / np.sqrt(n_b)
    group_b = TostGroupStats(
        name=name_b, n=n_b, mean=round(mean_b, 6), std=round(std_b, 6),
        sem=round(sem_b, 6),
        ci_lo=round(mean_b - t95b * sem_b, 6),
        ci_hi=round(mean_b + t95b * sem_b, 6),
    )

    # Conclusion text
    if equivalent:
        conclusion = (
            f"✅ EQUIVALENT — {name_b} is statistically equivalent to {name_a} "
            f"within ±{delta:.4f} (±{delta/abs(mean_a)*100:.1f}% of reference). "
            f"Both one-sided tests passed (p_lower={p1:.4f}, p_upper={p2:.4f}). "
            f"{ci_level} CI [{ci_lo:.4f}, {ci_hi:.4f}] ⊂ (−{delta:.4f}, +{delta:.4f})."
        )
        interpretation = (
            "The test process is statistically equivalent to the reference. "
            "Suitable for supplier qualification, process transfer, or method validation."
        )
    elif not test_lower.passed and not test_upper.passed:
        conclusion = (
            f"❌ NOT EQUIVALENT — Both tests failed. "
            f"The observed difference ({observed_diff:+.4f}) is outside the equivalence margin. "
            f"{ci_level} CI [{ci_lo:.4f}, {ci_hi:.4f}] extends beyond ±{delta:.4f}."
        )
        interpretation = (
            "The processes are not equivalent. "
            "Investigate the source of difference before qualification."
        )
    else:
        failing_test = "lower" if not test_lower.passed else "upper"
        conclusion = (
            f"❌ NOT EQUIVALENT — {failing_test} bound test failed. "
            f"p_lower={p1:.4f}, p_upper={p2:.4f}. "
            f"{ci_level} CI [{ci_lo:.4f}, {ci_hi:.4f}]."
        )
        interpretation = (
            "One directional equivalence test failed. "
            "The processes may be systematically shifted in one direction."
        )

    return EquivalenceResult(
        name_a=name_a,
        name_b=name_b,
        n_a=n_a,
        n_b=n_b,
        delta=round(delta, 6),
        delta_pct=round(delta / abs(mean_a) * 100, 2) if mean_a != 0 else 0.0,
        alpha=alpha,
        group_a=group_a,
        group_b=group_b,
        observed_difference=round(observed_diff, 6),
        tost_tests=[test_lower, test_upper],
        equivalent=equivalent,
        confidence_interval={
            "level": ci_level,
            "lower": ci_lo,
            "upper": ci_hi,
            "within_margin": ci_lo > -delta and ci_hi < delta,
        },
        conclusion=conclusion,
        interpretation=interpretation,
    )
