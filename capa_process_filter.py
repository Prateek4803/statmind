"""
capa_process_filter.py — Process-aware filtering for the CAPA rule library.

The existing engine (capa_rules_engine.py) uses process as a SOFT signal when
auto-matching rules to an analysis result. This module adds the complementary
HARD-filter capability the UI needs: "select Etch -> show ONLY etch rules",
plus the metadata a process-selector dropdown needs (process list + counts).

It is purely additive — it reads CAPA_RULES and never mutates the engine's
existing scoring behaviour, so it carries no regression risk to the auto-CAPA
flow.

NOTE ON COVERAGE (honest): the rule library is broad but uneven. Semiconductor
processes — the intended differentiator — are currently shallow (e.g. Etch has
only a handful of rules). `coverage_report()` surfaces this so gaps are visible
rather than hidden, and so domain experts know where to add depth.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

from capa_database_r3 import CAPA_RULES


# Human-friendly groupings for the process selector. Maps a UI category to the
# raw `process` tags used in the rule database. Extend as the library grows.
PROCESS_GROUPS = {
    "Semiconductor": [
        "Etch", "Deposition", "CMP", "Lithography", "Implant",
        "Diffusion", "WetClean", "RTP", "Epitaxy", "Metal",
    ],
    "Automotive (IATF 16949)": ["Automotive"],
    "Aerospace (AS9100)": ["Aerospace"],
    "Medical (ISO 13485)": ["Medical"],
    "Pharma / Biotech": ["Pharma"],
    "Electronics / PCB": ["Electronics"],
    "Injection Molding": ["InjectionMolding"],
    "Welding": ["Welding"],
    "CMM / GD&T": ["CMM"],
    "General": ["General"],
}


def _rule_to_summary(rule) -> dict:
    """Lightweight dict for list display (not the full CAPA report)."""
    return {
        "rule_id": rule.rule_id,
        "process": rule.process,
        "parameter": rule.parameter,
        "fault_pattern": rule.fault_pattern,
        "description": rule.description,
        "severity": rule.severity,
        "root_cause": getattr(rule, "root_cause", "") or "",
    }


def list_processes() -> list[dict]:
    """Return every process tag present in the library with its rule count,
    grouped by category. Powers the process-selector UI."""
    counts: dict[str, int] = {}
    for rule in CAPA_RULES:
        counts[rule.process] = counts.get(rule.process, 0) + 1

    out = []
    for category, tags in PROCESS_GROUPS.items():
        members = [{"process": t, "count": counts.get(t, 0)} for t in tags if counts.get(t, 0) > 0]
        if members:
            out.append({
                "category": category,
                "total": sum(m["count"] for m in members),
                "processes": members,
            })

    # Surface any process tag in the data that isn't mapped above, so nothing
    # silently disappears from the UI if a new tag is added to the database.
    mapped = {t for tags in PROCESS_GROUPS.values() for t in tags}
    unmapped = sorted(p for p in counts if p not in mapped)
    if unmapped:
        out.append({
            "category": "Other",
            "total": sum(counts[p] for p in unmapped),
            "processes": [{"process": p, "count": counts[p]} for p in unmapped],
        })
    return out


def get_rules_by_process(process: str, *, include_general: bool = True) -> list[dict]:
    """Hard filter: return rules for exactly this process tag.

    Args:
        process: a process tag, e.g. "Etch" (case-insensitive).
        include_general: also include cross-cutting "General" rules, which
            apply regardless of process (autocorrelation, Cpk-gap, etc.).
            These are clearly marked so the UI can separate them.

    Returns the matching rule summaries; empty list if the process is unknown.
    """
    if not process:
        return []
    target = process.strip().lower()
    out = []
    for rule in CAPA_RULES:
        p = rule.process.lower()
        if p == target:
            d = _rule_to_summary(rule)
            d["scope"] = "process"
            out.append(d)
        elif include_general and p == "general":
            d = _rule_to_summary(rule)
            d["scope"] = "general"
            out.append(d)
    return out


def coverage_report() -> dict:
    """Honest coverage map: rule count per process, plus a flag for processes
    that are under-covered (fewer than `THIN_THRESHOLD` rules). Intended to make
    gaps visible to whoever maintains the rule library — especially the
    semiconductor processes that are the product's differentiator."""
    THIN_THRESHOLD = 5
    counts: dict[str, int] = {}
    for rule in CAPA_RULES:
        counts[rule.process] = counts.get(rule.process, 0) + 1

    semi = set(PROCESS_GROUPS["Semiconductor"])
    thin = sorted(p for p, c in counts.items() if c < THIN_THRESHOLD)
    thin_semi = sorted(p for p in thin if p in semi)

    return {
        "total_rules": len(CAPA_RULES),
        "process_count": len(counts),
        "per_process": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        "thin_processes": thin,
        "thin_semiconductor_processes": thin_semi,
        "note": (
            "Processes below {n} rules are under-covered. Semiconductor "
            "processes are the intended differentiator and should be "
            "prioritised for rule expansion by a process engineer."
        ).format(n=THIN_THRESHOLD),
    }
