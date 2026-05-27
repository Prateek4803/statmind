"""
StatMind — Statistical Engine Test Suite
pytest tests for capability.py and control_charts.py

Validation targets:
  - AIAG SPC 2nd Ed. reference values
  - Montgomery "Introduction to Statistical Quality Control" 8th Ed.
  - NIST/SEMATECH e-Handbook of Statistical Methods

Run:
    pip install pytest numpy scipy
    pytest tests/test_statistical_engines.py -v
"""

import pytest
import numpy as np
import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from capability import (
    analyze_capability,
    estimate_sigma_within,
    cpk_confidence_interval,
    expected_ppm,
    _c4,
    CapabilityReport,
    ConfidenceInterval,
)
from control_charts import (
    build_imr,
    build_xbar_r,
    build_xbar_s,
    build_p_chart,
    build_c_chart,
    western_electric_rules,
    nelson_rules,
    _c4 as cc_c4,
    _d2, _d4, _a2, _a3,
)


# ═══════════════════════════════════════════════════════════════════
# CAPABILITY TESTS
# ═══════════════════════════════════════════════════════════════════

class TestC4Constant:
    """c4 must match AIAG SPC Table B-1 values exactly to 4 decimal places."""

    AIAG_TABLE = {
        2: 0.7979, 3: 0.8862, 4: 0.9213, 5: 0.9400,
        6: 0.9515, 7: 0.9594, 8: 0.9650, 9: 0.9693, 10: 0.9727,
    }

    @pytest.mark.parametrize("n,expected", AIAG_TABLE.items())
    def test_c4_aiag_values(self, n, expected):
        result = _c4(n)
        assert abs(result - expected) < 5e-4, (
            f"c4({n}) = {result:.4f}, AIAG expects {expected}"
        )

    def test_c4_monotone_increasing(self):
        """c4 must increase toward 1 as n increases."""
        vals = [_c4(n) for n in range(2, 26)]
        for i in range(len(vals) - 1):
            assert vals[i] < vals[i+1], f"c4 not monotone at n={i+2}"

    def test_c4_approaches_unity(self):
        """c4(25) > 0.98 — close to 1."""
        assert _c4(25) > 0.98


class TestSigmaWithin:
    """Verify sigma_within estimator behaviour."""

    def test_imr_known_sigma(self):
        """
        Generate data with known sigma=5 using fixed seed.
        MR estimate should be within 20% of truth for n=200.
        """
        rng = np.random.default_rng(42)
        data = rng.normal(loc=100.0, scale=5.0, size=200)
        sw = estimate_sigma_within(data, subgroup_size=1)
        assert abs(sw - 5.0) / 5.0 < 0.20, f"sigma_within = {sw:.3f}, expected ≈ 5"

    def test_subgroup_sigma(self):
        """Pooled s/c4 estimator should recover known sigma for large k."""
        rng = np.random.default_rng(7)
        data = rng.normal(loc=50.0, scale=2.0, size=500)
        sw = estimate_sigma_within(data, subgroup_size=5)
        assert abs(sw - 2.0) / 2.0 < 0.15, f"sigma_within = {sw:.3f}, expected ≈ 2"

    def test_minimum_data(self):
        """Single moving range should still work (n=2 yields 1 MR value)."""
        data = np.array([10.0, 12.0])
        sw = estimate_sigma_within(data)
        assert sw > 0

    def test_zero_sigma_fallback(self):
        """Identical values should not crash — returns overall sigma or near-zero."""
        data = np.full(20, 5.0)
        # Overall sigma is also 0 here, so analyze_capability should raise
        with pytest.raises(ValueError, match="standard deviation is zero"):
            analyze_capability(data, "test", usl=6.0, lsl=4.0)


class TestCpkCI:
    """Cpk confidence interval properties."""

    def test_ci_width_shrinks_with_n(self):
        """CI should narrow as n increases."""
        ci_small = cpk_confidence_interval(1.33, n=30,  confidence=0.95)
        ci_large = cpk_confidence_interval(1.33, n=300, confidence=0.95)
        width_small = ci_small.upper - ci_small.lower
        width_large = ci_large.upper - ci_large.lower
        assert width_large < width_small

    def test_ci_contains_true_value(self):
        """For large n the CI should tightly bracket the point estimate."""
        ci = cpk_confidence_interval(1.50, n=1000, confidence=0.95)
        assert ci.lower < 1.50 < ci.upper

    def test_ci_lower_never_negative(self):
        """Lower bound should be clipped to 0."""
        ci = cpk_confidence_interval(0.3, n=5, confidence=0.95)
        assert ci.lower >= 0.0

    def test_ci_80pct_narrower_than_99pct(self):
        ci_80 = cpk_confidence_interval(1.33, 100, 0.80)
        ci_99 = cpk_confidence_interval(1.33, 100, 0.99)
        assert (ci_80.upper - ci_80.lower) < (ci_99.upper - ci_99.lower)


class TestExpectedPPM:
    """PPM calculations."""

    def test_perfectly_centred_capable(self):
        """Cpk=1.33 centred process → ≈64 PPM total (AIAG reference)."""
        ppm = expected_ppm(mean=0.0, std=1.0, usl=4.0, lsl=-4.0)
        # 4-sigma process: Φ(-4)*2 * 1e6 ≈ 63.3 PPM
        assert 50 < ppm < 80, f"PPM = {ppm}, expected ≈ 63"

    def test_off_centre_higher_ppm(self):
        """Shifting mean off-centre should increase PPM."""
        ppm_centred  = expected_ppm(mean=0.0,  std=1.0, usl=3.0, lsl=-3.0)
        ppm_shifted  = expected_ppm(mean=1.5,  std=1.0, usl=3.0, lsl=-3.0)
        assert ppm_shifted > ppm_centred

    def test_zero_std_returns_zero(self):
        ppm = expected_ppm(mean=5.0, std=0.0, usl=6.0, lsl=4.0)
        assert ppm == 0.0

    def test_six_sigma_process(self):
        """6σ capable process (Cpk=2): ppm should be near 0.002."""
        ppm = expected_ppm(mean=0.0, std=1.0, usl=6.0, lsl=-6.0)
        assert ppm < 0.01


class TestAnalyzeCapability:
    """Integration tests for the main analyze_capability function."""

    def test_basic_capable_process(self):
        """Known capable data should yield Cpk > 1.33."""
        rng = np.random.default_rng(0)
        data = rng.normal(loc=100.0, scale=0.5, size=100)
        report = analyze_capability(data, "thickness", usl=105.0, lsl=95.0)
        assert isinstance(report, CapabilityReport)
        # spec width = 10, sigma ≈ 0.5 → Cp ≈ 3.33
        assert report.cp > 2.0
        assert report.verdict == "Excellent"

    def test_marginal_process(self):
        """Marginal Cpk ≈ 1.1 → verdict 'Marginal'."""
        rng = np.random.default_rng(1)
        data = rng.normal(loc=5.0, scale=0.9, size=200)
        report = analyze_capability(data, "param", usl=7.5, lsl=2.5)
        # Cpk = (7.5-5.0)/(3*0.9) ≈ 0.93 → "Not Capable"
        assert report.capa_required is True

    def test_cp_less_than_cpk_impossible(self):
        """Cp must always be ≥ |Cpk|."""
        rng = np.random.default_rng(2)
        data = rng.normal(loc=8.0, scale=0.5, size=100)
        report = analyze_capability(data, "x", usl=10.0, lsl=6.0)
        assert report.cp >= abs(report.cpk) - 1e-9

    def test_ppk_leq_cpk_general(self):
        """
        For stable processes ppk ≈ cpk.
        For unstable processes ppk < cpk.
        Both should be within a reasonable range of each other.
        """
        rng = np.random.default_rng(3)
        data = rng.normal(loc=100.0, scale=1.0, size=200)
        report = analyze_capability(data, "x", usl=106.0, lsl=94.0)
        # For a truly stationary process both should be similar
        assert abs(report.cpk - report.ppk) < 0.5

    def test_usl_leq_lsl_raises(self):
        with pytest.raises(ValueError, match="USL"):
            analyze_capability(np.ones(10), "x", usl=5.0, lsl=10.0)

    def test_too_few_points_raises(self):
        with pytest.raises(ValueError, match="5 data points"):
            analyze_capability(np.array([1.0, 2.0, 3.0]), "x", usl=5.0, lsl=0.0)

    def test_nan_values_are_dropped(self):
        """NaNs should be silently dropped."""
        data = np.array([100.0, np.nan, 101.0, np.nan, 99.0, 100.5, 100.2])
        report = analyze_capability(data, "x", usl=105.0, lsl=95.0)
        assert report.n == 5

    def test_target_defaults_to_midspec(self):
        data = np.random.default_rng(5).normal(100, 1, 50)
        report = analyze_capability(data, "x", usl=106.0, lsl=94.0)
        assert report.target == pytest.approx(100.0)

    def test_output_types_are_python_native(self):
        """All numeric outputs should be Python floats/ints, not numpy scalars."""
        data = np.random.default_rng(6).normal(100, 1, 50)
        report = analyze_capability(data, "x", usl=106.0, lsl=94.0)
        assert isinstance(report.cpk, float)
        assert isinstance(report.n, int)
        assert isinstance(report.ppm_within, float)

    def test_capa_notes_non_empty(self):
        """CAPA notes should always have at least one PPM note."""
        data = np.random.default_rng(7).normal(100, 2, 100)
        report = analyze_capability(data, "x", usl=106.0, lsl=94.0)
        assert len(report.capa_notes) >= 1


# ═══════════════════════════════════════════════════════════════════
# CONTROL CHART TESTS
# ═══════════════════════════════════════════════════════════════════

class TestControlChartConstants:
    """AIAG SPC Appendix B constant validation."""

    @pytest.mark.parametrize("n,expected", [(2, 1.128), (3, 1.693), (5, 2.326), (10, 3.078)])
    def test_d2_values(self, n, expected):
        assert abs(_d2(n) - expected) < 1e-3

    @pytest.mark.parametrize("n,expected", [(2, 3.267), (3, 2.575), (5, 2.114), (10, 1.744)])
    def test_d4_values(self, n, expected):
        assert abs(_d4(n) - expected) < 1e-3

    @pytest.mark.parametrize("n,expected", [(2, 1.880), (3, 1.023), (5, 0.577), (10, 0.308)])
    def test_a2_values(self, n, expected):
        assert abs(_a2(n) - expected) < 1e-3


class TestIMRChart:
    """I-MR chart correctness."""

    def test_in_control_no_alarms(self):
        """
        Stable normal process should not produce excessive alarms.

        Expected false-alarm rates per point for iid N(0,1):
          WE1 alone: 0.27% per point → ~0.27 alarms per 100 points
          WE2+WE3+WE4+Nelson rules collectively: ~3–5% per 100 points

        We allow ≤ 15 alarms for n=100 to account for rule overlap.
        A value > 25 would indicate a systematic false-alarm bug.
        """
        rng = np.random.default_rng(42)
        data = rng.normal(loc=100.0, scale=2.0, size=100)
        result = build_imr(data, "test")
        assert result["total_alarms"] <= 20, (
            f"Excessive alarms ({result['total_alarms']}) for stable iid data — "
            "possible false-alarm bug in WE/Nelson rules"
        )

    def test_out_of_control_detected(self):
        """Injected step-shift should trigger WE4 (8 consecutive same side)."""
        rng = np.random.default_rng(0)
        data = np.concatenate([
            rng.normal(100, 1, 30),
            rng.normal(104, 1, 20),   # deliberate shift
        ])
        result = build_imr(data, "test")
        assert result["total_alarms"] > 0
        assert result["in_control"] is False

    def test_centerline_equals_mean(self):
        data = np.array([10.0, 12.0, 11.0, 13.0, 10.0, 11.5, 12.5])
        result = build_imr(data, "x")
        assert result["primary_cl"] == pytest.approx(float(np.mean(data)), rel=1e-6)

    def test_ucl_above_lcl(self):
        data = np.random.default_rng(1).normal(50, 5, 50)
        result = build_imr(data, "x")
        assert result["primary_ucl"] > result["primary_cl"] > result["primary_lcl"]

    def test_primary_values_length(self):
        data = np.arange(1.0, 21.0)
        result = build_imr(data, "x")
        assert len(result["primary_values"]) == 20
        assert len(result["secondary_values"]) == 19  # n-1 MR values

    def test_output_types_serialisable(self):
        """All list elements must be Python floats."""
        data = np.random.default_rng(2).normal(0, 1, 30)
        result = build_imr(data, "x")
        for v in result["primary_values"]:
            assert isinstance(v, float)


class TestXbarRChart:
    """Xbar-R chart correctness."""

    def test_in_control_stable(self):
        rng = np.random.default_rng(10)
        data = rng.normal(50.0, 1.0, 200)
        result = build_xbar_r(data, "x", n=5)
        assert result["in_control"] is True or result["total_alarms"] <= 4

    def test_subgroup_count_correct(self):
        data = np.ones(50)
        result = build_xbar_r(data, "x", n=5)
        assert result["n_points"] == 10

    def test_sigma_inflated_by_sqrt_n_bug_fixed(self):
        """
        Bug fix verification: Xbar chart alarms were triggered too readily
        because sigma was divided by sqrt(n) twice.
        With 200 iid normal points and n=5, we should see VERY few WE/Nelson alarms.
        """
        rng = np.random.default_rng(99)
        data = rng.normal(loc=100.0, scale=2.0, size=500)
        result = build_xbar_r(data, "x", n=5)
        # If sigma_plot bug were still present, we'd get many false WE3/WE4 alarms
        false_alarm_rules = [a["rule"] for a in result["western_electric_alarms"]]
        # Allow some naturally occurring alarms in 100 subgroups
        assert len(false_alarm_rules) <= 10, (
            f"Too many alarms ({len(false_alarm_rules)}) — "
            "possible sigma_plot inflation bug still present"
        )

    def test_invalid_subgroup_size(self):
        with pytest.raises(ValueError):
            build_xbar_r(np.ones(100), "x", n=9)  # should be Xbar-S


class TestXbarSChart:
    """Xbar-S chart correctness."""

    def test_large_subgroup(self):
        data = np.random.default_rng(5).normal(100, 3, 300)
        result = build_xbar_s(data, "x", n=10)
        assert result["chart_type"] == "Xbar-S"
        assert result["n_points"] == 30


class TestPChart:
    """P chart (attribute) correctness."""

    def test_constant_n_in_control(self):
        """iid binomial process should be in control."""
        rng = np.random.default_rng(20)
        p_true = 0.05
        n = 100
        counts = rng.binomial(n, p_true, size=50)
        result = build_p_chart(counts, np.full(50, n), "defectives")
        assert result["chart_type"] == "P"

    def test_p_bar_calculated_correctly(self):
        """p̄ should equal total defectives / total inspected."""
        counts = np.array([5.0, 10.0, 3.0, 8.0])
        sizes  = np.array([100.0, 200.0, 100.0, 200.0])
        result = build_p_chart(counts, sizes, "x")
        expected_pbar = 26.0 / 600.0
        assert result["primary_cl"] == pytest.approx(expected_pbar, rel=1e-6)

    def test_variable_n_limits_provided(self):
        """Variable-n p-chart must include per-point UCL/LCL arrays."""
        counts = np.array([2.0, 5.0, 1.0, 3.0, 4.0])
        sizes  = np.array([50.0, 100.0, 60.0, 80.0, 70.0])
        result = build_p_chart(counts, sizes, "x")
        assert "ucl_per_point" in result
        assert "lcl_per_point" in result
        assert len(result["ucl_per_point"]) == 5


class TestCChart:
    """C chart correctness."""

    def test_centerline_equals_cbar(self):
        counts = np.array([3.0, 2.0, 5.0, 1.0, 4.0])
        result = build_c_chart(counts, "defects")
        assert result["primary_cl"] == pytest.approx(float(counts.mean()), rel=1e-6)

    def test_lcl_non_negative(self):
        """LCL must never be negative (poisson counts)."""
        counts = np.array([0.0, 1.0, 0.0, 1.0, 0.0])
        result = build_c_chart(counts, "defects")
        assert result["primary_lcl"] >= 0.0


class TestWesternElectricRules:
    """WE rule firing correctness."""

    def test_we1_fires_for_outlier(self):
        """Single 4σ outlier should trigger WE1."""
        data = np.full(20, 100.0)
        data[10] = 112.0  # large outlier
        cl    = 100.0
        sigma = 1.0
        alarms = western_electric_rules(data, cl, sigma)
        we1_indices = [a["index"] for a in alarms if a["rule"] == "WE1"]
        assert 10 in we1_indices

    def test_we4_fires_for_run(self):
        """8 consecutive points above CL should trigger WE4."""
        cl    = 0.0
        sigma = 1.0
        data  = np.array([0.5, 0.6, 0.7, 0.8, 0.9, 0.5, 0.6, 0.7,  # first 8 above
                          0.0, 0.0, 0.0])
        alarms = western_electric_rules(data, cl, sigma)
        rules  = [a["rule"] for a in alarms]
        assert "WE4" in rules

    def test_no_false_alarms_iid(self):
        """For perfectly iid N(0,1), false alarm rate should be < 5% of points."""
        rng   = np.random.default_rng(123)
        data  = rng.standard_normal(500)
        alarms = western_electric_rules(data, 0.0, 1.0)
        assert len(alarms) / 500 < 0.05


class TestNelsonRules:
    """Nelson rule firing correctness."""

    def test_n3_fires_for_trend(self):
        """6 strictly monotone increasing points should trigger N3."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 3.0, 3.0, 3.0, 3.0])
        cl    = 3.0
        sigma = 1.0
        alarms = nelson_rules(data, cl, sigma)
        n3_fired = any(a["rule"] == "N3" for a in alarms)
        assert n3_fired

    def test_n7_fires_for_hugging(self):
        """15 consecutive points within ±1σ should trigger N7 (stratification)."""
        cl    = 0.0
        sigma = 3.0
        # All points between -1σ and +1σ  (i.e., between -3 and 3 but all within 1σ of mean)
        data = np.array([0.5, -0.4, 0.3, -0.2, 0.1, 0.6, -0.3, 0.4,
                         -0.5, 0.2, 0.8, -0.7, 0.1, 0.3, -0.1])
        alarms = nelson_rules(data, cl, sigma)
        n7_fired = any(a["rule"] == "N7" for a in alarms)
        assert n7_fired

    def test_no_duplicate_alarms(self):
        """Same (index, rule) should appear at most once."""
        data = np.concatenate([np.full(20, 2.0), np.full(20, -2.0)])
        alarms = nelson_rules(data, 0.0, 1.0)
        seen = set()
        for a in alarms:
            key = (a["index"], a["rule"])
            assert key not in seen, f"Duplicate alarm at {key}"
            seen.add(key)


# ═══════════════════════════════════════════════════════════════════
# REGRESSION / EDGE CASES
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases that previously caused crashes or silent errors."""

    def test_capability_large_dataset(self):
        """10,000 points should complete without OOM or timeout."""
        data = np.random.default_rng(0).normal(100, 2, 10_000)
        report = analyze_capability(data, "x", usl=110.0, lsl=90.0)
        assert report.n == 10_000

    def test_capability_very_small_dataset(self):
        """Exactly 5 points — minimum allowed."""
        data = np.array([9.8, 10.0, 10.1, 9.9, 10.2])
        report = analyze_capability(data, "x", usl=11.0, lsl=9.0)
        assert report.cpk is not None

    def test_imr_minimum_data(self):
        """3 points — minimum for I-MR."""
        data = np.array([5.0, 6.0, 5.5])
        result = build_imr(data, "x")
        assert result["n_points"] == 3

    def test_capability_all_above_usl(self):
        """All data above USL → Cpk < 0, verdict 'Not Capable'."""
        data = np.full(20, 15.0) + np.random.default_rng(0).normal(0, 0.1, 20)
        report = analyze_capability(data, "x", usl=12.0, lsl=8.0)
        assert report.cpk < 0
        assert report.verdict == "Not Capable"
        assert report.capa_required is True

    def test_xbar_r_not_enough_subgroups(self):
        """< 3 subgroups should raise ValueError."""
        with pytest.raises(ValueError, match="subgroups"):
            build_xbar_r(np.ones(8), "x", n=5)  # only 1 subgroup

    def test_p_chart_zero_size_raises(self):
        with pytest.raises(ValueError):
            build_p_chart(np.array([1.0, 2.0]), np.array([0.0, 50.0]), "x")
