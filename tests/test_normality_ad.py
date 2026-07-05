"""
Tests for the self-contained Anderson-Darling implementation (P0-STAT-6).

scipy.stats.anderson deprecated its default calling convention in SciPy 1.17
and removes `critical_values` from the result in 1.19. StatMind now computes
A² and the Stephens small-sample critical values internally; these tests pin
that implementation against the SciPy reference while it is still available,
and against hand-checked properties so they keep passing after SciPy 1.19.
"""
import warnings

import numpy as np
import pytest

from normality import _anderson_darling_norm, run_anderson_darling


def _scipy_reference(data):
    """SciPy reference, tolerant of the 1.17 FutureWarning."""
    from scipy.stats import anderson
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return anderson(data, dist="norm")


@pytest.mark.parametrize("n", [8, 20, 80, 500, 5000])
@pytest.mark.parametrize("dist", ["normal", "exponential", "uniform"])
def test_matches_scipy_reference(n, dist):
    """A² and critical values must match scipy.stats.anderson exactly."""
    rng = np.random.default_rng(1234 + n)
    data = {
        "normal": rng.normal(10, 2, n),
        "exponential": rng.exponential(3, n),
        "uniform": rng.uniform(0, 1, n),
    }[dist]

    ref = _scipy_reference(data)
    a2, cv = _anderson_darling_norm(data)

    assert abs(a2 - ref.statistic) < 1e-8
    # scipy rounds its critical values to 3 decimals
    assert np.allclose(cv, ref.critical_values, atol=5e-4)


def test_decision_normal_not_rejected():
    rng = np.random.default_rng(7)
    res = run_anderson_darling(rng.normal(0, 1, 300))
    assert res.test_name == "Anderson-Darling"
    assert res.reject_null is False
    assert res.p_value > 0.05


def test_decision_skewed_rejected():
    rng = np.random.default_rng(7)
    res = run_anderson_darling(rng.exponential(1, 300))
    assert res.reject_null is True
    assert res.p_value < 0.05


def test_alpha_levels_map_to_correct_critical_values():
    rng = np.random.default_rng(3)
    data = rng.normal(50, 5, 100)
    cvs = [run_anderson_darling(data, alpha=a).critical_value
           for a in (0.15, 0.10, 0.05, 0.025, 0.01)]
    # Critical values must be strictly increasing as alpha decreases
    assert all(cvs[i] < cvs[i + 1] for i in range(len(cvs) - 1))


def test_rejects_tiny_and_degenerate_samples():
    with pytest.raises(ValueError):
        _anderson_darling_norm(np.array([1.0, 2.0, 3.0]))  # n < 8
    with pytest.raises(ValueError):
        _anderson_darling_norm(np.full(20, 5.0))  # zero variance


def test_no_future_warning_emitted():
    """The engine must not touch the deprecated scipy API path."""
    rng = np.random.default_rng(11)
    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        run_anderson_darling(rng.normal(0, 1, 100))
