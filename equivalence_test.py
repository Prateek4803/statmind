"""
equivalence_test.py — StatMind TOST Equivalence Testing
=========================================================
Two One-Sided Tests (Schuirmann 1987) for equivalence.

Used for:
  - Supplier qualification (does new supplier match reference?)
  - Process transfer (does new chamber/line match baseline?)
  - Method comparison (does new measurement method agree?)

ALGORITHM
---------
H₀_lower:  μ_B − μ_A ≤ −δ   (test process is inferior)
H₀_upper:  μ_B − μ_A ≥ +δ   (test process is different/superior)

Equivalence is declared when BOTH one-sided t-tests reject their H₀
(both p-values < α).  This is algebraically equivalent to checking
that the (1−2α)×100% confidence interval on the difference lies
entirely within (−δ, +δ).

CRITICAL BUG FIXED IN THIS VERSION
------------------------------------
Previous implementation used  `max(denominator, 1e-10)`  as the
floor in the Welch df denominator.  For the MQE dataset
(std_a≈0.0078, std_b≈0.0146, n=100 each) the true denominator is
≈4.9e-14, so `max(4.9e-14, 1e-10)` = 1e-10 — off by ×2000.
This produced df ≈ 0.07 → t.ppf(0.95, 0.07) ≈ 3.5 trillion →
confidence interval of ±5.8 billion — physically meaningless.

FIX:  Use `max(denominator, 1e-300)` (machine-epsilon-safe floor)
      and cap df at n_a + n_b − 2 for additional numerical safety.

Verified: MQE Dataset 1 vs Dataset 2 (δ = 5% of reference mean)
  df_correct = 151.9, 90% CI = [0.0078, 0.0133] ⊂ (−0.074, +0.074)
  → EQUIVALENT ✅
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
from scipy import stats


# ── Dataclasses (JSON-serialisable via dataclasses.asdict) ───────────────────

@dataclass
class GroupStats:
    name:  str
    n:     int
    mean:  float
    std:   float
    sem:   float
    ci_lo: float   # 95 % CI on the group mean
    ci_hi: float


@dataclass
class TostTest:
    name:       str    # "Lower bound test" | "Upper bound test"
    hypothesis: str    # H₀ statement
    t_stat:     float
    df:         float
    p_value:    float
    passed:     bool   # True = H₀ rejected = this bound is supported


@dataclass
class EquivalenceResult:
    name_a:              str
    name_b:              str
    n_a:                 int
    n_b:                 int
    delta:               float          # equivalence margin (absolute)
    delta_pct:           float          # delta as % of reference mean
    alpha:               float
    group_a:             GroupStats
    group_b:             GroupStats
    observed_difference: float          # mean_b − mean_a
    tost_tests:          List[TostTest]
    equivalent:          bool
    confidence_interval: dict           # (1−2α)×100% CI on the difference
    conclusion:          str
    interpretation:      str
    welch_df:            float = 0.0    # exposed for diagnostics


# ── Welch df (with overflow-safe floor) ──────────────────────────────────────

def _welch_df(var_a: float, n_a: int, var_b: float, n_b: int) -> float:
    """
    Welch-Satterthwaite degrees of freedom.

    Uses 1e-300 floor (not 1e-10) so the true denominator is never
    swamped by the floor, and caps at n_a + n_b - 2 for safety.
    """
    if var_a == 0.0 and var_b == 0.0:
        return float(n_a + n_b - 2)

    s_a = var_a / n_a
    s_b = var_b / n_b
    numerator   = (s_a + s_b) ** 2
    denominator = (s_a ** 2 / max(n_a - 1, 1)) + (s_b ** 2 / max(n_b - 1, 1))

    # BUG FIX: floor must be 1e-300, not 1e-10
    df = numerator / max(denominator, 1e-300)

    # Cap for numerical stability with large balanced samples
    return min(df, float(n_a + n_b - 2))


# ── Public API ────────────────────────────────────────────────────────────────

def tost_equivalence(
    data_a: np.ndarray,
    data_b: np.ndarray,
    delta:  Optional[float] = None,
    alpha:  float = 0.05,
    name_a: str   = "Reference",
    name_b: str   = "Test",
) -> EquivalenceResult:
    """
    Run TOST equivalence test.

    Parameters
    ----------
    data_a : reference (baseline) measurements
    data_b : test (new process) measurements
    delta  : equivalence margin (absolute units).
             Defaults to 5% of |mean_a| if None.
    alpha  : significance level (default 0.05 → 90% CI for TOST)
    name_a : label for group A (reference)
    name_b : label for group B (test)
    """
    data_a = np.asarray(data_a, dtype=float)
    data_b = np.asarray(data_b, dtype=float)
    data_a = data_a[~np.isnan(data_a)]
    data_b = data_b[~np.isnan(data_b)]

    n_a, n_b = len(data_a), len(data_b)
    if n_a < 3:
        raise ValueError(f"Group A ('{name_a}') has only {n_a} values; need ≥ 3.")
    if n_b < 3:
        raise ValueError(f"Group B ('{name_b}') has only {n_b} values; need ≥ 3.")

    mean_a, mean_b = float(data_a.mean()), float(data_b.mean())
    var_a  = float(data_a.var(ddof=1))
    var_b  = float(data_b.var(ddof=1))
    std_a  = math.sqrt(var_a)
    std_b  = math.sqrt(var_b)

    # Default δ: 5 % of |reference mean|  (industry convention)
    if delta is None:
        delta = abs(mean_a) * 0.05
    delta = abs(float(delta))

    # Standard error of the difference
    se = math.sqrt(max(var_a / n_a + var_b / n_b, 1e-300))

    # Welch df (BUG FIX applied)
    df = _welch_df(var_a, n_a, var_b, n_b)

    diff = mean_b - mean_a

    # ── TOST: two one-sided t-tests ──────────────────────────────────────────
    # Lower bound test: H₀: diff ≤ −δ  (test process inferior)
    t1 = (diff - (-delta)) / se
    p1 = float(1.0 - stats.t.cdf(t1, df=df))    # one-sided upper tail

    # Upper bound test: H₀: diff ≥ +δ  (test process superior/different)
    t2 = (diff - delta) / se
    p2 = float(stats.t.cdf(t2, df=df))           # one-sided lower tail

    test_lower = TostTest(
        name       = "Lower bound test",
        hypothesis = f"H₀: {name_b} − {name_a} ≤ −δ (inferiority)",
        t_stat     = round(t1, 4),
        df         = round(df, 1),
        p_value    = round(p1, 5),
        passed     = p1 < alpha,
    )
    test_upper = TostTest(
        name       = "Upper bound test",
        hypothesis = f"H₀: {name_b} − {name_a} ≥ +δ (difference/superiority)",
        t_stat     = round(t2, 4),
        df         = round(df, 1),
        p_value    = round(p2, 5),
        passed     = p2 < alpha,
    )

    equivalent = test_lower.passed and test_upper.passed

    # ── (1−2α)×100% CI on the difference ─────────────────────────────────────
    t_ci   = float(stats.t.ppf(1.0 - alpha, df=df))   # e.g. 1.655 for α=0.05
    ci_lo  = round(diff - t_ci * se, 6)
    ci_hi  = round(diff + t_ci * se, 6)
    ci_lvl = f"{int((1 - 2 * alpha) * 100)}%"
    within = ci_lo > -delta and ci_hi < delta

    # ── Per-group statistics (95 % CI on mean) ────────────────────────────────
    def _group_stats(data: np.ndarray, name: str) -> GroupStats:
        n    = len(data)
        mean = float(data.mean())
        std  = float(data.std(ddof=1)) if n > 1 else 0.0
        sem  = std / math.sqrt(n)
        t95  = float(stats.t.ppf(0.975, df=max(n - 1, 1)))
        return GroupStats(
            name  = name,
            n     = n,
            mean  = round(mean, 6),
            std   = round(std, 6),
            sem   = round(sem, 6),
            ci_lo = round(mean - t95 * sem, 6),
            ci_hi = round(mean + t95 * sem, 6),
        )

    group_a = _group_stats(data_a, name_a)
    group_b = _group_stats(data_b, name_b)

    # ── Conclusion text ───────────────────────────────────────────────────────
    delta_pct = round(delta / abs(mean_a) * 100, 2) if mean_a != 0 else 0.0

    if equivalent:
        conclusion = (
            f"✅ EQUIVALENT — '{name_b}' is statistically equivalent to "
            f"'{name_a}' within ±{delta:.5g} (±{delta_pct:.1f}% of reference). "
            f"Both one-sided tests passed (p_lower={p1:.4f}, p_upper={p2:.4f}). "
            f"{ci_lvl} CI [{ci_lo:.5g}, {ci_hi:.5g}] ⊂ (−{delta:.4g}, +{delta:.4g})."
        )
        interpretation = (
            "The test process is statistically equivalent to the reference within the "
            "specified margin.  Suitable for supplier qualification, process transfer "
            "validation, or method equivalence reporting."
        )
    elif not test_lower.passed and not test_upper.passed:
        conclusion = (
            f"❌ NOT EQUIVALENT — Both bounds failed. "
            f"Observed difference ({diff:+.5g}) exceeds the equivalence margin. "
            f"{ci_lvl} CI [{ci_lo:.5g}, {ci_hi:.5g}] extends beyond ±{delta:.4g}."
        )
        interpretation = (
            "The processes are not statistically equivalent.  "
            "Investigate the source of the systematic difference before qualification."
        )
    else:
        failing = "lower" if not test_lower.passed else "upper"
        conclusion = (
            f"❌ NOT EQUIVALENT — {failing} bound test failed. "
            f"p_lower={p1:.4f}, p_upper={p2:.4f}. "
            f"{ci_lvl} CI [{ci_lo:.5g}, {ci_hi:.5g}]."
        )
        interpretation = (
            "One directional equivalence test failed — the processes may be "
            "systematically shifted in one direction.  Review the observed difference "
            f"({diff:+.5g}) relative to the equivalence margin (±{delta:.4g})."
        )

    return EquivalenceResult(
        name_a               = name_a,
        name_b               = name_b,
        n_a                  = n_a,
        n_b                  = n_b,
        delta                = round(delta, 6),
        delta_pct            = delta_pct,
        alpha                = alpha,
        group_a              = group_a,
        group_b              = group_b,
        observed_difference  = round(diff, 6),
        tost_tests           = [test_lower, test_upper],
        equivalent           = equivalent,
        confidence_interval  = {
            "level":         ci_lvl,
            "lower":         ci_lo,
            "upper":         ci_hi,
            "within_margin": within,
        },
        conclusion           = conclusion,
        interpretation       = interpretation,
        welch_df             = round(df, 2),
    )
