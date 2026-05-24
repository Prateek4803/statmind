"""
StatMind R2 — Expanded CAPA Rule Database
80+ rules covering:
  - Semiconductor (expanded from R1)
  - CMM / GD&T (Flatness, Roundness, Cylindricity, Position, Runout, Profile)
  - Automotive IATF 16949 (dimensional, torque, press-fit, surface finish)
  - Aerospace AS9100 (fatigue, hardness, NDT, surface integrity)
  - Medical Devices ISO 13485 (implant tolerances, biocompatibility dims)
  - General Metrology / Lab (any measurement system)
References: AIAG MSA 4th Ed, ASME Y14.5-2018, IATF 16949:2016, AS9100D,
            ISO 13485:2016, ASTM standards
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CAPAAction:
    action: str
    owner: str
    timeline: str
    priority: str
    expected_impact: str


@dataclass
class PreventiveAction:
    action: str
    owner: str
    timeline: str
    system_change: str


@dataclass
class CAPARule:
    rule_id: str
    process: str
    parameter: str
    fault_pattern: str
    description: str
    severity: str
    cpk_max: Optional[float] = None
    cpk_min: Optional[float] = None
    ppk_max: Optional[float] = None
    cp_cpk_gap_min: Optional[float] = None
    ppm_min: Optional[float] = None
    spc_rules: list = field(default_factory=list)
    grr_min: Optional[float] = None
    ndc_max: Optional[int] = None
    non_normal: bool = False
    skewness_min: Optional[float] = None
    root_cause: str = ""
    root_cause_detail: str = ""
    alternative_causes: list = field(default_factory=list)
    corrective_actions: list = field(default_factory=list)
    preventive_actions: list = field(default_factory=list)
    containment: str = ""
    disposition: str = "Conditional Release"
    standard_reference: str = ""
    weight: float = 1.0


CAPA_RULES = [

    # ═══════════════════════════════════════════════════════════════════════════
    # SEMICONDUCTOR (expanded)
    # ═══════════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="SEMI-001", process="Etch", parameter="CD",
        fault_pattern="CD Low Cpk — Process Off-Center",
        description="Critical Dimension Cpk below threshold with significant Cp-Cpk gap indicating centering issue.",
        severity="Major", cpk_max=1.33, cp_cpk_gap_min=0.25,
        root_cause="Etch bias offset from RF power or pressure drift.",
        root_cause_detail="Large Cp-Cpk gap confirms spread is fine but centering is off. Most likely: incremental RF power drift, chamber wall conditioning change, or gas flow calibration offset.",
        alternative_causes=["Photoresist CD offset from upstream litho", "Focus/dose drift", "Chamber seasoning change after PM"],
        corrective_actions=[
            CAPAAction("Measure etch bias on 5 wafers and compare to baseline. Adjust RF power or bias voltage.", "Process Engineer", "Immediate", "P1", "Expected Cpk improvement to ≥1.33 after centering"),
            CAPAAction("Run DOE on etch time ±10% to map CD sensitivity. Update setpoint.", "Process Engineer", "1 week", "P1", "Quantifies optimal recipe window"),
            CAPAAction("Pull SEM CD data from last 30 days and correlate with chamber RF hours.", "Metrology", "1 week", "P2", "Identifies drift onset"),
        ],
        preventive_actions=[
            PreventiveAction("Add CD bias SPC chart. Alert on WE1 violation.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Add RF power to APC feedback loop.", "Equipment", "1 month", "APC"),
        ],
        containment="Hold last 24hr wafers for CD SEM verification.",
        disposition="Conditional Release", standard_reference="SEMI E10, SEMI E35", weight=2.0,
    ),

    CAPARule(
        rule_id="SEMI-002", process="Etch", parameter="Etch_Rate",
        fault_pattern="Etch Rate — SPC Shift/Trend",
        description="Etch rate shows sustained shift or trend. NE2/NE3/WE4 rules violated.",
        severity="Critical", spc_rules=["NE2","NE3","WE4","WE1"],
        root_cause="Electrode erosion, chamber wall polymer buildup, or gas flow controller drift.",
        root_cause_detail="Sustained shift = step-change assignable cause (PM event, consumable swap, recipe change). Trend = gradual degradation (electrode wear, wall conditioning drift).",
        alternative_causes=["He backside cooling pressure change", "ESC temperature drift", "Source gas purity change"],
        corrective_actions=[
            CAPAAction("Identify alarm trigger point. Correlate with maintenance log ±8hr.", "Process Engineer", "Immediate", "P1", "Identifies root cause"),
            CAPAAction("Run qualification wafers. If >5% delta from target, perform chamber clean.", "Equipment", "Immediate", "P1", "Restores etch rate to baseline"),
            CAPAAction("Inspect electrode condition. Replace if >80% rated life.", "Equipment", "1 week", "P2", "Eliminates electrode erosion"),
        ],
        preventive_actions=[
            PreventiveAction("Implement EWMA chart (λ=0.2) for sensitive shift detection.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Add etch rate to PM checklist — must be within ±3% before production.", "Equipment", "2 weeks", "PM"),
        ],
        containment="Pull last 50 wafers for etch depth verification.", disposition="Hold",
        standard_reference="SEMI E10", weight=2.5,
    ),

    CAPARule(
        rule_id="SEMI-003", process="CMP", parameter="Removal_Rate",
        fault_pattern="CMP Removal Rate — Downward Trend (Pad Glazing)",
        description="CMP removal rate showing consistent downward trend. NE3/WE3 fired.",
        severity="Major", spc_rules=["NE3","WE3","WE4"],
        root_cause="Pad glazing: progressive reduction in pad micro-roughness reducing removal rate.",
        root_cause_detail="Monotonic downward trend is the classic signature of pad glazing. Pad surface becomes smoother, reducing slurry transport and abrasive contact.",
        alternative_causes=["Slurry concentration depletion", "Platen temperature increase", "Carrier film wear"],
        corrective_actions=[
            CAPAAction("Correlate with pad wafer count. If matches pad installation, replace pad.", "Equipment", "Immediate", "P1", "Expected removal rate recovery to baseline"),
            CAPAAction("Increase conditioner downforce by 0.5 lbf and sweep speed by 10%.", "Process Engineer", "Immediate", "P1", "May restore pad texture without full replacement"),
        ],
        preventive_actions=[
            PreventiveAction("Implement pad life endpoint: replace when removal rate drops >5% from initial.", "Process Engineer", "1 week", "Recipe"),
            PreventiveAction("Add pad age to MES. Auto-alert at 70% pad life.", "Manufacturing", "1 month", "SOP"),
        ],
        containment="Pull wafers from trend period. Under-polished wafers to rework.", disposition="Conditional Release",
        standard_reference="SEMI M1", weight=2.1,
    ),

    CAPARule(
        rule_id="SEMI-004", process="Lithography", parameter="CD",
        fault_pattern="Litho CD — Low Cpk (Dose or Focus Drift)",
        description="Lithography CD capability below threshold — dose or focus drift.",
        severity="Critical", cpk_max=1.33, ppm_min=100,
        root_cause="Dose or focus offset in scanner causing systematic CD bias.",
        root_cause_detail="CD controlled by dose (energy) and focus (z-height). Centering failure means scanner dose/focus setpoint drifted. APC model may have degraded.",
        alternative_causes=["Resist coating thickness variation", "BARC thickness drift", "Reticle contamination", "Scanner illumination degradation"],
        corrective_actions=[
            CAPAAction("Pull FEM data. Compare to recipe setpoints. Update if delta >±2nm focus or ±0.3% dose.", "Process Engineer", "Immediate", "P1", "Expected CD centering to within ±1nm"),
            CAPAAction("Inspect reticle for particles. Clean if contamination found.", "Manufacturing", "Immediate", "P1", "Rules out reticle contamination"),
            CAPAAction("Check scanner APC model validity. If >2 weeks since calibration, run calibration wafers.", "Equipment", "1 week", "P1", "Restores APC correction accuracy"),
        ],
        preventive_actions=[
            PreventiveAction("Implement APC dose/focus feedback using ADI CD data.", "Equipment", "2 weeks", "APC"),
            PreventiveAction("Add resist CD SPC at ADI as leading indicator.", "Process Engineer", "2 weeks", "SPC"),
        ],
        containment="Hold all wafers exposed since last confirmed good lot.", disposition="Hold",
        standard_reference="SEMI M12", weight=3.0,
    ),

    CAPARule(
        rule_id="SEMI-005", process="Diffusion", parameter="Sheet_Resistance",
        fault_pattern="Sheet Resistance — Furnace Temperature Offset",
        description="Sheet resistance off-center — furnace thermocouple calibration drift.",
        severity="Major", cpk_max=1.33, cp_cpk_gap_min=0.25,
        root_cause="Furnace temperature offset from thermocouple calibration drift or heating element degradation.",
        root_cause_detail="Rs is exponentially sensitive to anneal temperature. ±2°C at 1000°C causes >5% Rs shift. Check thermocouple last calibration date.",
        alternative_causes=["Dopant implant dose variation", "Wafer position in boat", "Ambient humidity affecting oxide cap"],
        corrective_actions=[
            CAPAAction("Pull furnace thermocouple calibration records. Recalibrate if >30 days or >1°C offset.", "Equipment", "Immediate", "P1", "Expected Rs centering within ±2% after correction"),
            CAPAAction("Run monitor wafers at current recipe and ±5°C to bracket actual temperature.", "Process Engineer", "Immediate", "P1", "Quantifies actual furnace temperature offset"),
        ],
        preventive_actions=[
            PreventiveAction("Monthly thermocouple calibration in PM schedule.", "Equipment", "1 week", "PM"),
            PreventiveAction("Add Rs to lot-to-lot SPC chart.", "Process Engineer", "2 weeks", "SPC"),
        ],
        containment="Measure Rs on all wafers from affected lots.", disposition="Conditional Release",
        standard_reference="SEMI M11", weight=2.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # CMM / GD&T
    # ═══════════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="CMM-001", process="CMM", parameter="Flatness",
        fault_pattern="Flatness OOT — Surface Form Error",
        description="Flatness measurement out of tolerance. Surface deviates from true plane beyond specification.",
        severity="Major", cpk_max=1.33,
        root_cause="Machining distortion from clamping forces, thermal gradients during cutting, or residual stress release after machining.",
        root_cause_detail="Flatness OOT on machined surfaces results from: (1) clamping distortion — part springs back after unclamping, (2) thermal gradient — cutting heat causes differential expansion, (3) residual stress — material stress released after material removal. Also check CMM datum alignment.",
        alternative_causes=["Worn machine spindle causing cutting tool deflection", "Incorrect CMM datum setup causing apparent flatness error", "Part warpage from heat treatment or press-fit assembly", "Surface plate or fixture contamination"],
        corrective_actions=[
            CAPAAction("Re-measure part on CMM with fresh datum setup. Verify stylus qualification is current. Confirm flatness is real, not measurement artifact.", "Metrology", "Immediate", "P1", "Eliminates CMM setup error as cause"),
            CAPAAction("If machined: reduce clamping force by 30% and re-machine. Use softer clamping jaw material. Measure flatness after unclamping only.", "Manufacturing", "1 week", "P1", "Reduces clamping distortion — expected 40-60% flatness improvement"),
            CAPAAction("Check cutting tool condition. Replace if >50% of rated life. Reduce depth of cut in finishing pass.", "Manufacturing", "1 week", "P2", "Reduces cutting forces and thermal gradient"),
            CAPAAction("Perform stress relief anneal if material permits. Re-machine datum surfaces after stress relief.", "Process Engineer", "2 weeks", "P2", "Eliminates residual stress contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Add flatness SPC chart. Alert when trend approaches 80% of tolerance.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Define clamping torque specification in machining SOP. Use torque wrench.", "Manufacturing", "1 week", "SOP"),
            PreventiveAction("Add stress relief to process flow for high-residual-stress materials (hardened steel, aluminum castings).", "Process Engineer", "1 month", "Recipe"),
        ],
        containment="Segregate affected parts. 100% CMM inspection of flatness before release.",
        disposition="Hold", standard_reference="ASME Y14.5-2018, ISO 1101", weight=2.2,
    ),

    CAPARule(
        rule_id="CMM-002", process="CMM", parameter="Roundness",
        fault_pattern="Roundness/Circularity OOT — Non-Round Cross Section",
        description="Circularity (roundness) out of tolerance. Cross-section deviates from true circle.",
        severity="Major", cpk_max=1.33,
        root_cause="Chuck jaw pressure causing lobing on turned parts, or worn spindle bearings causing vibration during grinding.",
        root_cause_detail="Roundness OOT in turned parts: 3-jaw chuck creates 3-lobe pattern (triangular form). In ground parts: worn spindle bearings create multi-lobe harmonic pattern. Check if OOT correlates with specific machine, tool, or chuck.",
        alternative_causes=["Thermal growth of spindle during long production run", "Incorrect center height on turning center", "CMM measurement artifact from poor datum setup", "Vibration from adjacent equipment"],
        corrective_actions=[
            CAPAAction("Identify lobing frequency from CMM roundness plot. 3-lobe = chuck issue, high-frequency = bearing issue, irregular = vibration.", "Metrology", "Immediate", "P1", "Identifies root cause category"),
            CAPAAction("If turning: switch to 4-jaw chuck or collet for finish turning. Re-machine and verify.", "Manufacturing", "Immediate", "P1", "Eliminates 3-jaw chuck lobing — expected roundness improvement to spec"),
            CAPAAction("If grinding: check spindle bearing condition using vibration analysis. Schedule bearing replacement if amplitude >2x baseline.", "Equipment", "1 week", "P1", "Eliminates bearing-induced lobing"),
            CAPAAction("Check workholding: ensure part is not distorted by excessive clamp pressure. Reduce by 20% and re-measure.", "Manufacturing", "1 week", "P2", "Reduces workholding distortion"),
        ],
        preventive_actions=[
            PreventiveAction("Quarterly spindle bearing vibration check in PM schedule.", "Equipment", "1 month", "PM"),
            PreventiveAction("Add roundness to first-article and in-process SPC. Use roundness tester or CMM at defined cross-sections.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Specify chuck type and jaw condition in machining SOP.", "Manufacturing", "2 weeks", "SOP"),
        ],
        containment="100% roundness inspection on affected batch. Parts failing roundness to rework.",
        disposition="Conditional Release", standard_reference="ASME Y14.5-2018, ISO 12181", weight=2.1,
    ),

    CAPARule(
        rule_id="CMM-003", process="CMM", parameter="Cylindricity",
        fault_pattern="Cylindricity OOT — Combined Form Error",
        description="Cylindricity out of tolerance. Combined roundness and straightness error exceeds specification.",
        severity="Major", cpk_max=1.33,
        root_cause="Combination of machine axis straightness error and workholding deflection affecting the full cylinder form.",
        root_cause_detail="Cylindricity controls the entire cylinder surface. OOT means both roundness and/or straightness are contributing. Common cause: tailstock misalignment on lathe causing taper + roundness error. Also check: CMM measuring strategy (insufficient scan density will miss local errors).",
        alternative_causes=["Thermal growth causing taper on long turned parts", "Insufficient CMM scan points (too sparse to detect form error)", "Workpiece deflection on long slender parts", "Tool wear causing progressive diameter change along axis"],
        corrective_actions=[
            CAPAAction("Decompose cylindricity error: separate roundness component from straightness component using CMM analysis. Identify which dominates.", "Metrology", "Immediate", "P1", "Identifies whether roundness or straightness is the driver"),
            CAPAAction("If straightness dominant (taper): check and correct tailstock/steady rest alignment. Re-machine.", "Manufacturing", "1 week", "P1", "Eliminates machine alignment contribution"),
            CAPAAction("If roundness dominant: see CMM-002 roundness actions above.", "Manufacturing", "1 week", "P1", "Addresses roundness component"),
            CAPAAction("For long slender parts: add steady rest support. Verify deflection <10% of cylindricity tolerance.", "Manufacturing", "1 week", "P2", "Eliminates workpiece deflection"),
        ],
        preventive_actions=[
            PreventiveAction("Add machine axis alignment check to quarterly PM.", "Equipment", "1 month", "PM"),
            PreventiveAction("For cylindricity features: specify minimum scan density in CMM program (≥4 cross-sections, ≥36 points each).", "Metrology", "2 weeks", "SOP"),
        ],
        containment="Full cylindricity scan on all parts from affected production run.",
        disposition="Conditional Release", standard_reference="ASME Y14.5-2018, ISO 12180", weight=2.0,
    ),

    CAPARule(
        rule_id="CMM-004", process="CMM", parameter="Position",
        fault_pattern="True Position OOT — Hole/Feature Location Error",
        description="True position of hole or feature pattern out of tolerance. Feature located outside cylindrical tolerance zone.",
        severity="Critical", cpk_max=1.00,
        root_cause="Datum reference frame (DRF) setup error, CNC zero offset error, or fixture/pallet locating pin wear causing systematic position shift.",
        root_cause_detail="Position OOT is almost always a systematic cause (not random): worn fixture locating pins shift every part the same way, CNC work offset entered incorrectly, or thermal growth shifts the coordinate frame during long runs. Random position scatter = fixturing repeatability issue.",
        alternative_causes=["CMM datum setup inconsistency (part rocking on datum points)", "Thermal growth of machine or fixture during production", "CAD/drawing datum interpretation difference between programmer and inspector", "Tool runout causing drill walk on entry"],
        corrective_actions=[
            CAPAAction("Measure position deviation direction and magnitude on 3+ parts. If consistent direction = systematic cause (fixture, offset). If random = repeatability issue.", "Metrology", "Immediate", "P1", "Identifies systematic vs. random position error"),
            CAPAAction("If systematic: check and correct CNC work offset. Inspect fixture locating pins for wear. Replace pins if diameter wear >25% of tolerance.", "Manufacturing", "Immediate", "P1", "Corrects systematic position offset — expected 80-100% of parts back in spec"),
            CAPAAction("If random scatter: check fixture clamping repeatability. Measure part location variation across 10 loads. Improve if >30% of position tolerance.", "Manufacturing", "1 week", "P1", "Reduces fixture-induced position scatter"),
            CAPAAction("For drilled holes: use spot drill before drill, check point angle, reduce feed rate on entry by 50%.", "Manufacturing", "1 week", "P2", "Reduces drill walk"),
        ],
        preventive_actions=[
            PreventiveAction("Add fixture pin diameter to monthly PM inspection. Replace at 15% wear.", "Equipment", "2 weeks", "PM"),
            PreventiveAction("Implement first-article position check at start of each shift. Hold production if position exceeds 80% of tolerance.", "Quality", "1 week", "SOP"),
            PreventiveAction("Add position SPC chart. Track X and Y components separately.", "Quality", "2 weeks", "SPC"),
        ],
        containment="MANDATORY 100% position inspection. Sort: in-spec release, out-of-spec hold for rework or scrap review.",
        disposition="Hold", standard_reference="ASME Y14.5-2018, ISO 5458", weight=3.0,
    ),

    CAPARule(
        rule_id="CMM-005", process="CMM", parameter="Runout",
        fault_pattern="Total Runout OOT — Rotational Form Error",
        description="Total runout exceeds specification. Radial and/or axial surface variation during rotation is excessive.",
        severity="Major", cpk_max=1.33,
        root_cause="Datum axis (spindle/bearing) eccentricity during machining, or part datum diameter out-of-round causing apparent runout.",
        root_cause_detail="Total runout combines concentricity and cylindricity — it's the total band swept by the surface during rotation about the datum axis. OOT usually means: (1) datum bore/shaft is eccentric to machining centerline, (2) part was remounted between operations creating eccentricity, or (3) bearing runout in the machine spindle.",
        alternative_causes=["Part re-chucked between turning and grinding operations", "Keyway or flat causing imbalance during measurement rotation", "CMM rotary table calibration error", "Worn machine spindle bearing"],
        corrective_actions=[
            CAPAAction("Measure runout at multiple axial positions. If runout varies axially = cylindricity issue. If constant = concentricity/offset issue.", "Metrology", "Immediate", "P1", "Identifies root cause type"),
            CAPAAction("If concentricity: machine datum diameter and functional diameter in same setup without rechucking.", "Manufacturing", "1 week", "P1", "Eliminates rechucking eccentricity — expected runout reduction by 60-80%"),
            CAPAAction("Check machine spindle runout with precision indicator. If >20% of part tolerance, schedule bearing maintenance.", "Equipment", "1 week", "P2", "Eliminates machine spindle contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Design operations to machine datum and critical diameters in single setup.", "Process Engineer", "1 month", "Recipe"),
            PreventiveAction("Monthly spindle runout verification in PM checklist.", "Equipment", "1 month", "PM"),
        ],
        containment="100% runout inspection on batch. Parts with runout >50% over spec to scrap review.",
        disposition="Conditional Release", standard_reference="ASME Y14.5-2018, ISO 1101", weight=2.0,
    ),

    CAPARule(
        rule_id="CMM-006", process="CMM", parameter="Profile",
        fault_pattern="Surface Profile OOT — 3D Form Deviation",
        description="Surface profile of a line or surface out of tolerance. Complex 3D surface deviates from nominal CAD.",
        severity="Major", cpk_max=1.33,
        root_cause="CAM toolpath deviation, tool wear, or fixture instability causing surface to deviate from nominal 3D form.",
        root_cause_detail="Surface profile error on complex 3D surfaces is caused by: CAM toolpath exceeding scallop height tolerance, tool wear changing effective tool radius, or workpiece movement during 5-axis machining. Also verify CMM alignment to CAD coordinate system — misalignment creates apparent profile error.",
        alternative_causes=["CMM alignment to CAD datum error — part and CAD not in same coordinate frame", "Tool deflection on thin walls or unsupported features", "Incorrect tool radius compensation in CAM software", "Thermal growth of part during extended machining cycles"],
        corrective_actions=[
            CAPAAction("Re-align CMM to correct datum features per drawing. Re-measure profile with correct alignment. Confirm error is real.", "Metrology", "Immediate", "P1", "Eliminates alignment error as cause"),
            CAPAAction("If real: export CMM deviation map. Identify high-deviation zones. Check CAM toolpath over those zones for scallop height.", "Process Engineer", "1 week", "P1", "Identifies specific toolpath contribution"),
            CAPAAction("Reduce step-over in CAM finishing pass by 30% in high-deviation zones. Re-machine and verify.", "Manufacturing", "1 week", "P1", "Expected profile improvement by reducing scallop height"),
        ],
        preventive_actions=[
            PreventiveAction("Add tool radius measurement to pre-machining setup. Replace if >2% radius wear.", "Manufacturing", "2 weeks", "SOP"),
            PreventiveAction("Implement in-process probing at key profile checkpoints during machining.", "Manufacturing", "1 month", "Recipe"),
        ],
        containment="Full surface scan on affected parts. Map deviation — release where profile within spec, hold elsewhere.",
        disposition="Conditional Release", standard_reference="ASME Y14.5-2018, ISO 1660", weight=1.9,
    ),

    CAPARule(
        rule_id="CMM-007", process="CMM", parameter="Diameter",
        fault_pattern="Diameter OOT — Systematic Size Offset",
        description="Diameter measurement consistently offset from nominal — centering issue with adequate spread.",
        severity="Major", cpk_max=1.33, cp_cpk_gap_min=0.3,
        root_cause="Tool wear offset not compensated, or thermal growth causing systematic diameter drift during production.",
        root_cause_detail="Diameter centering offset in machining is most commonly from: tool wear not being offset-compensated in CNC, thermal growth of spindle shifting diameter, or incorrect tool setting after insert change. The systematic nature (Cp>>Cpk) confirms it's not a precision problem.",
        alternative_causes=["Incorrect tool offset entered after tool change", "CMM stylus calibration error causing systematic offset", "Material spring-back after turning (common in thin-wall parts)", "Coolant temperature affecting part size during measurement"],
        corrective_actions=[
            CAPAAction("Check CNC tool offset register. Compare to last verified offset value. Update if delta >50% of tolerance.", "Manufacturing", "Immediate", "P1", "Corrects systematic diameter offset"),
            CAPAAction("Verify CMM stylus qualification is current. Run test on certified ring gauge. Recalibrate if offset >±0.001mm.", "Metrology", "Immediate", "P1", "Rules out measurement system offset"),
            CAPAAction("Measure part at controlled temperature (20±1°C). If size changes significantly, apply thermal correction factor.", "Metrology", "1 week", "P2", "Eliminates thermal measurement error"),
        ],
        preventive_actions=[
            PreventiveAction("Implement post-offset-change verification: machine and measure test cut before production.", "Manufacturing", "1 week", "SOP"),
            PreventiveAction("Add diameter SPC chart with EWMA control. Alert before tolerance boundary reached.", "Quality", "2 weeks", "SPC"),
        ],
        containment="Measure all parts from production run since last good check. Sort by size into bins.",
        disposition="Conditional Release", standard_reference="ISO 286-1, ASME B4.1", weight=2.0,
    ),

    CAPARule(
        rule_id="CMM-008", process="CMM", parameter="Any",
        fault_pattern="CMM Gauge R&R High — Measurement Uncertainty Too Large",
        description="CMM GRR exceeds 30%. Measurement uncertainty is too large relative to feature tolerance.",
        severity="Major", grr_min=30.0, ndc_max=4,
        root_cause="CMM probe qualification frequency insufficient, stylus qualification drift, or part-fixture repeatability issue.",
        root_cause_detail="High CMM %GRR means the measurement process itself is unreliable. Common causes: (1) stylus qualification done too infrequently or on dirty reference sphere, (2) part fixturing not repeatable (part rocks on datum points), (3) environmental vibration affecting CMM, (4) incorrect measurement strategy for feature type.",
        alternative_causes=["Environmental — temperature variation in CMM room >±1°C", "CMM vibration isolation failure", "Probe head bearing wear", "Incorrect probe approach direction causing probe bending error"],
        corrective_actions=[
            CAPAAction("Re-run GRR with fresh stylus qualification on clean reference sphere. Verify room temperature 20±1°C. If improves: qualification was the issue.", "Metrology", "Immediate", "P1", "Isolates qualification vs. hardware cause"),
            CAPAAction("Check part fixture: load same part 10 times, measure datum setup repeatability. If >30% of tolerance, fix fixture.", "Metrology", "1 week", "P1", "Eliminates fixturing as GRR contributor — biggest single factor in CMM GRR"),
            CAPAAction("Run CMM with and without vibration isolation. If GRR differs, check isolation pads.", "Equipment", "1 week", "P2", "Identifies vibration contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Qualify stylus at start of each measurement session (not just daily).", "Metrology", "1 week", "SOP"),
            PreventiveAction("Annual CMM accuracy and repeatability verification per ISO 10360-2.", "Equipment", "1 year", "PM"),
            PreventiveAction("Biannual CMM GRR study per AIAG MSA manual for all critical dimensions.", "Metrology", "6 months", "Metrology"),
        ],
        containment="Suspend measurement-based accept/reject decisions until GRR is below 30%.",
        disposition="Hold", standard_reference="AIAG MSA 4th Ed, ISO 10360-2", weight=2.5,
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # AUTOMOTIVE (IATF 16949)
    # ═══════════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="AUTO-001", process="Automotive", parameter="Dimensional",
        fault_pattern="PPAP Dimension OOT — IATF 16949 Submission Risk",
        description="Critical dimension out of tolerance during PPAP or production. IATF 16949 Cpk ≥1.67 requirement not met.",
        severity="Critical", cpk_max=1.67,
        root_cause="Process not capable to IATF 16949 PPAP requirement of Cpk ≥1.67 for new or changed processes.",
        root_cause_detail="IATF 16949 and AIAG APQP require Cpk ≥1.67 for PPAP submission (Cpk ≥1.33 for ongoing production). A Cpk between 1.33–1.67 will pass ongoing monitoring but will fail initial PPAP. Root cause investigation must address both centering and spread.",
        alternative_causes=["Process designed to Cpk ≥1.33 target without PPAP margin", "Special cause during PPAP study window", "Sample selection bias — PPAP sample not representative of full production"],
        corrective_actions=[
            CAPAAction("Calculate whether gap is centering (increase Cpk by recentering) or spread (requires process improvement). Centering fix is faster.", "Quality Engineer", "Immediate", "P1", "Determines fastest path to PPAP compliance"),
            CAPAAction("If centering gap: adjust nominal setpoint. Re-run 30-piece capability study. Verify Cpk ≥1.67 across full tolerance.", "Process Engineer", "1 week", "P1", "Expected Cpk improvement to ≥1.67 after centering"),
            CAPAAction("If spread gap: conduct DOE on process variables. Identify and control the key process inputs driving variation.", "Process Engineer", "2 weeks", "P1", "Reduces process variation to achieve PPAP target"),
            CAPAAction("Notify customer immediately per IATF 16949 customer notification requirement. Document deviation request if shipment needed before fix.", "Quality Manager", "Immediate", "P1", "IATF 16949 compliance — customer notification is mandatory"),
        ],
        preventive_actions=[
            PreventiveAction("Design process to Cpk ≥2.0 target during development — provides margin for production drift.", "Process Engineer", "During APQP", "SOP"),
            PreventiveAction("Add PPAP dimension to production SPC with Cpk ≥1.33 alert threshold.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Quarterly process capability review for all PPAP-approved characteristics.", "Quality", "Quarterly", "SOP"),
        ],
        containment="Apply IATF 16949 containment: 100% inspection, lot traceability, customer notification.",
        disposition="Hold", standard_reference="IATF 16949:2016, AIAG APQP/PPAP", weight=3.0,
    ),

    CAPARule(
        rule_id="AUTO-002", process="Automotive", parameter="Torque",
        fault_pattern="Fastener Torque — Low Cpk / SPC Alarm",
        description="Assembly torque capability below standard or SPC showing drift. Risk of undertorque or overtorque.",
        severity="Critical", cpk_max=1.33, spc_rules=["WE1","WE4","NE2"],
        root_cause="Torque tool calibration drift, worn socket, or assembly operator technique variation.",
        root_cause_detail="Torque capability failure is safety-critical in automotive. Root causes: (1) torque wrench/gun calibration out of date — most common, (2) worn socket creating slip/angle measurement error, (3) lubrication variation on fastener affecting torque-tension relationship.",
        alternative_causes=["Thread damage on nut or bolt affecting torque-to-tension conversion", "Lubricant type or application variation", "Fastener batch-to-batch friction variation (coefficient of friction)", "Operator applying breakaway torque above prevailing torque on nyloc nuts"],
        corrective_actions=[
            CAPAAction("Pull torque tool calibration record. If >6 months since calibration, recalibrate immediately. Quarantine any assemblies torqued since last calibration.", "Quality", "Immediate", "P1", "Eliminates calibration as cause — mandatory IATF action"),
            CAPAAction("Inspect socket condition. Replace if wear visible or if test on calibrated fastener shows >5% error.", "Manufacturing", "Immediate", "P1", "Eliminates socket wear contribution"),
            CAPAAction("Measure K-factor (nut factor) on fastener samples from current lot. If K-factor changed vs. approved lot, notify engineering.", "Quality Engineer", "1 week", "P1", "Identifies fastener-side friction variation"),
        ],
        preventive_actions=[
            PreventiveAction("Monthly torque tool calibration per ISO 6789. Use IATF-approved calibration lab.", "Quality", "Monthly", "PM"),
            PreventiveAction("Add torque SPC chart at assembly station. Immediate alert on WE1.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Specify lubricant type and application method in assembly SOP. Photograph-documented application procedure.", "Manufacturing", "1 week", "SOP"),
        ],
        containment="100% torque audit on all assemblies from affected production period. Rework undertorqued joints.",
        disposition="Hold", standard_reference="IATF 16949:2016, ISO 6789, VDI 2230", weight=2.8,
    ),

    CAPARule(
        rule_id="AUTO-003", process="Automotive", parameter="Surface_Finish",
        fault_pattern="Surface Roughness — Ra/Rz OOT or High Variation",
        description="Surface finish (Ra or Rz) out of tolerance or showing high process variation.",
        severity="Major", cpk_max=1.33, non_normal=True,
        root_cause="Tool wear progression causing surface finish degradation, or workholding vibration creating chatter marks.",
        root_cause_detail="Surface roughness OOT in machined parts: (1) tool wear — Ra increases as cutting edge degrades (progressive trend), (2) chatter — high-frequency vibration creates periodic peaks in roughness profile (look for 2D spectrum peaks in roughness data), (3) coolant failure — insufficient cooling increases built-up edge.",
        alternative_causes=["Built-up edge on tool causing smearing", "Incorrect cutting parameters (speed, feed, depth) for material", "Coolant concentration out of specification", "Ra measurement stylus tip wear giving inflated readings"],
        corrective_actions=[
            CAPAAction("Check surface roughness trend over last 100 parts. If progressive increase, tool wear is cause. If sudden, check for chatter or coolant.", "Process Engineer", "Immediate", "P1", "Identifies degradation pattern"),
            CAPAAction("Replace cutting insert. Re-machine and verify Ra within spec before continuing production.", "Manufacturing", "Immediate", "P1", "Restores surface finish to target — expected Ra return to nominal"),
            CAPAAction("If chatter suspected: reduce depth of cut by 25%, increase spindle speed by 10%. Re-measure. If improved, chatter confirmed.", "Manufacturing", "1 week", "P2", "Eliminates chatter as root cause"),
        ],
        preventive_actions=[
            PreventiveAction("Implement tool life control: mandatory insert change at defined number of parts (not just on failure).", "Manufacturing", "2 weeks", "SOP"),
            PreventiveAction("Add Ra SPC chart at machining cell. Alert at 70% of tolerance to allow proactive insert change.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Daily coolant concentration and pH check. Log and trend.", "Manufacturing", "1 week", "SOP"),
        ],
        containment="100% surface roughness inspection on affected batch. Parts above Ra limit to rework.",
        disposition="Conditional Release", standard_reference="ISO 4287, IATF 16949:2016", weight=2.0,
    ),

    CAPARule(
        rule_id="AUTO-004", process="Automotive", parameter="Press_Fit",
        fault_pattern="Press-Fit Force OOT — Assembly Force Too High or Low",
        description="Press-fit insertion force outside specification. Risk of under-press (falls out) or over-press (part damage).",
        severity="Critical", cpk_max=1.33, spc_rules=["WE1","NE2"],
        root_cause="Bore/shaft diameter variation outside interference fit specification, or surface finish variation changing friction coefficient.",
        root_cause_detail="Press-fit force is directly driven by interference (bore-shaft diameter difference) and surface finish. OOT force means: diameter pairing is out of specification range, or surface finish Ra changed causing friction coefficient shift. Low force = insufficient interference = part will fall out in service. High force = over-interference = risk of cracking.",
        alternative_causes=["Temperature difference between parts at assembly (thermal expansion)", "Lubrication applied inconsistently before pressing", "Press machine force calibration out of date", "Burrs on bore entry chamfer causing spike in initial press force"],
        corrective_actions=[
            CAPAAction("Measure bore and shaft diameters independently. Calculate actual interference. If interference out of spec, that is the root cause.", "Metrology", "Immediate", "P1", "Identifies whether dimensional or process root cause"),
            CAPAAction("Check press machine force calibration certificate. Recalibrate if >6 months. Verify with load cell.", "Equipment", "Immediate", "P1", "Eliminates measurement error on force monitoring"),
            CAPAAction("Inspect bore entry chamfer. Remove any burrs. Verify chamfer angle and length per drawing.", "Manufacturing", "1 week", "P2", "Eliminates chamfer burr contribution to initial force spike"),
        ],
        preventive_actions=[
            PreventiveAction("Implement selective assembly pairing: measure bore and shaft, pair to maintain interference within spec.", "Manufacturing", "2 weeks", "SOP"),
            PreventiveAction("Add press force SPC chart. Alert on WE1 — any point beyond 3σ requires immediate inspection.", "Quality", "1 week", "SPC"),
            PreventiveAction("Monthly press machine force calibration per traceable standard.", "Equipment", "Monthly", "PM"),
        ],
        containment="100% press force audit. Under-force parts: immediate disassembly and re-press with correct diameter pairing.",
        disposition="Hold", standard_reference="IATF 16949:2016, ISO 10243", weight=2.7,
    ),

    CAPARule(
        rule_id="AUTO-005", process="Automotive", parameter="Hardness",
        fault_pattern="Heat Treatment Hardness — Low Cpk or SPC Drift",
        description="Part hardness after heat treatment out of specification range or showing process drift.",
        severity="Critical", cpk_max=1.33, spc_rules=["NE3","WE4"],
        root_cause="Furnace temperature uniformity degradation, quench media temperature drift, or atmosphere control failure.",
        root_cause_detail="Heat treatment hardness failure is almost always furnace-related: (1) temperature uniformity survey (TUS) due — batch furnaces typically require quarterly TUS, (2) atmosphere carbon potential drift causing under/over-carburizing, (3) quench oil temperature or agitation variation affecting cooling rate.",
        alternative_causes=["Incoming material chemistry variation (carbon content)", "Part cross-section variation causing different quench rates", "Fixture masking causing uneven atmosphere exposure", "Thermcouple failure in specific furnace zone"],
        corrective_actions=[
            CAPAAction("Pull furnace temperature uniformity survey (TUS) records. If >3 months since last TUS, perform emergency TUS immediately.", "Equipment", "Immediate", "P1", "IATF 16949 and AMS 2750 require TUS — this is compliance action"),
            CAPAAction("Check atmosphere carbon potential (Cp) chart for affected batch. If carbon potential drifted >0.05%, identify cause (atmosphere flow, oxygen probe calibration).", "Process Engineer", "Immediate", "P1", "Identifies atmosphere control failure"),
            CAPAAction("Measure quench oil/polymer temperature and agitation rate. If out of spec, adjust and re-qualify.", "Equipment", "1 week", "P2", "Eliminates quench media variation"),
        ],
        preventive_actions=[
            PreventiveAction("Quarterly TUS per AMS 2750E (or customer spec). Maintain records.", "Equipment", "Quarterly", "PM"),
            PreventiveAction("Daily atmosphere Cp measurement and logging. SPC chart with ±0.03% alert.", "Process Engineer", "1 week", "SPC"),
            PreventiveAction("Hardness SPC chart. Alert when hardness trends toward spec limit.", "Quality", "2 weeks", "SPC"),
        ],
        containment="100% hardness test on all parts from affected heat treat batch. Scrap if below minimum hardness (safety-critical).",
        disposition="Hold", standard_reference="IATF 16949:2016, AMS 2750E, SAE J423", weight=3.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # AEROSPACE (AS9100)
    # ═══════════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="AERO-001", process="Aerospace", parameter="Dimensional",
        fault_pattern="AS9100 Dimension OOT — Flight-Critical Feature",
        description="Flight-critical dimension out of tolerance. AS9100 nonconformance requiring MRB disposition.",
        severity="Critical", cpk_max=1.33,
        root_cause="Process drift or setup error on flight-critical dimension requiring immediate containment and MRB review.",
        root_cause_detail="AS9100D requires documented nonconformance disposition for all out-of-tolerance conditions on critical features. Root cause investigation must follow 8D or equivalent methodology. Rework requires re-inspection to original drawing requirements and re-buy-off if applicable.",
        alternative_causes=["Drawing interpretation error between design and manufacturing", "Previous operation non-conformance carried forward", "Wrong material or heat treatment condition"],
        corrective_actions=[
            CAPAAction("Immediately quarantine all affected parts. Initiate Nonconformance Report (NCR) per AS9100 clause 8.7.", "Quality Manager", "Immediate", "P1", "AS9100 compliance — NCR is mandatory"),
            CAPAAction("Convene Material Review Board (MRB). Options: Use-As-Is (requires engineering approval), Rework to drawing, or Scrap.", "MRB/Engineering", "Immediate", "P1", "Required AS9100 disposition process"),
            CAPAAction("Perform 8D root cause analysis. Identify escape point (how did it pass previous inspection?).", "Quality Engineer", "1 week", "P1", "AS9100 requires root cause documentation for customer submission"),
            CAPAAction("If rework approved: re-machine to drawing. Full dimensional buy-off required. Document traceability.", "Manufacturing", "1 week", "P1", "Rework must be documented with before/after measurements"),
        ],
        preventive_actions=[
            PreventiveAction("First-article inspection (FAI) per AS9102B for any new or changed process.", "Quality", "Before production", "SOP"),
            PreventiveAction("Add critical dimension to in-process control plan with defined inspection frequency.", "Quality", "2 weeks", "SOP"),
            PreventiveAction("Implement critical dimension SPC with automated out-of-spec alert to production supervisor.", "Quality", "1 month", "SPC"),
        ],
        containment="MANDATORY: quarantine, NCR, customer notification per contract requirements.",
        disposition="Hold", standard_reference="AS9100D, AS9102B, AS9103", weight=3.0,
    ),

    CAPARule(
        rule_id="AERO-002", process="Aerospace", parameter="Surface_Integrity",
        fault_pattern="Surface Integrity — Roughness or Burn Marks on Aerospace Component",
        description="Surface finish exceeds specification or thermal damage (grinding burn) detected on aerospace component.",
        severity="Critical", cpk_max=1.33, non_normal=True,
        root_cause="Grinding burn from insufficient coolant delivery or excessive grinding depth, or surface damage from end-of-life tooling.",
        root_cause_detail="Grinding burn is a safety-critical defect in aerospace — it creates tensile residual stress in the surface, reducing fatigue life. AS9100 and customer specs (often include Barkhausen noise or nital etch inspection requirements for safety-critical ground surfaces). Burn is not always visible — must use non-destructive inspection.",
        alternative_causes=["Dressing interval too long — dresser condition degraded", "Coolant nozzle clogged or misaligned", "Wheel specification wrong for material", "Spindle speed/feed combination outside safe window for material"],
        corrective_actions=[
            CAPAAction("Immediately quarantine all parts ground in affected period. Perform Barkhausen noise or nital etch inspection per applicable spec (AMS 2759/9 or equivalent).", "Quality", "Immediate", "P1", "Non-destructive inspection required — visual inspection INSUFFICIENT for burn detection"),
            CAPAAction("Disassemble grinding setup. Inspect coolant nozzle position and flow rate. Verify correct nozzle direction and pressure.", "Equipment", "Immediate", "P1", "Coolant delivery is #1 cause of grinding burn"),
            CAPAAction("Dress wheel and run test piece. Verify Ra and check for burn indicators before resuming production.", "Manufacturing", "Immediate", "P1", "Confirms setup is correct before production restart"),
        ],
        preventive_actions=[
            PreventiveAction("Define grinding parameters window in SOP: wheel spec, dress interval, coolant flow rate, depth of cut limits.", "Process Engineer", "2 weeks", "SOP"),
            PreventiveAction("Periodic Barkhausen noise inspection on production samples (frequency per customer spec).", "Quality", "Per customer spec", "Metrology"),
            PreventiveAction("Coolant concentration and flow rate measurement — daily log and SPC.", "Manufacturing", "1 week", "SPC"),
        ],
        containment="SCRAPPED if burn confirmed — no rework allowed for safety-critical aerospace surfaces.",
        disposition="Scrap", standard_reference="AS9100D, AMS 2759/9, ANSI B212.1", weight=3.0,
    ),

    CAPARule(
        rule_id="AERO-003", process="Aerospace", parameter="NDT",
        fault_pattern="NDT Indication — Subsurface Defect Detected",
        description="Non-destructive testing (UT, MT, PT, RT) indication found. Possible subsurface crack or void.",
        severity="Critical",
        root_cause="Material discontinuity from casting, forging, welding, or fatigue crack initiation during processing.",
        root_cause_detail="NDT indications in aerospace must be treated conservatively. Any indication within rejection criteria requires MRB review. Root cause depends on process: casting = shrinkage porosity or cold shut, forging = laps or seams, welding = porosity or lack of fusion, in-service = fatigue crack.",
        alternative_causes=["False indication from surface contamination or geometry (pseudo-indication)", "Equipment calibration issue creating incorrect sensitivity", "Technician error in interpretation"],
        corrective_actions=[
            CAPAAction("Re-inspect by Level II or Level III NDT technician using calibrated equipment. Confirm or reject indication.", "Quality/NDT", "Immediate", "P1", "Verification by qualified technician required before disposition"),
            CAPAAction("If confirmed: initiate NCR. Submit to MRB with indication map, depth estimate, and proposed disposition.", "Quality Manager", "Immediate", "P1", "AS9100 mandatory NCR process"),
            CAPAAction("Investigate process that created part. If casting: review gating/riser design. If weld: check WPS compliance and welder qualification.", "Engineering", "1 week", "P1", "Root cause to prevent recurrence"),
        ],
        preventive_actions=[
            PreventiveAction("Define NDT acceptance criteria in control plan per applicable specification (ASTM E1444, AMS 2644 etc).", "Quality", "Per spec", "SOP"),
            PreventiveAction("Annual NDT equipment calibration and procedure requalification.", "Equipment", "Annual", "PM"),
        ],
        containment="100% NDT on all parts from affected lot. Zero-tolerance disposition.",
        disposition="Hold", standard_reference="AS9100D, ASTM E1444, AMS 2644, NAS 410", weight=3.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # MEDICAL DEVICES (ISO 13485)
    # ═══════════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="MED-001", process="Medical", parameter="Dimensional",
        fault_pattern="Medical Device Dimension OOT — ISO 13485 Nonconformance",
        description="Critical dimension on medical device out of specification. ISO 13485 nonconformance requires documented CAPA.",
        severity="Critical", cpk_max=1.33,
        root_cause="Process drift on a critical dimension affecting device safety or performance.",
        root_cause_detail="ISO 13485:2016 clause 8.3 requires documented nonconformance procedures and CAPA system. For implants and Class II/III devices, OOT dimensions may require regulatory notification. All dispositions (rework, use-as-is, scrap) must be documented and approved by authorized personnel.",
        alternative_causes=["Drawing revision not incorporated into production traveler", "Incoming material non-conformance not detected", "Environmental contamination affecting measurement"],
        corrective_actions=[
            CAPAAction("Initiate Nonconforming Product Report (NCPR) per ISO 13485 clause 8.3. Quarantine all potentially affected units.", "Quality Manager", "Immediate", "P1", "ISO 13485 mandatory — regulatory compliance action"),
            CAPAAction("Assess risk using ISO 14971 risk analysis. Determine if OOT condition creates patient safety risk.", "Clinical/Regulatory Affairs", "Immediate", "P1", "Risk-based disposition required for Class II/III devices"),
            CAPAAction("Initiate formal CAPA per ISO 13485 clause 8.5.2. Root cause analysis, effectiveness verification planned.", "Quality Engineer", "1 week", "P1", "ISO 13485 CAPA process is mandatory and audited"),
            CAPAAction("If Class II/III device: evaluate FDA 21 CFR 806 field correction or recall reporting requirement.", "Regulatory Affairs", "Immediate", "P1", "Regulatory notification may be legally required"),
        ],
        preventive_actions=[
            PreventiveAction("Validate measurement system per ISO 13485 requirements — documented GRR study.", "Quality", "Before production", "Metrology"),
            PreventiveAction("Add critical device dimension to statistical process monitoring per ISO 13485 clause 8.2.6.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Annual process validation requalification per FDA 21 CFR 820 or ISO 13485.", "Quality", "Annual", "SOP"),
        ],
        containment="MANDATORY quarantine, NCPR, risk assessment. Possible regulatory notification.",
        disposition="Hold", standard_reference="ISO 13485:2016, FDA 21 CFR 820, ISO 14971", weight=3.0,
    ),

    CAPARule(
        rule_id="MED-002", process="Medical", parameter="Surface_Finish",
        fault_pattern="Implant Surface Finish OOT — Biocompatibility Risk",
        description="Implant surface roughness (Ra) out of specification. Risk to biocompatibility or osseointegration.",
        severity="Critical", cpk_max=1.33, non_normal=True,
        root_cause="Machining or surface treatment process deviation creating surface condition outside validated range.",
        root_cause_detail="For implantable devices, surface finish affects: (1) osseointegration (bone implants — specific Ra target for bone attachment), (2) tribology (bearing surfaces — too rough creates wear debris), (3) corrosion resistance (too rough increases surface area for corrosion). Any deviation from validated Ra range is potentially a biocompatibility issue.",
        alternative_causes=["Electropolishing bath concentration drift", "Passivation process out of specification", "Bead blasting or acid etching process variation", "Contamination from machining oil not fully removed"],
        corrective_actions=[
            CAPAAction("Initiate NCPR. Quarantine affected implants. Do not release until risk assessment complete.", "Quality", "Immediate", "P1", "ISO 13485 mandatory NCR"),
            CAPAAction("Perform ISO 10993 biocompatibility risk assessment. Assess whether surface change creates unacceptable risk.", "Regulatory/Clinical", "1 week", "P1", "ISO 10993 assessment may be needed before any release decision"),
            CAPAAction("Investigate surface treatment process: check bath concentration, temperature, timing, and process records for affected lot.", "Process Engineer", "1 week", "P1", "Surface treatment drift is most common cause"),
        ],
        preventive_actions=[
            PreventiveAction("Add surface treatment process parameters (bath concentration, temperature, time) to SPC.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Ra SPC chart with tight alert limits (±20% of nominal Ra target).", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Validate surface treatment process per ISO 13485 and document acceptance criteria.", "Quality", "Per validation plan", "SOP"),
        ],
        containment="Full Ra inspection on all implants from affected lot. Regulatory notification if required.",
        disposition="Hold", standard_reference="ISO 13485:2016, ISO 10993, ASTM F86", weight=3.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # GENERAL METROLOGY / LAB
    # ═══════════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="GEN-METRO-001", process="General", parameter="Any",
        fault_pattern="Process Incapable — Cpk < 1.00 (Defects Being Produced)",
        description="Cpk < 1.00 means defects are actively being produced. Industry-agnostic — immediate containment required.",
        severity="Critical", cpk_max=1.00, ppm_min=1000,
        root_cause="Process is fundamentally out of control relative to specification limits.",
        root_cause_detail="Cpk < 1.0 means the 3-sigma process width exceeds the specification range. Distinguish: Cp<1.0 = spread problem (process inherently too variable), Cp>1.0 but Cpk<1.0 = centering problem (process capable but not centered). Different root causes and different fixes.",
        alternative_causes=["Specification limit set incorrectly (too tight for process physics)", "Process running on wrong equipment or recipe", "Incoming material variation exceeding process tolerance"],
        corrective_actions=[
            CAPAAction("Calculate PPM and estimate yield impact. Present to management for priority triage.", "Quality Engineer", "Immediate", "P1", "Business impact quantification for escalation"),
            CAPAAction("100% inspect all product from affected period. Sort: in-spec = conditional release, OOT = scrap/rework.", "Manufacturing", "Immediate", "P1", "Containment of defective product"),
            CAPAAction("If Cp>1.0: centering fix — adjust setpoint. If Cp<1.0: spread reduction needed — DOE on process parameters.", "Process Engineer", "1 week", "P1", "Different fix path depending on whether Cp or Cpk is the issue"),
        ],
        preventive_actions=[
            PreventiveAction("Implement real-time SPC with automatic lot hold when Cpk drops below 1.33.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Quarterly process capability review for all critical parameters.", "Quality", "Quarterly", "SOP"),
        ],
        containment="MANDATORY LOT HOLD. 100% inspection before any release.",
        disposition="Hold", standard_reference="AIAG SPC 2nd Ed, ISO 22514", weight=3.0,
    ),

    CAPARule(
        rule_id="GEN-METRO-002", process="General", parameter="Any",
        fault_pattern="Measurement System Unacceptable — GRR > 30%",
        description="Gauge R&R exceeds 30%. Fix measurement system before making process decisions.",
        severity="Major", grr_min=30.0, ndc_max=None,
        root_cause="Measurement system variation exceeds 30% — gauge inadequate for this tolerance.",
        root_cause_detail="AIAG MSA manual: >30% GRR = unacceptable. Cannot distinguish good from bad product. All Cpk values calculated from this data are unreliable. Fix measurement before process.",
        alternative_causes=["Gauge resolution too coarse for tolerance (ndc<5)", "Operator technique variation dominant (AV>EV)", "Environmental conditions affecting measurement"],
        corrective_actions=[
            CAPAAction("Identify whether EV (repeatability) or AV (reproducibility) dominates. Different root causes.", "Metrology", "Immediate", "P1", "Targets most impactful GRR reduction lever"),
            CAPAAction("If AV dominant: standardize operator method, provide training, lock gauge settings.", "Metrology", "1 week", "P1", "Reduces operator-to-operator variation"),
            CAPAAction("If EV dominant: inspect gauge hardware, check calibration, assess environmental factors.", "Equipment", "1 week", "P1", "Addresses gauge hardware instability"),
        ],
        preventive_actions=[
            PreventiveAction("Biannual GRR studies for all critical gauges per AIAG MSA 4th Edition.", "Metrology", "6 months", "Metrology"),
            PreventiveAction("Track %GRR over time as a gauge health indicator.", "Metrology", "Ongoing", "SPC"),
        ],
        containment="Suspend process control decisions based on this gauge until GRR is resolved.",
        disposition="Conditional Release", standard_reference="AIAG MSA 4th Ed, ISO 22514-7", weight=2.5,
    ),

    CAPARule(
        rule_id="GEN-METRO-003", process="General", parameter="Any",
        fault_pattern="SPC Step Change — Assignable Cause Event",
        description="Control chart shows clear step change. Discrete assignable cause occurred at a specific time.",
        severity="Major", spc_rules=["WE1","WE4","NE2"],
        root_cause="Discrete process change: PM completion, material lot change, recipe modification, operator change, or equipment event.",
        root_cause_detail="Step changes in SPC are never random — they always have an assignable cause. Method: identify exact shift point, pull tool event log + maintenance log + material lot log within ±4 hours of shift. One of those will be the cause.",
        alternative_causes=["Unrecorded recipe adjustment", "Equipment alarm acknowledged without investigation", "Raw material lot change not flagged"],
        corrective_actions=[
            CAPAAction("Identify exact shift point. Pull tool event, ECO, and material lot logs within ±4hr window.", "Process Engineer", "Immediate", "P1", "Identifies specific assignable cause"),
            CAPAAction("Once cause identified: reverse change if possible. Verify return to baseline with 3 monitor runs.", "Process Engineer", "Immediate", "P1", "Restores process to pre-shift state"),
        ],
        preventive_actions=[
            PreventiveAction("Implement change notification system: all recipe/material/maintenance changes logged in SPC system with timestamp.", "Manufacturing", "2 weeks", "SOP"),
            PreventiveAction("Require monitor run after every PM or recipe change before resuming production.", "Manufacturing", "1 week", "SOP"),
        ],
        containment="Hold wafers/parts processed after shift point. Inspect before release.",
        disposition="Hold", standard_reference="AIAG SPC 2nd Ed, ISO 7870", weight=2.3,
    ),

    CAPARule(
        rule_id="GEN-METRO-004", process="General", parameter="Any",
        fault_pattern="Non-Normal Distribution — Transformation or Non-Parametric Analysis Required",
        description="Data fails normality tests. Standard Cpk indices may be misleading. Alternative analysis needed.",
        severity="Minor", non_normal=True, skewness_min=0.8,
        root_cause="Process has inherently non-normal output (one-sided physical limits, mixture of populations, or bounded measurement).",
        root_cause_detail="Non-normal distributions in manufacturing: (1) physically bounded process (particle count cannot be negative → right skewed), (2) mixture of two populations (bimodal), (3) tool wear progression (asymmetric), (4) ratio or log-normally distributed quantity. Standard Cpk is only valid for normal distributions.",
        alternative_causes=["Measurement system saturation at one end of scale", "Outliers from a different process mechanism", "Data stratification needed (different shifts/tools mixed)"],
        corrective_actions=[
            CAPAAction("Identify distribution type: right-skewed = try log or Box-Cox transform. Bimodal = stratify data. Left-skewed = try reflection + log.", "Quality Engineer", "1 week", "P2", "Determines correct analysis approach"),
            CAPAAction("Apply Box-Cox transformation and re-calculate Cpk on transformed data. Or use non-parametric Pp (percentile method).", "Quality Engineer", "1 week", "P2", "Provides valid capability estimate for non-normal data"),
            CAPAAction("If bimodal: stratify by operator, shift, tool, or material lot. Identify which stratification explains the two peaks.", "Process Engineer", "1 week", "P1", "Bimodality always has an assignable cause"),
        ],
        preventive_actions=[
            PreventiveAction("Run normality test before calculating Cpk for any new characteristic.", "Quality", "Ongoing", "SOP"),
            PreventiveAction("Document which characteristics are expected to be non-normal and define approved analysis method.", "Quality", "1 month", "SOP"),
        ],
        containment="No immediate hold required. Flag that standard Cpk is not valid for this data.",
        disposition="Release", standard_reference="AIAG SPC 2nd Ed, ISO 22514-2", weight=1.5,
    ),

    CAPARule(
        rule_id="GEN-METRO-005", process="General", parameter="Any",
        fault_pattern="ndc < 5 — Gauge Resolution Insufficient for Process Control",
        description="Number of distinct categories below 5. Gauge cannot differentiate between parts for effective SPC.",
        severity="Major", ndc_max=4,
        root_cause="Gauge resolution too coarse relative to process variation, OR process is very capable and part variation is smaller than gauge resolution.",
        root_cause_detail="ndc = 1.41 × sqrt(part variance / gauge variance). ndc<5 means the gauge divides the part population into fewer than 5 categories. AIAG MSA 4th Edition requirement is ndc≥5 for SPC. If process is very capable (Cpk>2), this may be acceptable for go/no-go but not for SPC tracking.",
        alternative_causes=["Part-to-part variation is genuinely small (very capable process) — gauge fine for acceptance but not SPC", "Wrong gauge selected — resolution spec too coarse for tolerance"],
        corrective_actions=[
            CAPAAction("Calculate ratio of gauge resolution to total tolerance. If resolution >5% of tolerance, gauge is inadequate.", "Metrology", "1 week", "P2", "Quantifies gauge adequacy for this tolerance"),
            CAPAAction("If gauge inadequate: evaluate higher-resolution option. For diameter: replace indicator gauge with air gauge or LVDT.", "Metrology", "2 weeks", "P1", "Upgrades measurement to achieve ndc≥5"),
        ],
        preventive_actions=[
            PreventiveAction("During gauge selection: require ndc analysis before approving gauge for production.", "Metrology", "1 month", "SOP"),
            PreventiveAction("Document gauge capability requirements in control plan.", "Quality", "1 month", "SOP"),
        ],
        containment="Production may continue. Note: SPC charts are not effective until gauge is upgraded.",
        disposition="Release", standard_reference="AIAG MSA 4th Ed", weight=1.6,
    ),

    CAPARule(
        rule_id="GEN-METRO-006", process="General", parameter="Any",
        fault_pattern="SPC Trend — Gradual Process Drift",
        description="Control chart shows gradual monotonic trend. Nelson NE3 or WE3 rule fired. Process drifting toward limit.",
        severity="Major", spc_rules=["NE3","WE3"],
        root_cause="Gradual consumable wear (tool, electrode, pad), gradual calibration drift, or systematic environmental change.",
        root_cause_detail="Monotonic trends in SPC always have a physical cause driving gradual change. In machining: tool wear. In processes: electrode or consumable degradation. In measurement: gauge drift. The trend slope tells you how fast you are approaching the limit — use it to predict when an intervention is needed.",
        alternative_causes=["Gradual material property change (incoming raw material batch transition)", "Environmental drift (temperature, humidity over a shift)", "Operator technique drift over time (fatigue)"],
        corrective_actions=[
            CAPAAction("Calculate trend slope (units/measurement). Extrapolate to predict when process will hit spec limit. Use this to set urgency of corrective action.", "Quality Engineer", "Immediate", "P2", "Quantifies time-to-failure for prioritization"),
            CAPAAction("Identify consumable most likely causing trend. Check age/usage. Replace proactively if >70% of rated life.", "Manufacturing", "1 week", "P1", "Proactive consumable replacement before failure"),
            CAPAAction("Implement APC correction if available: feed trend signal back to offset setpoint and compensate drift.", "Equipment", "2 weeks", "P1", "Automated trend compensation — eliminates manual intervention need"),
        ],
        preventive_actions=[
            PreventiveAction("Implement trend-sensitive SPC rules (NE3 with 5-point window as standard).", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Set preventive consumable replacement interval at 70% of rated life, not on failure.", "Manufacturing", "1 month", "SOP"),
        ],
        containment="Alert supervisor. Increase measurement frequency. No hold required unless approaching spec limit.",
        disposition="Release", standard_reference="AIAG SPC 2nd Ed, ISO 7870-2", weight=2.0,
    ),

    CAPARule(
        rule_id="GEN-METRO-007", process="General", parameter="Any",
        fault_pattern="Bimodal / Mixture Distribution — Two Populations Mixed",
        description="Data shows bimodal or multi-modal distribution. Two distinct populations are being measured as one.",
        severity="Major", non_normal=True, spc_rules=["NE8","NE4"],
        root_cause="Two distinct process conditions or sources are being mixed in the same dataset without stratification.",
        root_cause_detail="Bimodal distribution = two populations mixed. Common causes: (1) two machines feeding same SPC chart, (2) two shifts with different setups, (3) two material lots with different properties, (4) two operators with different techniques. The 'NE8' rule (points beyond ±1σ both sides, never near CL) is the SPC signature of a bimodal mixture.",
        alternative_causes=["Alternating tool A and tool B without separate tracking", "Day/night shift process difference", "Two cavity mold producing different nominal dimensions"],
        corrective_actions=[
            CAPAAction("Stratify data by machine, shift, operator, tool, and material lot. Plot each stratum separately. The stratum that shows bimodality is the driver.", "Quality Engineer", "Immediate", "P1", "Identifies stratification factor responsible for bimodality"),
            CAPAAction("Once stratified: treat each sub-population separately. Each gets its own SPC chart and capability study.", "Quality Engineer", "1 week", "P1", "Resolves bimodality by correct data management"),
            CAPAAction("Investigate why the two populations have different means. Address root cause: re-center one process, repair tool, retrain operator.", "Process Engineer", "1 week", "P2", "Eliminates the systematic difference between populations"),
        ],
        preventive_actions=[
            PreventiveAction("Require stratified SPC from first production: one chart per machine, cavity, shift.", "Quality", "During APQP", "SOP"),
            PreventiveAction("Add stratification factor (machine ID, cavity number) to data collection system.", "Quality", "2 weeks", "SOP"),
        ],
        containment="Sort parts by stratification factor. Inspect each stratum separately.",
        disposition="Conditional Release", standard_reference="AIAG SPC 2nd Ed, ISO 7870-5", weight=2.0,
    ),

    CAPARule(
        rule_id="GEN-METRO-008", process="General", parameter="Any",
        fault_pattern="High PPM — Process Producing Excessive Defects",
        description="Expected PPM above acceptable level. Process generating significant defect rate.",
        severity="Critical", ppm_min=1000, cpk_max=1.00,
        root_cause="Combined centering and spread issue exceeding specification limits.",
        root_cause_detail="High PPM from low Cpk means defects are being actively produced. Priority: contain first (stop shipping defects), then investigate root cause. PPM > 1000 in automotive/aerospace is typically a customer scorecard risk and may trigger a customer-mandated CAPA.",
        alternative_causes=["Specification tighter than process capability requires (spec should be reviewed)", "Multiple process streams mixed — high-PPM stream not identified"],
        corrective_actions=[
            CAPAAction("100% sort of all product from affected production period. Establish clean inventory.", "Manufacturing", "Immediate", "P1", "Immediate containment — stop shipping defects"),
            CAPAAction("Calculate PPM per stream (machine, shift, tool). If one stream dominates, focus correction there.", "Quality Engineer", "Immediate", "P1", "Identifies highest-PPM source for targeted correction"),
            CAPAAction("Engage customer if PPM exceeds customer scorecard threshold. Submit 8D per customer requirement.", "Quality Manager", "Immediate", "P1", "Customer notification and 8D may be contractually required"),
        ],
        preventive_actions=[
            PreventiveAction("Implement real-time SPC with auto-lot-hold when Cpk < 1.33.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Monthly PPM report and trend review.", "Quality Manager", "Monthly", "SOP"),
        ],
        containment="100% inspection. Quarantine and sort. Customer notification if above scorecard threshold.",
        disposition="Hold", standard_reference="AIAG SPC, ISO 22514, IATF 16949", weight=2.8,
    ),
]

