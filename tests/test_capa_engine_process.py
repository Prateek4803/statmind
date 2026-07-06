"""
Tests for feat/capa-process-filter (engine + endpoints):
  1. Explicit process selection HARD-filters matched_rules to that process +
     General (campaign 2026-07-06 proved Etch context returned Pharma/Automotive
     rules when process was only a soft signal).
  2. Auto mode reports detected_process / detection_confidence so the user can
     see and correct what Auto-Detect chose.
  3. New endpoints /capa/processes and /capa/rules serve the selector UI.
Module-level filter functions are covered in test_capa_process_filter.py.
"""
import pytest
from fastapi.testclient import TestClient

import main
from capa_rules_engine import run_capa_engine_v2

client = TestClient(main.app)


def _bad_capability(cpk=0.62):
    return {
        "column": "Etch_Rate_nm_min", "n": 250,
        "cp": 0.80, "cpk": cpk, "pp": 0.78, "ppk": cpk - 0.02,
        "mean": 452.0, "std_within": 12.0, "std_overall": 12.5,
        "usl": 480.0, "lsl": 420.0,
        "ppm_total": 45000.0, "sigma_level": 2.1,
    }


def _alarmed_spc():
    return {
        "chart_type": "Xbar-R", "column": "Etch_Rate_nm_min",
        "alarms": [
            {"rule": "WE1", "description": "Point beyond 3-sigma", "index": 41},
            {"rule": "WE2", "description": "9 points same side", "index": 45},
        ],
        "n_subgroups": 50, "in_control": False,
    }


@pytest.mark.parametrize("proc", ["Etch", "CMP", "Automotive"])
def test_explicit_process_hard_filters_rules(proc):
    res = run_capa_engine_v2(
        capability_result=_bad_capability(), spc_result=_alarmed_spc(),
        process_type=proc, parameter_name="Etch_Rate_nm_min",
    )
    procs = {r["process"] for r in res["matched_rules"]}
    assert procs, f"expected some matched rules for {proc}"
    assert procs <= {proc, "General"}, f"foreign rules leaked for {proc}: {procs}"
    assert res["process_mode"] == "explicit"
    assert res["effective_process"] == proc


def test_explicit_selection_case_insensitive():
    res = run_capa_engine_v2(
        capability_result=_bad_capability(), process_type="etch",
        parameter_name="Etch_Rate",
    )
    procs = {r["process"] for r in res["matched_rules"]}
    assert procs <= {"Etch", "General"}


def test_auto_mode_reports_detected_process():
    res = run_capa_engine_v2(
        capability_result=_bad_capability(), spc_result=_alarmed_spc(),
        process_type="", parameter_name="Etch_Rate_nm_min",
        process_context="plasma etch chamber A",
    )
    assert res["process_mode"] == "auto"
    assert res["detected_process"] is not None
    assert res["detection_confidence"] is not None
    assert res["effective_process"] == res["detected_process"]
    assert res["detected_process"] == "Etch"


def test_general_process_type_treated_as_auto():
    res = run_capa_engine_v2(
        capability_result=_bad_capability(), process_type="General",
        parameter_name="Etch_Rate_nm_min",
    )
    assert res["process_mode"] == "auto"
    assert res["detected_process"] is not None


def test_auto_mode_unknown_parameter_falls_back_to_general():
    res = run_capa_engine_v2(
        capability_result=_bad_capability(), process_type="",
        parameter_name="X1",
    )
    assert res["process_mode"] == "auto"
    assert res["effective_process"] in ("General", res["detected_process"])
    assert res["matched_rules"], "General fallback must still match rules"


def test_matched_rules_carry_scope_tag():
    res = run_capa_engine_v2(
        capability_result=_bad_capability(), process_type="Etch",
        parameter_name="Etch_Rate_nm_min",
    )
    for r in res["matched_rules"]:
        assert r["scope"] == ("general" if r["process"] == "General" else "process")


def test_processes_endpoint_groups_and_counts():
    r = client.get("/api/v1/capa/processes")
    assert r.status_code == 200
    groups = r.json()["groups"]
    assert groups, "no process groups returned"
    cats = {g["category"] for g in groups}
    assert "Semiconductor" in cats
    for g in groups:
        assert g["total"] == sum(p["count"] for p in g["processes"])
        for p in g["processes"]:
            assert p["count"] > 0, "processes with zero rules must not be listed"


def test_rules_endpoint_filters_and_tags_scope():
    r = client.get("/api/v1/capa/rules?process=Etch")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["rules"]) > 0
    procs = {x["process"] for x in body["rules"]}
    assert procs <= {"Etch", "General"}
    r2 = client.get("/api/v1/capa/rules?process=Etch&include_general=false")
    procs2 = {x["process"] for x in r2.json()["rules"]}
    assert procs2 == {"Etch"}


def test_rules_endpoint_unknown_process_returns_empty_not_error():
    """Unknown process: no process-scoped rules; cross-cutting General rules
    still apply (module contract per test_capa_process_filter.py). Must be a
    200, never a 500."""
    r = client.get("/api/v1/capa/rules?process=Underwater_Basket_Weaving")
    assert r.status_code == 200
    body = r.json()
    assert body["process_rule_count"] == 0
    assert all(x["scope"] == "general" for x in body["rules"])
    r2 = client.get("/api/v1/capa/rules?process=Underwater_Basket_Weaving&include_general=false")
    assert r2.status_code == 200 and r2.json()["count"] == 0


def test_rules_endpoint_validates_process_param():
    assert client.get("/api/v1/capa/rules").status_code == 422
    assert client.get("/api/v1/capa/rules?process=" + "x" * 41).status_code == 422


def test_generate_endpoint_roundtrip_explicit_and_auto():
    payload = {
        "capability_result": _bad_capability(), "spc_result": _alarmed_spc(),
        "parameter_name": "Etch_Rate_nm_min",
    }
    r = client.post("/api/v1/capa/v2/generate", json={**payload, "process_type": "Etch"})
    assert r.status_code == 200
    j = r.json()
    assert j["process_mode"] == "explicit"
    assert {x["process"] for x in j["matched_rules"]} <= {"Etch", "General"}

    r2 = client.post("/api/v1/capa/v2/generate", json={**payload, "process_type": ""})
    j2 = r2.json()
    assert j2["process_mode"] == "auto"
    assert "detected_process" in j2 and j2["detected_process"]
