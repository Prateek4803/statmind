import dataclasses
from typing import List, Optional

@dataclasses.dataclass
class CAPAAction:
    action: str
    owner: str
    timeline: str
    priority: str
    expected_impact: str

@dataclasses.dataclass
class PreventiveAction:
    action: str
    owner: str
    timeline: str
    system_change: str

@dataclasses.dataclass
class CAPARule:
    rule_id: str
    process: str
    parameter: str
    fault_pattern: str
    severity: str
    description: str
    root_cause: str
    root_cause_detail: str
    alternative_causes: List[str]
    corrective_actions: List[CAPAAction]
    preventive_actions: List[PreventiveAction]
    disposition: str
    containment: str
    standard_reference: str = ""
    weight: float = 1.0
    
    # Statistical Triggers
    cpk_max: Optional[float] = None
    ppk_max: Optional[float] = None
    cp_cpk_gap_min: Optional[float] = None
    ppm_min: Optional[float] = None
    grr_min: Optional[float] = None
    ndc_max: Optional[int] = None
    non_normal: bool = False
    skewness_min: Optional[float] = None
    spc_rules: List[str] = dataclasses.field(default_factory=list)

# The list that the engine loops through
CAPA_RULES = [
    CAPARule(
        rule_id="CAPA-001",
        process="General",
        parameter="Any",
        fault_pattern="Process Shift (Mean Off-Target)",
        severity="Major",
        description="The process mean has shifted away from the target, causing low Cpk despite acceptable Cp.",
        root_cause="Tool calibration drift or raw material lot change.",
        root_cause_detail="A significant gap between Cp and Cpk indicates the process variation is acceptable, but the centering is drifting.",
        alternative_causes=["Operator setup error", "Measurement bias"],
        corrective_actions=[
            CAPAAction("Recalibrate tool to nominal", "Maintenance", "24h", "P1", "Restores centering"),
            CAPAAction("Check first article of current batch", "Quality", "Immediate", "P1", "Verifies fix")
        ],
        preventive_actions=[
            PreventiveAction("Implement daily verification sample", "Quality", "1 Week", "Updated Control Plan")
        ],
        disposition="Sort current batch for OOS",
        containment="Hold current lot.",
        cp_cpk_gap_min=0.2, # Triggers if Cp - Cpk >= 0.2
        weight=1.5
    ),
    CAPARule(
        rule_id="CAPA-002",
        process="General",
        parameter="Any",
        fault_pattern="Excessive Process Variation",
        severity="Critical",
        description="The natural variation of the process exceeds the specification limits (Low Cp and Low Cpk).",
        root_cause="Inherent equipment degradation or unstable parameters.",
        root_cause_detail="Cp is fundamentally too low, meaning centering the process won't fix the defect rate.",
        alternative_causes=["Worn tooling", "Unstable environment (temp/humidity)"],
        corrective_actions=[
            CAPAAction("Perform maintenance tear-down", "Engineering", "48h", "P1", "Reduces variation"),
        ],
        preventive_actions=[
            PreventiveAction("Shorten PM (Preventive Maintenance) cycles", "Maintenance", "1 Month", "Updated PM Schedule")
        ],
        disposition="100% Inspection required",
        containment="Hold and 100% sort all recent production.",
        cpk_max=1.0,
        weight=2.0
    )
]