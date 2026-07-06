"""
Regression tests for the 2026-07-06 full-feature campaign findings:
  P0-STAT-8  GR&R silently analyzed the Trial column of AIAG-format studies
             (verdict "Unacceptable 100%" on a good gauge).
  P1-VAL-2   Pareto rejected legitimate pre-aggregated category+count files.
  P1-VAL-3   DOE silently truncated mismatched response counts.
  P2-UX-1    Attribute charts leaked raw KeyErrors as error messages.
  P2-UX-2    Malformed JSON bodies -> unhandled 500.
"""
import io

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main
from gauge_rr import parse_grr_csv

client = TestClient(main.app)


# ── Data builders (campaign ground truths, generated inline) ─────────────────

def _aiag_grr_csv(extra_meas_col=False):
    """10 parts x 3 operators x 3 trials, AIAG format WITH a Trial column.
    Designed: part sd=5, repeatability sd=1, op bias sd~0.5 -> %GRR ~ 20%."""
    rng = np.random.default_rng(2026)
    parts_true = rng.normal(100, 5, 10)
    rows = []
    for p in range(10):
        for op, bias in {"Alice": -0.5, "Bob": 0.2, "Chen": 0.6}.items():
            for t in range(3):
                row = {"Part": f"P{p+1:02d}", "Operator": op, "Trial": t + 1,
                       "Thickness_nm": round(parts_true[p] + bias + rng.normal(0, 1.0), 3)}
                if extra_meas_col:
                    row["Width_um"] = round(row["Thickness_nm"] * 0.9, 3)
                rows.append(row)
    return pd.DataFrame(rows).to_csv(index=False).encode()


# ── P0-STAT-8: GR&R column detection ─────────────────────────────────────────

def test_grr_aiag_format_with_trial_column_analyzes_measurement():
    """THE bug: Trial must never be chosen as the measurement."""
    m, p, o, col = parse_grr_csv(_aiag_grr_csv(), "study.csv")
    assert col == "Thickness_nm"
    assert len(m) == 90


def test_grr_aiag_endpoint_verdict_is_correct():
    r = client.post("/api/v1/grr/analyze?method=ANOVA&tolerance=30",
                    files={"file": ("g.csv", io.BytesIO(_aiag_grr_csv()), "text/csv")})
    assert r.status_code == 200
    j = r.json()
    assert j["column"] == "Thickness_nm"
    # Designed %GRR ~ 19-22% => Marginal, NOT the old false "Unacceptable"
    assert j["verdict"] in ("Marginal", "Acceptable")
    assert 10 <= j["gauge_rr"]["pct_study_var"] <= 35


def test_grr_true_ambiguity_requires_explicit_column():
    csv = _aiag_grr_csv(extra_meas_col=True)  # Thickness_nm AND Width_um
    r = client.post("/api/v1/grr/analyze",
                    files={"file": ("g.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 400
    assert "Thickness_nm" in r.json()["detail"] and "Width_um" in r.json()["detail"]

    r2 = client.post("/api/v1/grr/analyze?column=Width_um",
                     files={"file": ("g.csv", io.BytesIO(csv), "text/csv")})
    assert r2.status_code == 200
    assert r2.json()["column"] == "Width_um"


def test_grr_explicit_column_is_case_insensitive():
    r = client.post("/api/v1/grr/analyze?column=thickness_NM",
                    files={"file": ("g.csv", io.BytesIO(_aiag_grr_csv()), "text/csv")})
    assert r.status_code == 200
    assert r.json()["column"] == "Thickness_nm"


def test_grr_index_only_numerics_refused_with_explanation():
    df = pd.DataFrame({"Part": ["P1", "P1", "P2", "P2"] * 3,
                       "Operator": ["A", "B"] * 6, "Trial": [1, 2, 3] * 4})
    r = client.post("/api/v1/grr/analyze",
                    files={"file": ("g.csv", io.BytesIO(df.to_csv(index=False).encode()), "text/csv")})
    assert r.status_code == 400
    assert "index-like" in r.json()["detail"] or "Trial" in r.json()["detail"]


def test_grr_unknown_explicit_column_clear_error():
    r = client.post("/api/v1/grr/analyze?column=Nope",
                    files={"file": ("g.csv", io.BytesIO(_aiag_grr_csv()), "text/csv")})
    assert r.status_code == 400 and "Nope" in r.json()["detail"]


# ── P1-VAL-2: Pareto accepts short categorical files ─────────────────────────

def test_pareto_accepts_preaggregated_seven_categories():
    csv = ("Defect_Type,Count\nParticle,182\nScratch,95\nCD_OOS,61\n"
           "Overlay,34\nCorrosion,18\nPeeling,9\nOther,6\n").encode()
    r = client.post("/api/v1/pareto/analyze?category_col=Defect_Type&count_col=Count",
                    files={"file": ("p.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert "Particle" in str(body)


def test_pareto_accepts_category_only_event_log():
    """Raw event log: category column only, zero numeric columns."""
    csv = ("Defect\n" + "\n".join(
        ["Particle"] * 9 + ["Scratch"] * 4 + ["Overlay"] * 2)).encode()
    r = client.post("/api/v1/pareto/analyze?category_col=Defect",
                    files={"file": ("p.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 200


def test_other_endpoints_keep_strict_numeric_gate():
    """The relaxation is Pareto-scoped: measurement analyses still require
    10+ numeric values."""
    csv = "X\n1\n2\n3\n".encode()
    r = client.post("/api/v1/normality/analyze?column=X",
                    files={"file": ("d.csv", io.BytesIO(csv), "text/csv")})
    assert r.status_code == 400


# ── P1-VAL-3: DOE response-count validation ──────────────────────────────────

def test_doe_rejects_mismatched_response_count():
    r = client.post("/api/v1/doe/analyze", json={
        "factor_names": ["A", "B", "C"],
        "factor_levels": {"A": [-1, 1], "B": [-1, 1], "C": [-1, 1]},
        "design_type": "full",
        "responses": list(range(16)),   # 16 responses on an 8-run design
    })
    assert r.status_code == 400
    assert "8" in r.json()["detail"] and "16" in r.json()["detail"]


def test_doe_correct_count_still_works():
    r = client.post("/api/v1/doe/analyze", json={
        "factor_names": ["A", "B", "C"],
        "factor_levels": {"A": [-1, 1], "B": [-1, 1], "C": [-1, 1]},
        "design_type": "full",
        "responses": [34.1, 34.0, 35.8, 34.3, 50.9, 50.1, 57.2, 56.4],
    })
    assert r.status_code == 200
    assert r.json()["main_effects"]


def test_doe_no_responses_generates_design_only():
    r = client.post("/api/v1/doe/analyze", json={
        "factor_names": ["A", "B"],
        "factor_levels": {"A": [-1, 1], "B": [-1, 1]},
        "design_type": "full",
    })
    assert r.status_code == 200


# ── P2-UX-1: attribute chart error messages ──────────────────────────────────

@pytest.mark.parametrize("chart,body,missing", [
    ("p",  {"defectives": [1, 2]}, "subgroup_sizes"),
    ("np", {"defectives": [1, 2]}, "subgroup_size"),
    ("u",  {"defects": [1, 2]},    "subgroup_sizes"),
    ("c",  {},                     "defects"),
])
def test_attribute_charts_name_missing_fields(chart, body, missing):
    r = client.post(f"/api/v1/attribute-charts/{chart}", json=body)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert missing in detail and "Missing required field" in detail
    assert detail != f"'{missing}'"   # the old raw KeyError leak


# ── P2-UX-2: malformed JSON body -> 400, not 500 ────────────────────────────

def test_malformed_json_body_returns_400():
    r = client.post("/api/v1/intelligence/analyse",
                    content=b"this is not json",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert "JSON" in r.json()["detail"]
