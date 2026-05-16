"""
StatMind — NPI Quality Gate Tracker / Product Quality Plan (PQP)
Apple explicitly: "Develop PQP at each development phase"
Google: "NPI cycles", Apple: "NPI to Sustaining"
Amazon Kuiper: "production process validation"

5 phases: Concept → Design → Prototype → Validation → Mass Production
Each phase has mandatory quality gates with pass/fail criteria.
Links to StatMind statistical results (Cpk, GRR, SPC, DOE).
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# AIAG APQP 5 phases mapped to Apple/Google NPI language
PHASE_NAMES = ["Concept (P0)", "Design (P1)", "Prototype (P2)", "Validation (P3)", "Mass Production (P4)"]

PHASE_GATES = {
    "Concept (P0)": [
        {"gate": "CTQ characteristics identified", "tool": "VOC/QFD", "required": True},
        {"gate": "DFMEA initiated", "tool": "PFMEA", "required": True},
        {"gate": "Tolerance analysis complete", "tool": "Tolerance Stack-Up", "required": True},
        {"gate": "Supplier selection criteria defined", "tool": "Supplier Scorecard", "required": False},
    ],
    "Design (P1)": [
        {"gate": "DFMEA completed (all RPN < 200)", "tool": "PFMEA", "required": True},
        {"gate": "GD&T drawings released", "tool": "GD&T", "required": True},
        {"gate": "MSA plan defined", "tool": "GRR", "required": True},
        {"gate": "DOE plan approved", "tool": "DOE", "required": False},
        {"gate": "Control Plan (prototype) approved", "tool": "Control Plan", "required": True},
    ],
    "Prototype (P2)": [
        {"gate": "Gauge R&R < 30% (all critical dimensions)", "tool": "GRR", "required": True},
        {"gate": "Process capability Cpk ≥ 1.00 (prototype)", "tool": "Capability", "required": True},
        {"gate": "SPC charts established", "tool": "SPC", "required": True},
        {"gate": "DOE completed — key factors identified", "tool": "DOE", "required": False},
        {"gate": "First Article Inspection (FAI) approved", "tool": "FAI", "required": True},
        {"gate": "Fishbone/8D closed for any issues", "tool": "8D / Fishbone", "required": False},
    ],
    "Validation (P3)": [
        {"gate": "Cpk ≥ 1.33 on all critical dimensions", "tool": "Capability", "required": True},
        {"gate": "GRR < 10% on all critical dimensions", "tool": "GRR", "required": True},
        {"gate": "SPC in statistical control (30-day run)", "tool": "SPC", "required": True},
        {"gate": "PFMEA updated — all High AP items closed", "tool": "PFMEA", "required": True},
        {"gate": "Control Plan (production) approved", "tool": "Control Plan", "required": True},
        {"gate": "AQL sampling plan approved", "tool": "IQC/AQL", "required": True},
        {"gate": "Reliability testing passed", "tool": "Weibull / ALT", "required": True},
    ],
    "Mass Production (P4)": [
        {"gate": "PPAP submitted and approved (Cpk ≥ 1.67)", "tool": "Capability", "required": True},
        {"gate": "SPC monitoring active", "tool": "SPC", "required": True},
        {"gate": "Supplier scorecard green", "tool": "Supplier Scorecard", "required": True},
        {"gate": "FRACAS system active for field returns", "tool": "FRACAS", "required": False},
        {"gate": "CoPQ baseline established", "tool": "CoPQ", "required": False},
    ],
}

@dataclass
class GateStatus:
    gate: str
    tool: str
    required: bool
    status: str        # "Not Started", "In Progress", "Passed", "Waived", "Failed"
    evidence: str      # link to StatMind result, test report number, etc.
    owner: str
    target_date: str
    actual_date: str
    linked_cpk: Optional[float]
    linked_grr: Optional[float]
    notes: str

@dataclass
class PhaseStatus:
    phase_name: str
    phase_number: int
    gates: list        # list of GateStatus
    overall_status: str  # "Not Started","In Progress","Gate Review","Passed","Failed"
    gate_review_date: str
    approved_by: str
    completion_pct: int

@dataclass
class NPIProject:
    project_id: str
    product_name: str
    part_number: str
    program: str        # "iPhone 17", "Pixel 9", "Project Kuiper v2"
    team: str
    target_mp_date: str  # Mass Production target date
    created_date: str
    current_phase: str
    overall_status: str  # "On Track", "At Risk", "Red"
    phases: list         # list of PhaseStatus
    # Linked analyses summary
    best_cpk: Optional[float]
    best_grr: Optional[float]
    open_issues: int
    notes: str

_projects: dict = {}

def create_npi(product_name: str, part_number: str = "", program: str = "",
               team: str = "", target_mp_date: str = "") -> NPIProject:
    pid = f"NPI-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    phases = []
    for i, phase_name in enumerate(PHASE_NAMES):
        gate_defs = PHASE_GATES.get(phase_name, [])
        gates = [GateStatus(
            gate=g["gate"], tool=g["tool"], required=g["required"],
            status="Not Started", evidence="", owner="",
            target_date="", actual_date="", linked_cpk=None,
            linked_grr=None, notes=""
        ) for g in gate_defs]
        phases.append(PhaseStatus(
            phase_name=phase_name, phase_number=i,
            gates=gates, overall_status="Not Started" if i > 0 else "In Progress",
            gate_review_date="", approved_by="", completion_pct=0,
        ))

    proj = NPIProject(
        project_id=pid, product_name=product_name, part_number=part_number,
        program=program, team=team, target_mp_date=target_mp_date,
        created_date=datetime.now().strftime("%Y-%m-%d"),
        current_phase=PHASE_NAMES[0],
        overall_status="On Track", phases=phases,
        best_cpk=None, best_grr=None, open_issues=0, notes="",
    )
    _projects[pid] = proj
    return proj

def update_gate(project_id: str, phase_name: str, gate_text: str,
                status: str, evidence: str = "", owner: str = "",
                target_date: str = "", cpk: float = None,
                grr: float = None, notes: str = "") -> NPIProject:
    if project_id not in _projects:
        raise KeyError(f"NPI Project {project_id} not found.")
    proj = _projects[project_id]
    for phase in proj.phases:
        if phase.phase_name == phase_name:
            for gate in phase.gates:
                if gate_text.lower() in gate.gate.lower() or gate.gate.lower() in gate_text.lower():
                    gate.status = status
                    if evidence: gate.evidence = evidence
                    if owner:    gate.owner = owner
                    if target_date: gate.target_date = target_date
                    if cpk is not None: gate.linked_cpk = cpk
                    if grr is not None: gate.linked_grr = grr
                    if notes: gate.notes = notes
                    if status == "Passed":
                        gate.actual_date = datetime.now().strftime("%Y-%m-%d")
                    break
            # Update phase completion
            total = len(phase.gates)
            passed = sum(1 for g in phase.gates if g.status in ("Passed","Waived"))
            phase.completion_pct = int(passed/total*100) if total else 0
            if passed == total:
                phase.overall_status = "Passed"
            elif any(g.status == "Failed" for g in phase.gates if g.required):
                phase.overall_status = "Failed"
            elif passed > 0:
                phase.overall_status = "In Progress"
            break
    # Update overall
    failed = any(ph.overall_status == "Failed" for ph in proj.phases)
    at_risk = any(ph.completion_pct < 50 for ph in proj.phases[:2])
    proj.overall_status = "Red" if failed else "At Risk" if at_risk else "On Track"
    if cpk: proj.best_cpk = max(proj.best_cpk or 0, cpk)
    if grr:  proj.best_grr = min(proj.best_grr or 100, grr)
    return proj

def get_npi(pid: str) -> NPIProject:
    if pid not in _projects: raise KeyError(f"NPI {pid} not found.")
    return _projects[pid]
def list_npi() -> list: return list(_projects.values())

import dataclasses as _dc
def npi_to_dict(p: NPIProject) -> dict: return _dc.asdict(p)
