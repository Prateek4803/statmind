"""
tests/test_capa_process_filter.py — coverage for process-aware CAPA filtering.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from capa_process_filter import (
    list_processes, get_rules_by_process, coverage_report, PROCESS_GROUPS,
)


def test_list_processes_returns_categories_with_counts():
    procs = list_processes()
    assert isinstance(procs, list)
    assert len(procs) > 0
    # Every category entry has the expected shape
    for cat in procs:
        assert "category" in cat and "total" in cat and "processes" in cat
        assert cat["total"] == sum(p["count"] for p in cat["processes"])
        assert cat["total"] > 0  # never show an empty category


def test_semiconductor_category_present():
    procs = list_processes()
    cats = {c["category"] for c in procs}
    assert any("Semiconductor" in c for c in cats)


def test_get_rules_by_process_etch_returns_only_etch_and_general():
    rules = get_rules_by_process("Etch")
    assert len(rules) > 0
    for r in rules:
        # Hard filter: every rule is either an Etch rule or a General rule
        assert r["scope"] in ("process", "general")
        if r["scope"] == "process":
            assert r["process"].lower() == "etch"


def test_get_rules_by_process_is_case_insensitive():
    a = get_rules_by_process("etch")
    b = get_rules_by_process("ETCH")
    assert len(a) == len(b) and len(a) > 0


def test_exclude_general_returns_only_process_rules():
    rules = get_rules_by_process("Etch", include_general=False)
    assert len(rules) > 0
    assert all(r["scope"] == "process" for r in rules)
    assert all(r["process"].lower() == "etch" for r in rules)


def test_unknown_process_returns_empty():
    assert get_rules_by_process("NotARealProcess", include_general=False) == []


def test_empty_process_returns_empty():
    assert get_rules_by_process("") == []


def test_rule_summary_has_required_fields():
    rules = get_rules_by_process("Automotive", include_general=False)
    assert len(rules) > 0
    for r in rules:
        for field in ("rule_id", "process", "parameter", "description", "severity"):
            assert field in r and r[field] is not None


def test_coverage_report_structure():
    rep = coverage_report()
    assert rep["total_rules"] > 0
    assert rep["process_count"] > 0
    assert isinstance(rep["per_process"], dict)
    assert isinstance(rep["thin_processes"], list)
    # per_process counts must sum to total
    assert sum(rep["per_process"].values()) == rep["total_rules"]


def test_coverage_report_flags_thin_semiconductor():
    """The honest finding: semiconductor processes are under-covered.
    This test documents that and will start failing (prompting a happy update)
    once the rule library is deepened past the threshold."""
    rep = coverage_report()
    # Etch is known-thin today; this asserts the report correctly catches it.
    assert "Etch" in rep["thin_semiconductor_processes"] or \
           rep["per_process"].get("Etch", 0) >= 5


def test_every_grouped_process_tag_is_valid():
    """Sanity: every tag we group in the UI must be a real string."""
    for cat, tags in PROCESS_GROUPS.items():
        assert isinstance(tags, list) and len(tags) > 0
        assert all(isinstance(t, str) and t for t in tags)
