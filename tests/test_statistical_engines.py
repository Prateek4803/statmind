"""
StatMind — Test Suite v3
Covers all P0/P1 audit fixes:
  P0-STAT-1  c4 constant table (AIAG values)
  P0-STAT-2  Two-sided PPM formula
  P0-STAT-3  Cpk CI guard for n<5
  P0-STAT-4  CAPA notes negative-LSL false positive
  P0-STAT-5  Zero-variance guard
  P0-SEC-1   File size limit
  P0-SEC-2   Bounded report cache TTL eviction

Run:
    pip install pytest numpy scipy
    pytest tests/test_statistical_engines.py -v
"""

import time
import threading
import pytest
import numpy as np
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from capability import (
    analyze_capability, _c4, expected_ppm,
    cpk_confidence_interval, estimate_sigma_within,
    MAX_DATA_POINTS, CapabilityReport,
)


# ═══════════════════════════════════════════════════════════
# P0-STAT-1 — c4 constant table
# ═══════════════════════════════════════════════════════════

class TestC4Constant:
    """AIAG MSA 4th Ed. Table B-1 validation."""

    AIAG = {
        2: 0.7979, 3: 0.8862, 4: 0.9213, 5: 0.9400,
        6: 0.9515, 7: 0.9594, 8: 0.9650, 9: 0.9693, 10: 0.9727,
    }

    @pytest.mark.parametrize("n,expected", AIAG.items())
    def test_aiag_values(self, n, expected):
        assert abs(_c4(n) - expected) < 5e-4, f"c4({n})={_c4(n):.4f}, expected {expected}"

    def test_monotone_increasing(self):
        vals = [_c4(n) for n in range(2, 30)]
        for i in range(len(vals) - 1):
            assert vals[i] < vals[i+1], f"c4 not monotone at n={i+2}"

    def test_approaches_unity(self):
        assert _c4(100) > 0.995

    def test_no_nan(self):
        """Formula must not return NaN for any n in [2..100]."""
        for n in range(2, 101):
            v = _c4(n)
            assert not np.isnan(v), f"c4({n}) returned NaN"
            assert 0.7 < v < 1.0, f"c4({n}) = {v} out of range"

    def test_raises_for_n_lt_2(self):
        with pytest.raises(ValueError):
            _c4(1)


# ═══════════════════════════════════════════════════════════
# P0-STAT-2 — Two-sided PPM formula
# ═══════════════════════════════════════════════════════════

class TestPPM:
    def test_centred_process_both_tails(self):
        """For a perfectly centred 3σ process, PPM ≈ 2700 (both tails)."""
        ppm = expected_ppm(mean=0.0, std=1.0, usl=3.0, lsl=-3.0)
        assert 2500 < ppm < 2800, f"PPM={ppm}, expected ≈ 2700"

    def test_off_centre_higher_ppm(self):
        """Shifting mean toward USL increases PPM vs centred."""
        ppm_centred = expected_ppm(mean=0.0, std=1.0, usl=3.0, lsl=-3.0)
        ppm_shifted = expected_ppm(mean=1.5, std=1.0, usl=3.0, lsl=-3.0)
        assert ppm_shifted > ppm_centred

    def test_one_sided_shortcut_is_wrong(self):
        """
        Proves old formula 2*sf(3*Cpk) is wrong for off-centre process.
        Off-centre: mean=1, USL=3, LSL=-3, std=1
        Cpk = min((3-1)/3, (1+3)/3) = min(0.667, 1.333) = 0.667
        Old formula: 2 * sf(3*0.667) * 1e6 = 2 * sf(2.0) * 1e6 ≈ 45,500 PPM
        Correct:     sf((3-1)/1) + cdf((-3-1)/1) = sf(2) + cdf(-4)
                   ≈ 22,750 + 31.7 ≈ 22,782 PPM
        """
        correct_ppm = expected_ppm(mean=1.0, std=1.0, usl=3.0, lsl=-3.0)
        # The correct answer is dominated by the upper tail only ≈ 22,750
        assert 20_000 < correct_ppm < 25_000, f"PPM={correct_ppm}"

    def test_zero_std_returns_zero(self):
        assert expected_ppm(5.0, 0.0, 6.0, 4.0) == 0.0

    def test_negative_lsl(self):
        """Handles negative LSL correctly (no false overflow)."""
        ppm = expected_ppm(mean=0.0, std=1.0, usl=3.0, lsl=-3.0)
        assert ppm > 0

    def test_six_sigma_ppm(self):
        """6σ capable process: PPM should be < 0.01."""
        ppm = expected_ppm(mean=0.0, std=1.0, usl=6.0, lsl=-6.0)
        assert ppm < 0.01


# ═══════════════════════════════════════════════════════════
# P0-STAT-3 — Cpk CI guard for n<5
# ═══════════════════════════════════════════════════════════

class TestCpkCI:
    def test_n_lt_5_returns_safe_bounds(self):
        """Should not raise or return NaN for n<5."""
        ci = cpk_confidence_interval(1.33, n=3, confidence=0.95)
        assert ci.lower == 0.0
        assert ci.upper == float("inf")

    def test_n_eq_5_runs_without_error(self):
        ci = cpk_confidence_interval(1.33, n=5, confidence=0.95)
        assert ci.lower >= 0.0
        assert ci.upper > ci.lower

    def test_ci_narrows_with_more_data(self):
        ci_small = cpk_confidence_interval(1.33, n=30,   confidence=0.95)
        ci_large = cpk_confidence_interval(1.33, n=3000, confidence=0.95)
        assert (ci_large.upper - ci_large.lower) < (ci_small.upper - ci_small.lower)

    def test_lower_never_negative(self):
        ci = cpk_confidence_interval(0.2, n=10, confidence=0.95)
        assert ci.lower >= 0.0

    def test_wider_at_higher_confidence(self):
        ci_95 = cpk_confidence_interval(1.33, n=50, confidence=0.95)
        ci_99 = cpk_confidence_interval(1.33, n=50, confidence=0.99)
        assert (ci_99.upper - ci_99.lower) > (ci_95.upper - ci_95.lower)


# ═══════════════════════════════════════════════════════════
# P0-STAT-4 — CAPA notes negative-LSL false positive
# ═══════════════════════════════════════════════════════════

class TestCapaNotesFalsePositive:
    def test_negative_lsl_no_false_tail_alarm(self):
        """
        Process with LSL=-5, USL=5, mean=0, std=1.
        3σ lower tail = -3, which is well within spec.
        Old code: -3 < -5 * 1.02 = -5.1 → FALSE (no alarm). OK.
        But for LSL=-0.5: lower_tail = mean-3σ = -3. Old check: -3 < -0.5*1.02=-0.51 → TRUE (false alarm!)
        New code uses absolute distance, so no false alarm.
        """
        rng = np.random.default_rng(42)
        # Tight specs around zero with negative LSL
        data = rng.normal(loc=0.0, scale=0.1, size=100)
        report = analyze_capability(data, "test", usl=0.5, lsl=-0.5)
        # With std=0.1, 3σ tail at -0.3, LSL=-0.5 → margin = 0.2, not a problem
        # Should NOT have tail proximity alarm
        tail_notes = [n for n in report.capa_notes if "lower tail" in n.lower() and "units of LSL" in n]
        assert len(tail_notes) == 0, f"False positive tail alarm: {tail_notes}"

    def test_genuine_tail_proximity_fires(self):
        """Process genuinely close to limit SHOULD trigger the note."""
        rng = np.random.default_rng(99)
        # mean=0, std=1, LSL=-3.1 → lower tail at -3, margin = 0.1 (very close)
        data = rng.normal(loc=0.0, scale=1.0, size=200)
        report = analyze_capability(data, "test", usl=10.0, lsl=-3.1)
        tail_notes = [n for n in report.capa_notes if "lower tail" in n.lower()]
        assert len(tail_notes) >= 1, "Expected tail proximity note was not generated"


# ═══════════════════════════════════════════════════════════
# P0-STAT-5 — Zero variance guard
# ═══════════════════════════════════════════════════════════

class TestZeroVariance:
    def test_identical_values_raises(self):
        with pytest.raises(ValueError, match="standard deviation is zero|identical"):
            analyze_capability(np.full(20, 5.0), "x", usl=6.0, lsl=4.0)

    def test_near_zero_variance_works(self):
        """Tiny but non-zero variance should not crash."""
        rng = np.random.default_rng(0)
        data = np.full(20, 5.0) + rng.normal(0, 1e-6, 20)
        # Should run without error
        report = analyze_capability(data, "x", usl=6.0, lsl=4.0)
        assert report.cpk > 0


# ═══════════════════════════════════════════════════════════
# P0-SEC-1 — File size limit
# ═══════════════════════════════════════════════════════════

class TestFileSizeLimit:
    def test_oversized_array_raises(self):
        """Arrays over MAX_DATA_POINTS should raise ValueError."""
        huge = np.ones(MAX_DATA_POINTS + 1)
        with pytest.raises(ValueError, match="maximum allowed"):
            analyze_capability(huge, "x", usl=2.0, lsl=0.0)

    def test_exactly_at_limit_passes(self):
        """Exactly MAX_DATA_POINTS should be accepted."""
        rng  = np.random.default_rng(0)
        data = rng.normal(1.0, 0.1, MAX_DATA_POINTS)
        # Should not raise
        report = analyze_capability(data, "x", usl=1.5, lsl=0.5)
        assert report.n == MAX_DATA_POINTS


# ═══════════════════════════════════════════════════════════
# P0-SEC-2 — Bounded report cache
# ═══════════════════════════════════════════════════════════

class TestReportCache:
    def test_basic_set_get(self, tmp_path):
        from report_cache import ReportCache
        cache = ReportCache(ttl=60, maxsize=10)
        p = str(tmp_path / "test.pdf")
        open(p, "w").close()
        cache.set("abc123", p)
        assert cache.get("abc123") == p

    def test_ttl_expiry(self, tmp_path):
        from report_cache import ReportCache
        cache = ReportCache(ttl=1, maxsize=10)
        p = str(tmp_path / "test.pdf")
        open(p, "w").close()
        cache.set("abc123", p)
        time.sleep(1.1)
        assert cache.get("abc123") is None

    def test_maxsize_eviction(self, tmp_path):
        from report_cache import ReportCache
        cache = ReportCache(ttl=3600, maxsize=3)
        for i in range(5):
            p = str(tmp_path / f"r{i}.pdf")
            open(p, "w").close()
            cache.set(f"id{i}", p)
        assert cache.size() <= 3

    def test_missing_key_returns_none(self):
        from report_cache import ReportCache
        cache = ReportCache(ttl=60, maxsize=10)
        assert cache.get("nonexistent") is None

    def test_thread_safety(self, tmp_path):
        from report_cache import ReportCache
        cache  = ReportCache(ttl=3600, maxsize=1000)
        errors = []

        def writer(i):
            try:
                p = str(tmp_path / f"t{i}.pdf")
                open(p, "w").close()
                cache.set(f"id{i}", p)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == [], f"Thread-safety errors: {errors}"


# ═══════════════════════════════════════════════════════════
# Integration — full analyze_capability
# ═══════════════════════════════════════════════════════════

class TestAnalyzeCapabilityIntegration:
    def test_capable_process(self):
        rng  = np.random.default_rng(0)
        data = rng.normal(100.0, 0.5, 100)
        r    = analyze_capability(data, "thickness", usl=105.0, lsl=95.0)
        assert isinstance(r, CapabilityReport)
        assert r.cp > 2.0
        assert r.verdict == "Excellent"
        assert r.capa_required is False

    def test_not_capable_process(self):
        rng  = np.random.default_rng(1)
        data = rng.normal(5.0, 1.5, 200)
        r    = analyze_capability(data, "param", usl=7.5, lsl=2.5)
        assert r.capa_required is True

    def test_cp_gte_abs_cpk(self):
        """Cp ≥ |Cpk| is always true by definition."""
        rng  = np.random.default_rng(2)
        data = rng.normal(8.0, 0.5, 100)
        r    = analyze_capability(data, "x", usl=10.0, lsl=6.0)
        assert r.cp >= abs(r.cpk) - 1e-9

    def test_nan_values_dropped(self):
        data = np.array([100.0, np.nan, 101.0, np.nan, 99.0, 100.5, 100.2])
        r    = analyze_capability(data, "x", usl=105.0, lsl=95.0)
        assert r.n == 5

    def test_usl_le_lsl_raises(self):
        with pytest.raises(ValueError, match="USL"):
            analyze_capability(np.ones(20), "x", usl=5.0, lsl=10.0)

    def test_too_few_points_raises(self):
        with pytest.raises(ValueError, match="5 data points"):
            analyze_capability(np.array([1.0, 2.0, 3.0]), "x", usl=5.0, lsl=0.0)

    def test_all_outputs_native_python(self):
        """FastAPI JSON encoder must handle all outputs without custom encoder."""
        data = np.random.default_rng(6).normal(100, 1, 50)
        r    = analyze_capability(data, "x", usl=106.0, lsl=94.0)
        assert isinstance(r.cpk,        float)
        assert isinstance(r.n,          int)
        assert isinstance(r.ppm_within, float)
        assert isinstance(r.capa_notes, list)

    def test_capa_notes_always_has_ppm_entry(self):
        data = np.random.default_rng(7).normal(100, 2, 100)
        r    = analyze_capability(data, "x", usl=106.0, lsl=94.0)
        ppm_notes = [n for n in r.capa_notes if "PPM" in n or "conformance" in n.lower()]
        assert len(ppm_notes) >= 1

    def test_sigma_level_capped_at_6(self):
        rng  = np.random.default_rng(8)
        data = rng.normal(100.0, 0.01, 100)   # extremely capable
        r    = analyze_capability(data, "x", usl=106.0, lsl=94.0)
        assert r.sigma_level <= 6.0

    def test_negative_cpk_not_capable(self):
        """Mean outside spec range → negative Cpk."""
        data = np.full(20, 15.0) + np.random.default_rng(0).normal(0, 0.1, 20)
        r    = analyze_capability(data, "x", usl=12.0, lsl=8.0)
        assert r.cpk < 0
        assert r.verdict == "Not Capable"
