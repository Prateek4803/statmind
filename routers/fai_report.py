"""
StatMind — First Article Inspection (FAI) Report
AS9102 Rev B (aerospace) + AIAG PPAP-compatible.
Amazon Kuiper (aerospace), Google hardware, Apple NPI all require FAI.
No free FAI tool exists anywhere.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class FAIMeasurement:
    balloon_number: str      # drawing balloon number
    characteristic: str      # dimension name
    nominal: float
    upper_tol: float
    lower_tol: float
    usl: float               # computed: nominal + upper_tol
    lsl: float               # computed: nominal - lower_tol
    actual_values: list      # list of measured values (min 3)
    mean: float
    range_val: float
    cpk: Optional[float]
    conforming: bool         # all within spec?
    measurement_tool: str    # CMM, caliper, optical
    notes: str

@dataclass
class FAIReport:
    report_id: str
    part_name: str
    part_number: str
    revision: str
    drawing_number: str
    supplier: str
    customer: str
    po_number: str
    lot_number: str
    quantity_inspected: int
    inspection_date: str
    inspector: str
    report_type: str         # "Full FAI", "Partial FAI", "Delta FAI"
    # AS9102 Form 1: Part Number Accountability
    form1_complete: bool
    material_cert_attached: bool
    # Form 2: Product Accountability
    measurements: list       # list of FAIMeasurement
    n_characteristics: int
    n_conforming: int
    n_nonconforming: int
    # Form 3: Design Characteristic Accountability
    functional_test_pass: bool
    functional_test_notes: str
    # Overall
    overall_disposition: str  # "APPROVED", "CONDITIONAL", "REJECTED"
    open_discrepancies: list
    customer_approval: str
    created_date: str
    # Linked capability
    overall_cpk: Optional[float]

_fai_reports: dict = {}

def create_fai(part_name: str, part_number: str, revision: str = "A",
               supplier: str = "", customer: str = "", report_type: str = "Full FAI") -> FAIReport:
    rid = f"FAI-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    r = FAIReport(
        report_id=rid, part_name=part_name, part_number=part_number,
        revision=revision, drawing_number="", supplier=supplier,
        customer=customer, po_number="", lot_number="",
        quantity_inspected=3, inspection_date=datetime.now().strftime("%Y-%m-%d"),
        inspector="", report_type=report_type,
        form1_complete=False, material_cert_attached=False,
        measurements=[], n_characteristics=0, n_conforming=0, n_nonconforming=0,
        functional_test_pass=False, functional_test_notes="",
        overall_disposition="PENDING", open_discrepancies=[],
        customer_approval="", created_date=datetime.now().strftime("%Y-%m-%d"),
        overall_cpk=None,
    )
    _fai_reports[rid] = r
    return r

def add_measurement(report_id: str, data: dict) -> FAIReport:
    import numpy as np
    if report_id not in _fai_reports: raise KeyError(f"FAI {report_id} not found.")
    r = _fai_reports[report_id]
    nom   = float(data.get("nominal", 0))
    u_tol = float(data.get("upper_tol", 0))
    l_tol = float(data.get("lower_tol", 0))
    usl   = nom + u_tol
    lsl   = nom - l_tol
    vals  = [float(v) for v in data.get("actual_values", [])]
    mean  = float(np.mean(vals)) if vals else 0
    rng   = float(np.ptp(vals)) if len(vals) > 1 else 0
    std   = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0
    cpk   = None
    if std > 0 and usl > lsl:
        cpk = round(float(min((usl-mean)/(3*std), (mean-lsl)/(3*std))), 4)
    conforming = all(lsl <= v <= usl for v in vals) if vals else True
    m = FAIMeasurement(
        balloon_number=str(data.get("balloon_number","1")),
        characteristic=data.get("characteristic",""),
        nominal=nom, upper_tol=u_tol, lower_tol=l_tol,
        usl=round(usl,6), lsl=round(lsl,6),
        actual_values=vals, mean=round(mean,6), range_val=round(rng,6),
        cpk=cpk, conforming=conforming,
        measurement_tool=data.get("measurement_tool","CMM"),
        notes=data.get("notes",""),
    )
    r.measurements.append(m)
    # Recompute summary
    r.n_characteristics = len(r.measurements)
    r.n_conforming      = sum(1 for x in r.measurements if x.conforming)
    r.n_nonconforming   = r.n_characteristics - r.n_conforming
    cpk_vals = [x.cpk for x in r.measurements if x.cpk is not None]
    r.overall_cpk = round(min(cpk_vals), 4) if cpk_vals else None
    if r.n_nonconforming == 0 and r.n_characteristics > 0:
        r.overall_disposition = "APPROVED"
    elif r.n_nonconforming > 0:
        r.overall_disposition = "REJECTED" if r.n_nonconforming / r.n_characteristics > 0.1 else "CONDITIONAL"
    return r

def get_fai(rid: str) -> FAIReport:
    if rid not in _fai_reports: raise KeyError(f"FAI {rid} not found.")
    return _fai_reports[rid]
def list_fai() -> list: return list(_fai_reports.values())

import dataclasses as _dc
def fai_to_dict(r: FAIReport) -> dict: return _dc.asdict(r)
