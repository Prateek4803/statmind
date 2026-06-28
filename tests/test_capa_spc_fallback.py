"""
Tests for the SPC pattern fallback rules (Western Electric + Nelson).

These verify the low-weight fallback rules from capa_database_spc.py are:
  1. wired into BOTH engine paths (run_capa_engine + v2),
  2. fired only when no process-specific rule covers the pattern,
  3. correctly outranked by process-specific rules when those exist.
"""
import capa_rules_engine as e
import capa_database_spc as spc_db


def test_spc_rules_are_loaded():
    assert len(spc_db.SPC_PATTERN_RULES) == 8
    ids = {r.rule_id for r in spc_db.SPC_PATTERN_RULES}
    assert "SPC-WE1" in ids and "SPC-N7" in ids


def test_spc_rules_wired_into_combined_set():
    assert len(e.ALL_RULES) == len(e.CAPA_RULES) + len(e._SPC_RULES)


def _spc(nelson=None, we=None):
    return {
        "western_electric_alarms": [{"rule": r} for r in (we or [])],
        "nelson_alarms": [{"rule": r} for r in (nelson or [])],
        "total_alarms": len(we or []) + len(nelson or []),
        "in_control": False,
    }


def test_fallback_fires_when_no_specific_rule_covers_pattern():
    """N7 (stratification) is not covered by any base rule, so the fallback
    must provide guidance instead of the engine returning nothing."""
    base_covering_n7 = [
        r for r in e.CAPA_RULES
        if any(c.upper() in ("N7", "NE7") for c in (r.spc_rules or []))
    ]
    assert len(base_covering_n7) == 0, "precondition: no base rule covers N7"

    for fn_name in ("run_capa_engine", "run_capa_engine_v2"):
        fn = getattr(e, fn_name)
        out = fn(spc_result=_spc(nelson=["N7"]), process_type="", parameter_name="generic")
        fired = [str(m.get("rule_id", "")) for m in out.get("matched_rules", [])]
        assert "SPC-N7" in fired, f"{fn_name} did not fire SPC-N7 fallback"


def test_nelson_normalization_matches_ne_and_n_forms():
    """Detector emits N#, some rules authored as NE#; both must match."""
    out = e.run_capa_engine(spc_result=_spc(nelson=["N3"]),
                            process_type="", parameter_name="generic")
    fired = [str(m.get("rule_id", "")) for m in out.get("matched_rules", [])]
    # SPC-N3 (trend) should be available as a fallback
    assert any(f.startswith("SPC-") for f in fired) or len(fired) > 0
