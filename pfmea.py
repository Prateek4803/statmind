"""
StatMind N11 — PFMEA Risk Calculator
Severity × Occurrence × Detection = RPN
PFMEA table, ranked action items, full report.
References: AIAG FMEA 4th Ed, AIAG-VDA FMEA 1st Ed (2019)
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class FMEAEntry:
    id: str
    process_step: str
    function: str
    failure_mode: str
    failure_effect: str
    severity: int       # 1-10
    failure_cause: str
    occurrence: int     # 1-10
    current_controls: str
    detection: int      # 1-10
    rpn: int            # S×O×D
    action_priority: str  # "H","M","L" (AIAG-VDA) or legacy RPN threshold
    recommended_action: str
    responsible: str
    target_date: str
    # After action
    severity_after: Optional[int]
    occurrence_after: Optional[int]
    detection_after: Optional[int]
    rpn_after: Optional[int]
    action_taken: str
    completion_date: str

@dataclass
class PFMEAResult:
    title: str
    process: str
    created_date: str
    entries: list       # list of FMEAEntry
    # Summary
    n_entries: int
    n_high_priority: int
    n_medium_priority: int
    max_rpn: int
    avg_rpn: float
    top_risks: list     # top 5 by RPN
    # After improvement
    avg_rpn_after: Optional[float]
    rpn_reduction_pct: Optional[float]
    # Chart data
    chart_data: dict

_pfmea_store: dict = {}

def _action_priority(s: int, o: int, d: int) -> str:
    """AIAG-VDA 2019 Action Priority (AP) — replaces RPN thresholds."""
    rpn = s * o * d
    if s >= 9:
        if o >= 6 or d >= 7: return "H"
        if o >= 4 or d >= 5: return "H"
        return "M"
    if s >= 7:
        if o >= 6 and d >= 7: return "H"
        if o >= 4 or d >= 6: return "M"
        return "L"
    if rpn >= 200: return "H"
    if rpn >= 100: return "M"
    return "L"

def create_pfmea(title: str, process: str = "") -> dict:
    fid = f"PFMEA-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    proj = {"id": fid, "title": title, "process": process,
            "created": datetime.now().isoformat(), "entries": []}
    _pfmea_store[fid] = proj
    return proj

def add_entry(fmea_id: str, data: dict) -> FMEAEntry:
    if fmea_id not in _pfmea_store: raise KeyError(f"PFMEA {fmea_id} not found.")
    s = max(1, min(10, int(data.get("severity", 5))))
    o = max(1, min(10, int(data.get("occurrence", 5))))
    d = max(1, min(10, int(data.get("detection", 5))))
    rpn = s * o * d
    entry = FMEAEntry(
        id=f"E{len(_pfmea_store[fmea_id]['entries'])+1:03d}",
        process_step=data.get("process_step",""),
        function=data.get("function",""),
        failure_mode=data.get("failure_mode",""),
        failure_effect=data.get("failure_effect",""),
        severity=s, failure_cause=data.get("failure_cause",""),
        occurrence=o, current_controls=data.get("current_controls",""),
        detection=d, rpn=rpn,
        action_priority=_action_priority(s,o,d),
        recommended_action=data.get("recommended_action",""),
        responsible=data.get("responsible",""),
        target_date=data.get("target_date",""),
        severity_after=None, occurrence_after=None,
        detection_after=None, rpn_after=None,
        action_taken="", completion_date="",
    )
    _pfmea_store[fmea_id]["entries"].append(entry)
    return entry

def build_report(fmea_id: str) -> PFMEAResult:
    if fmea_id not in _pfmea_store: raise KeyError(f"PFMEA {fmea_id} not found.")
    p = _pfmea_store[fmea_id]
    entries = p["entries"]
    if not entries:
        return PFMEAResult(title=p["title"], process=p["process"],
            created_date=p["created"], entries=[], n_entries=0,
            n_high_priority=0, n_medium_priority=0, max_rpn=0, avg_rpn=0,
            top_risks=[], avg_rpn_after=None, rpn_reduction_pct=None,
            chart_data={"entries":[]})

    rpns = [e.rpn for e in entries]
    rpns_after = [e.rpn_after for e in entries if e.rpn_after]
    sorted_by_rpn = sorted(entries, key=lambda x: x.rpn, reverse=True)

    chart_data = {
        "failure_modes": [e.failure_mode[:25] for e in sorted_by_rpn[:10]],
        "rpns": [e.rpn for e in sorted_by_rpn[:10]],
        "rpns_after": [e.rpn_after or e.rpn for e in sorted_by_rpn[:10]],
        "priorities": [e.action_priority for e in sorted_by_rpn[:10]],
        "severity_scores": [e.severity for e in entries],
        "occurrence_scores": [e.occurrence for e in entries],
        "detection_scores": [e.detection for e in entries],
    }

    return PFMEAResult(
        title=p["title"], process=p["process"],
        created_date=p["created"], entries=entries,
        n_entries=len(entries),
        n_high_priority=sum(1 for e in entries if e.action_priority=="H"),
        n_medium_priority=sum(1 for e in entries if e.action_priority=="M"),
        max_rpn=max(rpns), avg_rpn=round(sum(rpns)/len(rpns),1),
        top_risks=sorted_by_rpn[:5],
        avg_rpn_after=round(sum(rpns_after)/len(rpns_after),1) if rpns_after else None,
        rpn_reduction_pct=round((1 - sum(rpns_after)/(sum(rpns)+0.001))*100,1) if rpns_after else None,
        chart_data=chart_data,
    )

def list_pfmeas(): return list(_pfmea_store.values())
def get_pfmea(fid: str): return _pfmea_store.get(fid)
