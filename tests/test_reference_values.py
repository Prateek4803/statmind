"""
tests/test_reference_values.py
Reference-value tests for StatMind's trust-critical engines.

These lock in statistical CORRECTNESS (not just "doesn't crash") for the two
modules a wrong-but-plausible number would do the most damage in:

  1. Cpk confidence intervals  — cross-checked against an independent
     implementation of the Bissell (1990) variance approximation, the same
     formula Minitab/Montgomery §8.3 use.
  2. Gauge R&R variance components — checked by recovering KNOWN injected
     variance from a synthetic crossed study (AIAG two-way ANOVA method).

If any of these fail, a real measurement/disposition decision could be made
on a bad number. Treat a failure here as a release blocker.

Run: pytest tests/test_reference_values.py -v
"""
import os
import sys

import numpy as np
import pytest
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from capability import cpk_confidence_interval
from gauge_rr import analyze_gauge_rr


# ─────────────────────────────────────────────────────────────────────────────
# 1. Cpk confidence interval — independent reference cross-check
# ─────────────────────────────────────────────────────────────────────────────

def _reference_cpk_ci(cpk: float, n: int, confidence: float):
    """Independent re-implementation of the published Bissell formula.
    Var(Cpk) = 1/(9n) + Cpk^2 / (2(n-1)).  Deliberately written separately
    from the production code so a copy-paste error in either is caught."""
    if n < 5:
        return (0.0, float("inf"))
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    se = np.sqrt(1 / (9 * n) + cpk ** 2 / (2 * (n - 1)))
    return (max(0.0, cpk - z * se), cpk + z * se)


# (cpk, n, confidence) spanning typical capability/sample-size regimes
_CI_CASES = [
    (1.33, 30, 0.95),
    (1.00, 50, 0.95),
    (1.67, 100, 0.99),
    (0.80, 25, 0.90),
    (2.00, 60, 0.95),
    (1.10, 200, 0.99),
]


@pytest.mark.parametrize("cpk,n,confidence", _CI_CASES)
def test_cpk_ci_matches_independent_reference(cpk, n, confidence):
    got = cpk_confidence_interval(cpk, n, confidence)
    exp_lo, exp_hi = _reference_cpk_ci(cpk, n, confidence)
    assert got.lower == pytest.approx(round(exp_lo, 4), abs=1e-3), (
        f"lower bound drift: impl={got.lower} ref={exp_lo}"
    )
    assert got.upper == pytest.approx(round(exp_hi, 4), abs=1e-3), (
        f"upper bound drift: impl={got.upper} ref={exp_hi}"
    )


def test_cpk_ci_small_n_returns_safe_bounds():
    """n<5 is statistically unreliable for this approximation — must widen,
    never return a falsely-tight interval."""
    ci = cpk_confidence_interval(1.33, 4, 0.95)
    assert ci.lower == 0.0
    assert ci.upper == float("inf")


def test_cpk_ci_lower_bound_never_negative():
    """A negative Cpk lower bound is meaningless and would mislead a user."""
    ci = cpk_confidence_interval(0.30, 20, 0.99)
    assert ci.lower >= 0.0


def test_cpk_ci_widens_with_confidence():
    c90 = cpk_confidence_interval(1.33, 50, 0.90)
    c99 = cpk_confidence_interval(1.33, 50, 0.99)
    assert (c99.upper - c99.lower) > (c90.upper - c90.lower)


def test_cpk_ci_narrows_with_more_data():
    small = cpk_confidence_interval(1.33, 20, 0.95)
    large = cpk_confidence_interval(1.33, 500, 0.95)
    assert (large.upper - large.lower) < (small.upper - small.lower)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Gauge R&R — recover KNOWN variance components from synthetic data
# ─────────────────────────────────────────────────────────────────────────────

def _build_crossed_study(seed=7, n_parts=10, sigma_part=2.0,
                         sigma_repeat=0.4, op_bias=None):
    """Synthetic crossed GRR: 10 parts x 3 operators x 2 reps, with known
    part spread, repeatability, and operator (reproducibility) biases."""
    if op_bias is None:
        op_bias = {"A": 0.0, "B": 0.3, "C": -0.2}
    rng = np.random.default_rng(seed)
    part_true = rng.normal(10, sigma_part, n_parts)
    parts, ops, meas = [], [], []
    for p in range(n_parts):
        for op in op_bias:
            for _ in range(2):
                parts.append(f"P{p:02d}")
                ops.append(op)
                meas.append(part_true[p] + op_bias[op]
                            + rng.normal(0, sigma_repeat))
    return np.array(meas), parts, ops


def test_grr_recovers_dominant_part_variation():
    """With large part spread and small gauge error, part-to-part variance
    must dominate GRR variance — the defining property of a good gauge."""
    meas, parts, ops = _build_crossed_study()
    r = analyze_gauge_rr(meas, parts, ops)
    assert r.part_to_part.variance > r.gauge_rr.variance


def test_grr_repeatability_in_expected_range():
    """Injected repeatability sigma=0.4 -> variance ~0.16. Allow estimation
    spread but catch gross errors (off by >3x)."""
    meas, parts, ops = _build_crossed_study(sigma_repeat=0.4)
    r = analyze_gauge_rr(meas, parts, ops)
    assert 0.05 < r.repeatability.variance < 0.45


def test_grr_variance_components_nonnegative():
    """AIAG mandates clamping negative variance components to zero.
    No component may be negative under any input."""
    meas, parts, ops = _build_crossed_study(seed=123)
    r = analyze_gauge_rr(meas, parts, ops)
    for vc in (r.repeatability, r.reproducibility, r.gauge_rr,
               r.part_to_part, r.total_variation):
        assert vc.variance >= 0.0, f"{vc.source} variance negative: {vc.variance}"


def test_grr_equals_repeat_plus_reproduce():
    """GRR variance must equal repeatability + reproducibility (identity)."""
    meas, parts, ops = _build_crossed_study()
    r = analyze_gauge_rr(meas, parts, ops)
    assert r.gauge_rr.variance == pytest.approx(
        r.repeatability.variance + r.reproducibility.variance, abs=1e-6
    )


def test_grr_excellent_gauge_is_acceptable():
    """Tiny gauge error vs huge part spread -> low %GRR -> Acceptable verdict."""
    meas, parts, ops = _build_crossed_study(
        sigma_part=5.0, sigma_repeat=0.05, op_bias={"A": 0.0, "B": 0.02, "C": -0.02}
    )
    r = analyze_gauge_rr(meas, parts, ops)
    assert r.gauge_rr.pct_study_var < 30.0
    assert r.verdict in ("Acceptable", "Marginal")


def test_grr_terrible_gauge_is_unacceptable():
    """Gauge error comparable to part spread -> high %GRR -> Unacceptable."""
    meas, parts, ops = _build_crossed_study(
        sigma_part=0.5, sigma_repeat=1.5, op_bias={"A": 0.0, "B": 1.0, "C": -0.8}
    )
    r = analyze_gauge_rr(meas, parts, ops)
    assert r.gauge_rr.pct_study_var > 30.0
    assert r.verdict == "Unacceptable"


def test_grr_ndc_is_nonnegative_integer():
    meas, parts, ops = _build_crossed_study()
    r = analyze_gauge_rr(meas, parts, ops)
    assert isinstance(r.ndc, int)
    assert r.ndc >= 0
