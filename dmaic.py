"""
StatMind N9 — DMAIC Project Tracker
Define → Measure → Analyze → Improve → Control
Links analyses to phases, tracks progress, stores results.
"""
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class DMAICPhase:
    name: str           # Define/Measure/Analyze/Improve/Control
    status: str         # "not_started","in_progress","complete"
    completion_pct: int
    tools_used: list    # e.g. ["Normality","Capability","SPC"]
    analyses_linked: list  # result summaries
    notes: str
    target_date: str
    completed_date: str

@dataclass
class DMAICProject:
    project_id: str
    title: str
    process: str
    parameter: str
    problem_statement: str
    goal: str
    team: str
    start_date: str
    target_date: str
    status: str         # "active","complete","on_hold"
    phases: list        # 5 DMAICPhase objects
    overall_pct: int
    chart_data: dict
    last_updated: str

# In-memory store (persists per server session)
_projects: dict = {}

def create_project(
    title: str, process: str = "", parameter: str = "",
    problem_statement: str = "", goal: str = "",
    team: str = "", target_date: str = "",
) -> DMAICProject:
    pid = f"DMAIC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    phases = []
    phase_tools = {
        "Define":  ["Project Charter","SIPOC","VOC","CTQ Tree","Fishbone"],
        "Measure": ["Normality","Capability (Cpk)","GRR/MSA","SPC","Data Collection Plan"],
        "Analyze": ["Hypothesis Testing","Regression","Multi-Vari","Pareto","Correlation"],
        "Improve": ["DOE","Box-Cox","Tolerance Intervals","Solution Matrix"],
        "Control": ["SPC Control Plan","Capability Sixpack","PDF Report","CAPA Engine"],
    }
    for name in ["Define","Measure","Analyze","Improve","Control"]:
        phases.append(DMAICPhase(
            name=name, status="not_started", completion_pct=0,
            tools_used=[], analyses_linked=[],
            notes="", target_date="", completed_date="",
        ))
    proj = DMAICProject(
        project_id=pid, title=title, process=process,
        parameter=parameter, problem_statement=problem_statement,
        goal=goal, team=team, start_date=datetime.now().strftime("%Y-%m-%d"),
        target_date=target_date, status="active",
        phases=phases, overall_pct=0,
        chart_data={"phase_names":["Define","Measure","Analyze","Improve","Control"],
                    "phase_tools": phase_tools, "pcts":[0]*5},
        last_updated=datetime.now().isoformat(),
    )
    _projects[pid] = proj
    return proj

def update_phase(pid: str, phase_name: str, status: str = None,
                 completion_pct: int = None, notes: str = None,
                 tool: str = None, analysis_summary: dict = None) -> DMAICProject:
    if pid not in _projects: raise KeyError(f"Project {pid} not found.")
    proj = _projects[pid]
    for ph in proj.phases:
        if ph.name == phase_name:
            if status: ph.status = status
            if completion_pct is not None: ph.completion_pct = completion_pct
            if notes: ph.notes = notes
            if tool and tool not in ph.tools_used: ph.tools_used.append(tool)
            if analysis_summary: ph.analyses_linked.append(analysis_summary)
            if status == "complete":
                ph.completed_date = datetime.now().strftime("%Y-%m-%d")
                ph.completion_pct = 100
            break
    # Recalculate overall
    pcts = [ph.completion_pct for ph in proj.phases]
    proj.overall_pct = int(sum(pcts) / len(pcts))
    proj.chart_data["pcts"] = pcts
    proj.last_updated = datetime.now().isoformat()
    if proj.overall_pct == 100: proj.status = "complete"
    return proj

def list_projects() -> list: return list(_projects.values())
def get_project(pid: str) -> DMAICProject:
    if pid not in _projects: raise KeyError(f"Project {pid} not found.")
    return _projects[pid]
def delete_project(pid: str) -> bool:
    if pid in _projects: del _projects[pid]; return True
    return False
