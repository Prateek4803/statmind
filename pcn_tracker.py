"""
StatMind — Process Change Notification (PCN) Tracker
Google Cloud: "PCN qualification". Tracks when suppliers change process.
Requires requalification before approving the change.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class PCNRecord:
    pcn_id: str
    supplier: str
    part_number: str
    change_description: str
    change_category: str     # "Process","Material","Design","Location","Equipment"
    change_impact: str       # "Critical","Major","Minor"
    supplier_notice_date: str
    effective_date: str
    # Qualification status
    status: str             # "Received","Under Review","Qualification","Approved","Rejected","On Hold"
    # Required qualification activities
    dimensional_inspection: str  # "Required","Complete","Waived"
    capability_study: str
    grr_study: str
    reliability_test: str
    functional_test: str
    # Results
    cpk_before: Optional[float]
    cpk_after: Optional[float]
    approved_by: str
    approval_date: str
    reject_reason: str
    notes: str
    days_open: int

_pcns: dict = {}
_pcn_counter = [0]

def create_pcn(supplier: str, part_number: str, change_description: str,
               change_category: str = "Process", impact: str = "Major",
               effective_date: str = "") -> PCNRecord:
    _pcn_counter[0] += 1
    pid = f"PCN-{datetime.now().strftime('%Y%m%d')}-{_pcn_counter[0]:04d}"
    # Determine required activities based on impact
    req_map = {
        "Critical": {"dim":"Required","cap":"Required","grr":"Required","rel":"Required","func":"Required"},
        "Major":    {"dim":"Required","cap":"Required","grr":"Required","rel":"Required","func":"Waived"},
        "Minor":    {"dim":"Required","cap":"Required","grr":"Waived","rel":"Waived","func":"Waived"},
    }
    reqs = req_map.get(impact, req_map["Major"])
    r = PCNRecord(
        pcn_id=pid, supplier=supplier, part_number=part_number,
        change_description=change_description, change_category=change_category,
        change_impact=impact,
        supplier_notice_date=datetime.now().strftime("%Y-%m-%d"),
        effective_date=effective_date, status="Received",
        dimensional_inspection=reqs["dim"],
        capability_study=reqs["cap"],
        grr_study=reqs["grr"],
        reliability_test=reqs["rel"],
        functional_test=reqs["func"],
        cpk_before=None, cpk_after=None,
        approved_by="", approval_date="",
        reject_reason="", notes="",
        days_open=0,
    )
    _pcns[pid] = r
    return r

def update_pcn(pcn_id: str, updates: dict) -> PCNRecord:
    if pcn_id not in _pcns: raise KeyError(f"PCN {pcn_id} not found.")
    r = _pcns[pcn_id]
    for k, v in updates.items():
        if hasattr(r, k): setattr(r, k, v)
    # Auto-approve if all required activities complete
    acts = [r.dimensional_inspection, r.capability_study, r.grr_study, r.reliability_test, r.functional_test]
    all_done = all(a in ("Complete","Waived") for a in acts)
    if all_done and r.status not in ("Approved","Rejected"):
        r.status = "Approved"
        r.approval_date = datetime.now().strftime("%Y-%m-%d")
    try:
        created = datetime.strptime(r.supplier_notice_date, "%Y-%m-%d")
        r.days_open = (datetime.now() - created).days
    except Exception: pass
    return r

def get_pcn(pid: str) -> PCNRecord:
    if pid not in _pcns: raise KeyError(f"PCN {pid} not found.")
    return _pcns[pid]
def list_pcns() -> list: return list(_pcns.values())
def pcn_summary() -> dict:
    pcns = list(_pcns.values())
    return {
        "total": len(pcns),
        "received": sum(1 for p in pcns if p.status == "Received"),
        "under_review": sum(1 for p in pcns if p.status in ("Under Review","Qualification")),
        "approved": sum(1 for p in pcns if p.status == "Approved"),
        "rejected": sum(1 for p in pcns if p.status == "Rejected"),
        "critical_open": sum(1 for p in pcns if p.change_impact == "Critical" and p.status not in ("Approved","Rejected")),
        "avg_days_open": round(sum(p.days_open for p in pcns if p.status not in ("Approved","Rejected")) / max(1, sum(1 for p in pcns if p.status not in ("Approved","Rejected"))), 1),
    }

import dataclasses as _dc
def pcn_to_dict(r: PCNRecord) -> dict: return _dc.asdict(r)
