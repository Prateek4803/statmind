"""
capa_engine/packs/medical_device.py — Medical Device rule pack.

Encodes spec §5 "Rule Pack — Medical Device":
    FDA QMSR / 21 CFR 820 -> ISO 13485:2016 · EU MDR 2017/745 · EU IVDR 2017/746
    Core clauses: ISO 13485 §8.5.2 (corrective), §8.5.3 (preventive);
    legacy 820.100 data-source inputs.

⚠️ REGULATORY DISCLAIMER (from the source spec):
Clause citations are summarised for engineering reference and are NOT legal
advice. The QMSR became effective Feb 2, 2026, folding CAPA into the ISO 13485
structure; this pack is effective-dated accordingly. Verify every clause and
timer against current published regulation before relying on it. Every field
here carries that caveat via `verify_against_current_regulation=True`.
"""
from __future__ import annotations

from ..schema import (
    RulePack, MandatoryFieldGate, RoleGate, TimerGate, EvidenceGate,
    EffectivenessGate, BlockRule,
)


def build_medical_device_pack() -> RulePack:
    return RulePack(
        pack_id="medical_device_qmsr",
        industry="medical_device",
        standards=[
            "FDA QMSR (21 CFR 820, effective 2026-02-02)",
            "ISO 13485:2016",
            "EU MDR 2017/745",
            "EU IVDR 2017/746",
        ],
        effective_from="2026-02-02",

        # Triage gate (spec §3 + §5): recurrence and reportability force full CAPA.
        triage_force_capa_if=[
            "recurrence==true",       # a repeat issue can never be correction-only
            "reportable==true",       # MDR/vigilance reportable -> parallel workflow
            "severity==catastrophic",
            "rpn>=125",               # tenant-configurable threshold
        ],

        # Mandatory-field gates: cannot advance until present.
        mandatory_field_gates=[
            MandatoryFieldGate(
                state="INVESTIGATION",
                fields=["rca_method", "root_cause", "evidence_attachment"],
            ),
            MandatoryFieldGate(
                state="TRIAGE",
                # Spec §3: low-triaged items require a documented justification.
                fields=["severity", "occurrence", "detectability"],
            ),
        ],

        # Role gate: only quality engineers approve the investigation transition.
        role_gates=[
            RoleGate(state="INVESTIGATION", roles_allowed=["quality_engineer"]),
            RoleGate(state="CLOSURE", roles_allowed=["quality_manager"]),
        ],

        # Timer gates — SLAs as stated; VERIFY against current regulation.
        timer_gates=[
            TimerGate(
                state="CONTAINMENT", sla_days=5, on_breach="escalate",
                citation="Containment SLA (tenant policy; verify)",
            ),
        ],

        # Evidence gate: investigation cannot close without an RCA output attached.
        evidence_gates=[
            EvidenceGate(state="INVESTIGATION", required_evidence=["rca_output"]),
        ],

        # Effectiveness gate (spec §2/§5): closure blocked until verification passes
        # after a waiting period. ISO allows preventive effectiveness "where
        # appropriate" -> engine requires it OR a logged justification.
        effectiveness_gate=EffectivenessGate(
            min_wait_days=90,
            preventive_policy="required_or_justified",
        ),

        # Hard block rules (spec §5 pharma rule generalised; applied here as good
        # practice): human-error root cause blocked without system-cause analysis.
        block_rules=[
            BlockRule(
                state="INVESTIGATION",
                condition="root_cause=='human_error' && !system_cause_ruled_out",
                message="'Human error' cannot be the root cause without a "
                        "documented system-cause analysis ruling out process/"
                        "system causes (spec §5).",
            ),
        ],

        # RCA methods available for this industry (spec §5 RCA selector).
        rca_methods=["5-Whys", "Fishbone (6M)", "FMEA update", "Fault Tree Analysis"],

        clause_notes={
            "corrective": "ISO 13485 §8.5.2",
            "preventive": "ISO 13485 §8.5.3",
            "legacy_data_sources": "21 CFR 820.100",
            "parallel_triggers": "complaint -> MDR reportability eval; "
                                 "field issue -> recall / FSCA workflow",
            "qmsr_note": "QMSR effective 2026-02-02 folds CAPA into ISO 13485 "
                         "structure; historical records keep original clause map.",
        },
        verify_against_current_regulation=True,
    )
