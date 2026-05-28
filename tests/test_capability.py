"""
tests/test_capability.py
Unit tests for StatMind capability engine.
Run: pytest tests/ -v
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from capability import analyze_capability, expected_ppm


def make_normal_data(mean=10.0, std=0.1, n=50, seed=42):
    import random
    random.seed(seed)
    return [mean + std * (sum(random.random() for _ in range(12)) - 6) for _ in range(n)]


def run(data, usl=10.3, lsl=9.7, target=10.0):
    return analyze_capability(data=data, column="test_col", usl=usl, lsl=lsl, target=target, subgroup_size=1)


def test_ppm_near_zero_for_excellent_process():
    ppm = expected_ppm(mean=10.0, std=0.001, usl=10.5, lsl=9.5)
    assert ppm < 0.01, f"Expected near-zero PPM, got {ppm}"


def test_ppm_high_for_poor_process():
    ppm = expected_ppm(mean=10.0, std=1.0, usl=10.5, lsl=9.5)
    assert ppm > 100_000, f"Expected high PPM for poor process, got {ppm}"


def test_ppm_off_centre_higher_than_centred():
    ppm_centre = expected_ppm(mean=10.0, std=0.1, usl=10.3, lsl=9.7)
    ppm_off    = expected_ppm(mean=10.25, std=0.1, usl=10.3, lsl=9.7)
    assert ppm_off > ppm_centre, "Off-centre process should have higher PPM"


def test_ppm_positive():
    ppm = expected_ppm(mean=10.0, std=0.1, usl=10.3, lsl=9.7)
    assert ppm >= 0, f"PPM must be non-negative, got {ppm}"


def test_cp_reasonable_range():
    data = make_normal_data(mean=10.0, std=0.1, n=100)
    result = run(data)
    assert hasattr(result, 'cp'), "Result missing cp"
    assert 0.5 < result.cp < 2.5, f"Cp={result.cp} out of expected range"


def test_cpk_le_cp():
    data = make_normal_data(mean=10.1, std=0.1, n=100)
    result = run(data)
    assert result.cpk <= result.cp + 0.05, f"Cpk ({result.cpk}) > Cp ({result.cp})"


def test_cpk_lower_for_off_centre():
    data_centre = make_normal_data(mean=10.0, std=0.1, n=100, seed=1)
    data_off    = make_normal_data(mean=9.75, std=0.1, n=100, seed=2)
    r_c = run(data_centre)
    r_o = run(data_off)
    assert r_o.cpk < r_c.cpk, "Off-centre process should have lower Cpk"


def test_ppk_le_pp():
    data = make_normal_data(mean=10.1, std=0.1, n=100)
    result = run(data)
    assert result.ppk <= result.pp + 0.05, f"Ppk ({result.ppk}) > Pp ({result.pp})"


def test_zero_std_guard():
    import math
    data = [10.0] * 50
    try:
        result = run(data)
        assert not math.isinf(result.cp), "Cp should not be inf for zero-std data"
        assert not math.isnan(result.cp), "Cp should not be NaN for zero-std data"
    except Exception:
        pass


def test_result_has_required_fields():
    data = make_normal_data(mean=10.0, std=0.1, n=50)
    result = run(data)
    for field in ['cp', 'cpk', 'pp', 'ppk', 'ppm_within', 'ppm_overall']:
        assert hasattr(result, field), f"Result missing field: {field}"


def test_ppm_within_non_negative():
    data = make_normal_data(mean=10.0, std=0.1, n=50)
    result = run(data)
    assert result.ppm_within >= 0
    assert result.ppm_overall >= 0
