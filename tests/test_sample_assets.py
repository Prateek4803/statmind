"""Teaching empty states (Session 5): the bundled sample datasets must be
served and must remain analyzable end-to-end — each sample is wired to the
analysis whose upload zone offers it, so a broken sample = a broken first-run
experience."""
import io

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)

SAMPLES = [
    "semiconductor_etch_process.csv",
    "gauge_rr_study.csv",
    "pareto_defect_log.csv",
    "multivari_oxide_study.csv",
    "logistic_pass_fail.csv",
    "tool_comparison_AB.csv",
]


def _get_sample(name):
    r = client.get(f"/static/samples/{name}")
    assert r.status_code == 200, f"{name} not served"
    return r.content


def test_all_samples_served():
    for s in SAMPLES:
        body = _get_sample(s)
        assert len(body) > 50
        assert b"," in body.splitlines()[0]  # csv header


def test_samples_run_their_target_analyses():
    """The exact pairings the UI offers must work end-to-end."""
    etch = _get_sample("semiconductor_etch_process.csv")
    f = lambda name, b: {"file": (name, io.BytesIO(b), "text/csv")}

    r = client.post("/api/v1/normality/analyze?column=Etch_Rate_nm_min",
                    files=f("s.csv", etch))
    assert r.status_code == 200

    r = client.post("/api/v1/capability/analyze?column=Etch_Rate_nm_min&usl=480&lsl=420&subgroup_size=5",
                    files=f("s.csv", etch))
    assert r.status_code == 200 and r.json()["cpk"] is not None

    r = client.post("/api/v1/grr/analyze?method=ANOVA&tolerance=30",
                    files=f("g.csv", _get_sample("gauge_rr_study.csv")))
    assert r.status_code == 200
    assert r.json()["column"] == "Thickness_nm"  # AIAG file, Trial excluded

    r = client.post("/api/v1/pareto/analyze?category_col=Defect_Type&count_col=Count",
                    files=f("p.csv", _get_sample("pareto_defect_log.csv")))
    assert r.status_code == 200  # 7-category pre-aggregated file (Session 3 fix)

    r = client.post("/api/v1/multivari/analyze?value_col=Ox_Thickness_A&part_col=Wafer&position_col=Site&time_col=Lot",
                    files=f("m.csv", _get_sample("multivari_oxide_study.csv")))
    assert r.status_code == 200

    r = client.post("/api/v1/hypothesis/from-file?test=two_sample_t&columns=Tool_A,Tool_B",
                    files=f("t.csv", _get_sample("tool_comparison_AB.csv")))
    assert r.status_code == 200
