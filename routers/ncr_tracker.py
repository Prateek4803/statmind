"""
StatMind — Non-Conformance Report (NCR) / MRB Tracker
Amazon: "Manage the MRB (Material Review Board) process"
Apple: quality incident tracking
Google: "field issues debug, root cause analysis, corrective actions"
Tracks: NCR → MRB disposition → CAPA → closure
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class NCReport:
    ncr_id: str
    title: str
    part_number: str
    lot_number: str
    quantity_affected: int
    quantity_nonconforming: int
    date_detected: str
    detected_by: str
    detection_point: str     # "IQC", "IPQC", "OQC", "Field", "Customer"
    # Description
    nonconformance_description: str
    # Root cause
    root_cause_category: str  # "Design","Material","Process","Measurement","Human","Unknown"
    root_cause_detail: str
    # MRB Disposition
    mrb_disposition: str     # "Use-As-Is","Rework","Repair","Return","Scrap","Conditional Release"
    mrb_justification: str
    mrb_date: str
    mrb_approver: str
    # Containment
    containment_action: str
    containment_date: str
    # Corrective action
    corrective_action: str
    ca_owner: str
    ca_due_date: str
    ca_completion_date: str
    ca_effectiveness: str    # verification that CA worked
    # Status
    status: str              # "Open","Pending MRB","MRB Complete","CAPA Open","Closed"
    priority: str            # "Critical","Major","Minor"
    # Cost
    scrap_cost: Optional[float]
    rework_cost: Optional[float]
    # Links
    linked_8d_id: Optional[str]
    linked_capa_id: Optional[str]
    closed_date: str
    days_open: int

_ncrs: dict = {}
_ncr_counter = [0]

def create_ncr(title: str, part_number: str = "", lot_number: str = "",
               qty_affected: int = 1, qty_nc: int = 1,
               detection_point: str = "IQC", priority: str = "Major",
               description: str = "") -> NCReport:
    _ncr_counter[0] += 1
    ncr_id = f"NCR-{datetime.now().strftime('%Y%m%d')}-{_ncr_counter[0]:04d}"
    r = NCReport(
        ncr_id=ncr_id, title=title, part_number=part_number,
        lot_number=lot_number, quantity_affected=qty_affected,
        quantity_nonconforming=qty_nc,
        date_detected=datetime.now().strftime("%Y-%m-%d"),
        detected_by="", detection_point=detection_point,
        nonconformance_description=description,
        root_cause_category="Unknown", root_cause_detail="",
        mrb_disposition="Pending", mrb_justification="",
        mrb_date="", mrb_approver="",
        containment_action="", containment_date="",
        corrective_action="", ca_owner="", ca_due_date="",
        ca_completion_date="", ca_effectiveness="",
        status="Open", priority=priority,
        scrap_cost=None, rework_cost=None,
        linked_8d_id=None, linked_capa_id=None,
        closed_date="", days_open=0,
    )
    _ncrs[ncr_id] = r
    return r

def update_ncr(ncr_id: str, updates: dict) -> NCReport:
    if ncr_id not in _ncrs: raise KeyError(f"NCR {ncr_id} not found.")
    r = _ncrs[ncr_id]
    for k, v in updates.items():
        if hasattr(r, k): setattr(r, k, v)
    try:
        created = datetime.strptime(r.date_detected, "%Y-%m-%d")
        r.days_open = (datetime.now() - created).days
    except Exception: pass
    # Auto-update status
    if r.mrb_disposition and r.mrb_disposition != "Pending":
        if r.corrective_action and r.ca_completion_date:
            r.status = "Closed"
            r.closed_date = r.ca_completion_date
        elif r.corrective_action:
            r.status = "CAPA Open"
        else:
            r.status = "MRB Complete"
    elif r.mrb_disposition == "Pending":
        r.status = "Pending MRB"
    return r

def get_ncr(nid: str) -> NCReport:
    if nid not in _ncrs: raise KeyError(f"NCR {nid} not found.")
    return _ncrs[nid]

def list_ncrs(status_filter: str = None) -> list:
    all_ncrs = list(_ncrs.values())
    if status_filter:
        return [r for r in all_ncrs if r.status == status_filter]
    return all_ncrs

def ncr_summary() -> dict:
    all_r = list(_ncrs.values())
    return {
        "total": len(all_r),
        "open": sum(1 for r in all_r if r.status == "Open"),
        "pending_mrb": sum(1 for r in all_r if r.status == "Pending MRB"),
        "capa_open": sum(1 for r in all_r if r.status == "CAPA Open"),
        "closed": sum(1 for r in all_r if r.status == "Closed"),
        "critical": sum(1 for r in all_r if r.priority == "Critical" and r.status != "Closed"),
        "total_scrap_cost": sum(r.scrap_cost or 0 for r in all_r),
        "total_rework_cost": sum(r.rework_cost or 0 for r in all_r),
        "avg_days_open": round(sum(r.days_open for r in all_r if r.status != "Closed") / max(1, sum(1 for r in all_r if r.status != "Closed")), 1),
    }

import dataclasses as _dc
def ncr_to_dict(r: NCReport) -> dict: return _dc.asdict(r)
