"""
StatMind — FDA Regulatory Routing Helpers
=========================================

Two small, structured lookups from public FDA frameworks:

1. Recall severity classification (21 CFR Part 7 / Part 806) — used as a
   SEVERITY MULTIPLIER on top of an existing CAPA risk score, not a trigger.
   Recall class is a *patient-harm* classification, independent of root cause.

2. CFR citation taxonomy (21 CFR 211 drug cGMP, 21 CFR 820 device QSR) — maps a
   cited CFR section to a CAPA category, for auto-tagging and "similar precedent"
   routing on a CAPA opened under the same citation.

References
----------
FDA "Recalls, Corrections and Removals (Devices)" — 21 CFR 7.3 / 806.
21 CFR 211 (drug cGMP), 21 CFR 820 (device Quality System Regulation).
Taxonomy in §4 is a starting routing table, not a verbatim FDA-published table —
validate against current CFR text before regulated use.
"""

from dataclasses import dataclass
from typing import Optional


# ── FDA Recall Severity (21 CFR Part 7) ──────────────────────────────────────
@dataclass
class RecallClassification:
    recall_class: str          # "Class I" | "Class II" | "Class III"
    severity_multiplier: float # applied on top of existing CAPA risk score
    capa_action: str
    reporting_flag: str = ""
    standard_reference: str = "21 CFR 7.3 (recall classification)"


def classify_recall(
    serious_or_death: bool,
    reversible_or_remote: bool = False,
) -> RecallClassification:
    """Classify recall severity per 21 CFR 7.3.

    Class I:  reasonable probability of serious adverse health consequences or death.
    Class II: temporary or medically reversible consequences, or serious harm remote.
    Class III: not likely to cause adverse health consequences.

    The multiplier is a suggested escalation factor on an existing CAPA risk
    score (e.g. RPN) — tune to your scoring scale; it is not an absolute value.
    """
    if serious_or_death:
        return RecallClassification(
            recall_class="Class I", severity_multiplier=3.0,
            capa_action=("Highest-severity CAPA; mandatory Health Hazard Evaluation; "
                         "field action; expedited regulatory notification."),
            reporting_flag="Class I — expedited notification",
        )
    if reversible_or_remote:
        return RecallClassification(
            recall_class="Class II", severity_multiplier=2.0,
            capa_action="High-severity CAPA; effectiveness checks required.",
            reporting_flag="Class II",
        )
    return RecallClassification(
        recall_class="Class III", severity_multiplier=1.0,
        capa_action="Standard CAPA; document and monitor.",
        reporting_flag="Class III",
    )


def correction_removal_reportable() -> RecallClassification:
    """21 CFR 806 correction/removal — flag the 10-working-day FDA reporting clock."""
    return RecallClassification(
        recall_class="Reportable (21 CFR 806)", severity_multiplier=2.0,
        capa_action="Auto-create '10-working-day FDA reporting clock' task.",
        reporting_flag="21 CFR 806 — 10-working-day clock",
        standard_reference="21 CFR 806 (corrections and removals)",
    )


# ── CFR Citation Taxonomy (citation -> CAPA category) ────────────────────────
# Drug cGMP (21 CFR 211)
_CFR_211 = {
    "211.22":  ("Quality System Governance", "Quality unit failed to review/approve, or lacked authority"),
    "211.100": ("Procedural Control", "No written procedures, or procedures not followed"),
    "211.160": ("Procedural Control", "Laboratory controls / procedures not established or followed"),
    "211.165": ("Laboratory Investigation", "Release testing inadequate or incomplete"),
    "211.192": ("Laboratory Investigation", "OOS / discrepancy investigations inadequate"),
    "211.68":  ("Equipment/CSV", "Computer/equipment not validated or controlled"),
    "211.42":  ("Environmental Control", "Facility / contamination control deficiencies"),
    "211.113": ("Environmental Control", "Control of microbiological / objectionable contamination"),
    "211.188": ("Documentation Integrity", "Batch production records incomplete"),
    "211.198": ("Documentation Integrity", "Complaint files incomplete / not handled"),
}

# Device QSR (21 CFR 820)
_CFR_820 = {
    "820.100": ("CAPA System Itself", "No CAPA procedure, or CAPA not effective/closed-loop"),
    "820.30":  ("Design Controls", "Design control / design history file gaps"),
    "820.198": ("Complaint Management", "Complaint handling not documented or investigated"),
    "820.50":  ("Supplier Quality", "Supplier / purchasing controls inadequate"),
    "820.70":  ("Process Validation", "Production / process controls not established"),
    "820.184": ("Record Integrity", "Device history record gaps"),
    "820.186": ("Record Integrity", "Quality system record gaps"),
}

_CFR_ALL = {**_CFR_211, **_CFR_820}


@dataclass
class CFRRouting:
    citation: str
    capa_category: str
    typical_failure: str
    framework: str             # "Drug cGMP (21 CFR 211)" | "Device QSR (21 CFR 820)"
    standard_reference: str = "FDA Warning Letter / 483 citation taxonomy"


def route_cfr_citation(citation: str) -> Optional[CFRRouting]:
    """Map a cited CFR section (e.g. '211.192' or '820.100') to a CAPA category.

    Returns None for an unknown citation rather than guessing — unknown
    citations should be routed to manual triage, not mis-categorized.
    """
    key = (citation or "").strip()
    # Normalize common forms: "21 CFR 211.192", "§211.192", "211.192", "CFR 820.100"
    key = key.replace("§", " ").replace(",", " ")
    chosen = ""
    for token in key.split():
        # a CFR section looks like NNN.NNN where the part before '.' is digits
        if "." in token and token.split(".")[0].isdigit():
            chosen = token
            break
    info = _CFR_ALL.get(chosen)
    if not info:
        return None
    framework = "Drug cGMP (21 CFR 211)" if chosen in _CFR_211 else "Device QSR (21 CFR 820)"
    return CFRRouting(
        citation=chosen, capa_category=info[0], typical_failure=info[1],
        framework=framework,
    )
