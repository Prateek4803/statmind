"""
StatMind P2-A — Control Plan Builder (AIAG 3rd Ed 2024)
Links process steps → characteristics → SPC method → reaction plan.
One of the AIAG 5 Core Tools — completely missing from all free tools.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class ControlPlanEntry:
    step_number: str
    process_name: str
    # Characteristics
    characteristic_name: str
    characteristic_type: str     # "Product", "Process"
    special_char_symbol: str     # "△" "◆" "" (triangle=key, diamond=critical)
    spec_nominal: Optional[float]
    spec_usl: Optional[float]
    spec_lsl: Optional[float]
    spec_units: str
    # Measurement
    measurement_technique: str   # CMM, caliper, SPC chart, visual
    sample_size: int
    sample_frequency: str        # "every lot", "hourly", "5 per shift"
    # Control
    control_method: str          # "I-MR Chart", "Xbar-R", "attribute p-chart", "visual"
    # Reaction Plan
    reaction_plan: str           # what to do when out of spec / OOC signal
    # Linked sessions (populated from StatMind analysis)
    cpk: Optional[float]
    grr_pct: Optional[float]
    spc_status: str              # "In Control", "Out of Control", "Not Run"

@dataclass
class ControlPlan:
    plan_id: str
    part_name: str
    part_number: str
    revision: str
    process_type: str            # "Prototype", "Pre-Launch", "Production"
    team: str
    supplier: str
    plant: str
    date: str
    entries: list
    # Linked
    linked_pfmea_id: Optional[str]
    # Summary
    n_steps: int
    n_critical: int
    n_key: int
    n_failing_cpk: int

_plans: dict = {}

def create_plan(part_name: str, part_number: str = "", revision: str = "A",
                process_type: str = "Production", team: str = "",
                supplier: str = "", plant: str = "") -> ControlPlan:
    pid = f"CP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    plan = ControlPlan(
        plan_id=pid, part_name=part_name, part_number=part_number,
        revision=revision, process_type=process_type, team=team,
        supplier=supplier, plant=plant,
        date=datetime.now().strftime("%Y-%m-%d"),
        entries=[], linked_pfmea_id=None,
        n_steps=0, n_critical=0, n_key=0, n_failing_cpk=0,
    )
    _plans[pid] = plan
    return plan

def add_entry(plan_id: str, data: dict) -> ControlPlan:
    if plan_id not in _plans: raise KeyError(f"Control Plan {plan_id} not found.")
    plan = _plans[plan_id]
    entry = ControlPlanEntry(
        step_number=data.get("step_number", str(len(plan.entries)+1)),
        process_name=data.get("process_name",""),
        characteristic_name=data.get("characteristic_name",""),
        characteristic_type=data.get("characteristic_type","Product"),
        special_char_symbol=data.get("special_char_symbol",""),
        spec_nominal=data.get("spec_nominal"),
        spec_usl=data.get("spec_usl"),
        spec_lsl=data.get("spec_lsl"),
        spec_units=data.get("spec_units","mm"),
        measurement_technique=data.get("measurement_technique",""),
        sample_size=int(data.get("sample_size",5)),
        sample_frequency=data.get("sample_frequency","every lot"),
        control_method=data.get("control_method","I-MR Chart"),
        reaction_plan=data.get("reaction_plan","Stop production, notify supervisor, quarantine last lot."),
        cpk=data.get("cpk"),
        grr_pct=data.get("grr_pct"),
        spc_status=data.get("spc_status","Not Run"),
    )
    plan.entries.append(entry)
    _refresh_plan(plan)
    return plan

def _refresh_plan(plan: ControlPlan):
    plan.n_steps    = len(plan.entries)
    plan.n_critical = sum(1 for e in plan.entries if e.special_char_symbol == "◆")
    plan.n_key      = sum(1 for e in plan.entries if e.special_char_symbol == "△")
    plan.n_failing_cpk = sum(1 for e in plan.entries if e.cpk is not None and e.cpk < 1.33)

def get_plan(pid: str) -> ControlPlan:
    if pid not in _plans: raise KeyError(f"Control Plan {pid} not found.")
    return _plans[pid]

def list_plans() -> list: return list(_plans.values())
def delete_plan(pid: str) -> bool:
    if pid in _plans: del _plans[pid]; return True
    return False

def export_summary(plan: ControlPlan) -> dict:
    """PPAP-compatible summary export."""
    ppap_ok = all(
        (e.cpk is None or e.cpk >= 1.33) and
        (e.grr_pct is None or e.grr_pct <= 30) and
        e.spc_status != "Out of Control"
        for e in plan.entries
    )
    return {
        "plan_id": plan.plan_id,
        "part_name": plan.part_name,
        "part_number": plan.part_number,
        "revision": plan.revision,
        "date": plan.date,
        "n_steps": plan.n_steps,
        "n_critical": plan.n_critical,
        "n_key": plan.n_key,
        "n_failing_cpk": plan.n_failing_cpk,
        "ppap_ready": ppap_ok,
        "entries": [
            {
                "step": e.step_number, "process": e.process_name,
                "characteristic": e.characteristic_name,
                "type": e.characteristic_type, "symbol": e.special_char_symbol,
                "nominal": e.spec_nominal, "usl": e.spec_usl, "lsl": e.spec_lsl,
                "units": e.spec_units, "measurement": e.measurement_technique,
                "n": e.sample_size, "frequency": e.sample_frequency,
                "control": e.control_method, "reaction": e.reaction_plan,
                "cpk": e.cpk, "grr_pct": e.grr_pct, "spc_status": e.spc_status,
                "status": "✓ OK" if (e.cpk is None or e.cpk >= 1.33) else "✗ Cpk < 1.33",
            }
            for e in plan.entries
        ],
    }
