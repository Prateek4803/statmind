"""
Smoke tests for the analysis endpoints that were failing.
Run from the repo root:  pytest tests/test_endpoints_smoke.py -q

Each test asserts HTTP 200 and the presence of the key fields the frontend reads,
which is what catches the contract-drift bugs that produced the original errors.
"""
import io
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def _csv():
    np.random.seed(42)
    n = 80
    df = pd.DataFrame({
        "Etch_Rate_nm_min": np.random.normal(449, 30, n),
        "CD_nm_DS2_shift":  np.random.normal(121, 8, n),
        "Thickness_A":      np.random.normal(2205, 40, n),
        "Uniformity_pct":   np.abs(np.random.normal(2.0, 0.6, n)),
    })
    return df.to_csv(index=False).encode()


def _twa_csv():
    np.random.seed(1)
    n = 90
    df = pd.DataFrame({
        "Yield":   np.random.normal(100, 5, n) + np.tile([0, 3, 6], n // 3),
        "Machine": np.tile(["M1", "M2", "M3"], n // 3),
        "Shift":   np.repeat(["Day", "Night"], n // 2)[:n],
    })
    return df.to_csv(index=False).encode()


def _aaa_csv():
    np.random.seed(7)
    rows = []
    for s in range(1, 16):
        truth = "Pass" if s % 3 else "Fail"
        for app in ["Alice", "Bob", "Carol"]:
            for rep in (1, 2):
                d = truth if np.random.rand() > 0.12 else ("Fail" if truth == "Pass" else "Pass")
                rows.append({"Sample": s, "Appraiser": app, "Replicate": rep,
                             "Decision": d, "Reference": truth})
    return pd.DataFrame(rows).to_csv(index=False).encode()


def _post(url, data):
    return client.post(url, files={"file": ("f.csv", data, "text/csv")})


def test_spc():
    r = _post("/api/v1/spc/analyze?column=Etch_Rate_nm_min&subgroup_size=1", _csv())
    assert r.status_code == 200
    assert "primary_values" in r.json()


def test_runchart_has_nested_tests():
    r = _post("/api/v1/runchart/analyze?column=CD_nm_DS2_shift", _csv())
    assert r.status_code == 200
    j = r.json()
    assert "p" in j["runs_test"] and "p" in j["trend_test"]
    assert "overall_verdict" in j and "data" in j


def test_cusum_ewma_nested():
    r = _post("/api/v1/cusum/analyze?column=CD_nm_DS2_shift&k=0.5&h=5&lam=0.2&L=3", _csv())
    assert r.status_code == 200
    j = r.json()
    assert "cusum" in j and "ewma" in j
    assert "ewma_values" in j["ewma"] and "cusum_pos" in j["cusum"]


def test_correlation_optional_columns():
    r = _post("/api/v1/correlation/matrix?method=pearson", _csv())
    assert r.status_code == 200
    j = r.json()
    assert "correlation_matrix" in j and "p_values" in j


def test_equivalence_multipart():
    r = _post("/api/v1/equivalence/analyze?col_a=Etch_Rate_nm_min&col_b=CD_nm_DS2_shift&delta=0.05", _csv())
    assert r.status_code == 200
    assert "equivalent" in r.json()


def test_transformation():
    r = _post("/api/v1/transformation/analyze?column=Uniformity_pct&usl=1.53&lsl=1.47", _csv())
    assert r.status_code == 200


def test_sixpack():
    r = _post("/api/v1/sixpack/analyze?column=Etch_Rate_nm_min&usl=550&lsl=350", _csv())
    assert r.status_code == 200
    assert "cp" in r.json()


def test_tolerance():
    r = _post("/api/v1/tolerance/analyze?column=Etch_Rate_nm_min&coverage=0.99&confidence=0.95&interval_type=two_sided", _csv())
    assert r.status_code == 200


@pytest.mark.parametrize("test", ["two_t", "paired_t", "mann_whitney", "anova", "kruskal", "variance"])
def test_hypothesis_from_file(test):
    cols = "Etch_Rate_nm_min,CD_nm_DS2_shift,Thickness_A" if test in ("anova", "kruskal") \
        else "Etch_Rate_nm_min,CD_nm_DS2_shift"
    r = _post(f"/api/v1/hypothesis/from-file?test={test}&columns={cols}&alpha=0.05", _csv())
    assert r.status_code == 200
    assert "p_value" in r.json()


def test_two_way_anova():
    r = _post("/api/v1/hypothesis/two-way-anova?response=Yield&factor_a=Machine&factor_b=Shift", _twa_csv())
    assert r.status_code == 200
    labels = [row["source"] for row in r.json()["anova_table"]]
    assert "Machine × Shift" in labels


def test_aaa():
    r = _post("/api/v1/aaa/analyze?decision_col=Decision&sample_col=Sample&appraiser_col=Appraiser&replicate_col=Replicate&reference_col=Reference", _aaa_csv())
    assert r.status_code == 200
    assert "fleiss_kappa" in r.json()


# ── Regression guard: endpoints that were dead-on-arrival (NameError on
#    _parse_upload + missing pandas import) and the sklearn duplicates.
#    These tests fail loudly if those defects ever return. ────────────────────

def _post_form(url, data, form):
    """Post a file plus multipart form fields (for Form(...)-based endpoints)."""
    return client.post(
        url,
        files={"file": ("f.csv", data, "text/csv")},
        data=form,
    )


def _weibull_csv():
    """Positive failure-time data for Weibull MLE."""
    np.random.seed(11)
    # Weibull-distributed positive lifetimes
    data = np.random.weibull(1.8, 60) * 1000 + 50
    return pd.DataFrame({"FailureTime_hrs": data}).to_csv(index=False).encode()


def _logistic_csv():
    """Binary response + numeric predictors for logistic regression."""
    np.random.seed(5)
    n = 120
    x1 = np.random.normal(0, 1, n)
    x2 = np.random.normal(0, 1, n)
    logit = 0.8 * x1 - 0.5 * x2
    y = (1 / (1 + np.exp(-logit)) > np.random.rand(n)).astype(int)
    return pd.DataFrame({"Pass": y, "Temp": x1, "Pressure": x2}).to_csv(index=False).encode()


def test_weibull_analyze_not_dead():
    """Was NameError: _parse_upload undefined. Must return real Weibull output."""
    r = _post_form(
        "/api/v1/weibull/analyze",
        _weibull_csv(),
        {"column": "FailureTime_hrs", "confidence": "0.95"},
    )
    assert r.status_code == 200, r.text
    j = r.json()
    # beta (shape) / eta (scale) are the core Weibull MLE outputs
    assert any(k in j for k in ("beta", "shape", "eta", "scale"))


def test_pca_analyze_not_dead():
    """Duplicate sklearn route removed; pure analyze_pca engine must serve this URL."""
    r = client.post(
        "/api/v1/pca/analyze?columns=Etch_Rate_nm_min,CD_nm_DS2_shift,Thickness_A",
        files={"file": ("f.csv", _csv(), "text/csv")},
    )
    assert r.status_code == 200, r.text


def test_boxplot_analyze_not_dead():
    """Was NameError: _parse_upload undefined."""
    r = _post_form(
        "/api/v1/boxplot/analyze",
        _csv(),
        {"columns": "Etch_Rate_nm_min,CD_nm_DS2_shift"},
    )
    assert r.status_code == 200, r.text


def test_msa_linearity_not_dead():
    """Was NameError: _parse_upload undefined."""
    np.random.seed(3)
    ref = np.repeat([2.0, 4.0, 6.0, 8.0, 10.0], 12)
    meas = ref + np.random.normal(0, 0.15, len(ref))
    csv = pd.DataFrame({"Reference": ref, "Measured": meas}).to_csv(index=False).encode()
    r = _post_form(
        "/api/v1/msa/linearity",
        csv,
        {"reference_col": "Reference", "measurement_col": "Measured"},
    )
    assert r.status_code == 200, r.text


def test_logistic_via_regression_route():
    """Frontend uses /regression/logistic (pure engine); the sklearn
    /logistic/analyze duplicate was removed. This route must keep working."""
    r = client.post(
        "/api/v1/regression/logistic?response=Pass&predictors=Temp,Pressure",
        files={"file": ("f.csv", _logistic_csv(), "text/csv")},
    )
    assert r.status_code == 200, r.text


def test_rate_limiting_is_enforced_globally():
    """SlowAPIMiddleware must throttle even upload endpoints that don't declare
    a Request param. Without the middleware these escaped all limits (DoS surface).
    Health is exempt-ish but heavy endpoints must 429 once the budget is spent.

    conftest.py disables the per-IP limiter for the rest of the suite (all test
    requests share one pseudo-IP); this test re-enables it locally because the
    limiter itself is the behavior under test."""
    from rate_limit import limiter as _limiter
    _limiter.enabled = True
    try:
        # Hammer a heavy upload endpoint past the per-minute default (60/min).
        got_429 = False
        for _ in range(75):
            r = client.post(
                "/api/v1/spc/analyze?column=Etch_Rate_nm_min&subgroup_size=1",
                files={"file": ("f.csv", _csv(), "text/csv")},
            )
            if r.status_code == 429:
                got_429 = True
                break
        assert got_429, "Expected a 429 after exceeding the rate limit; endpoint appears unthrottled."
    finally:
        _limiter.enabled = False
