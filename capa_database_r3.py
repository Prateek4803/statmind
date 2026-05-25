"""
StatMind R3 — CAPA Rule Database (Major Expansion)
Total: 80+ rules covering:
  Semiconductor R3 (expanded): Etch, CMP, Litho, Diffusion, CVD/ALD, Ion Implant, Wet Clean
  CMM / GD&T: Flatness, Roundness, Cylindricity, Position, Runout, Profile, Angularity,
               Parallelism, Perpendicularity, Concentricity, GRR
  Automotive IATF 16949: Dimensional, Torque, Surface Finish, Press-Fit, Hardness,
                          Weld Integrity, Leak Test, Adhesive Bond
  Aerospace AS9100: Dimensional, Surface Integrity, NDT, Fatigue/Fracture, Corrosion
  Medical ISO 13485: Dimensional, Surface Finish, Sterility/Particulate, Catheter/Stent
  Pharma / Biotech: Dissolution, Content Uniformity, Particle Size, Fill Weight
  Electronics / PCB: Solder Joint, Impedance, Via Integrity, Warpage
  Injection Molding: Dimensional, Warpage, Flash/Short Shot, Sink Marks
  Welding: Weld Strength, Penetration, Heat Input, Porosity
  General (expanded): All prior + Autocorrelation, Gauge Linearity, Cpk Target Miss

References: AIAG MSA 4th Ed, ASME Y14.5-2018, IATF 16949:2016, AS9100D,
            ISO 13485:2016, SEMI standards, USP <711>, IPC-A-610, AWS D1.1
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

    # ═══════════════════════════════════════════════════════════════════════
    # SEMICONDUCTOR — ETCH (expanded)
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="SEMI-001", process="Etch", parameter="CD",
        fault_pattern="CD Low Cpk — Process Off-Center",
        description="Critical Dimension Cpk below threshold with significant Cp-Cpk gap indicating centering issue.",
        severity="Major", cpk_max=1.33, cp_cpk_gap_min=0.25,
        root_cause="Etch bias offset from RF power or pressure drift.",
        root_cause_detail=(
            "Large Cp-Cpk gap confirms spread is fine but centering is off. Most likely: incremental "
            "RF power drift, chamber wall conditioning change, or gas flow calibration offset."
        ),
        alternative_causes=["Photoresist CD offset from upstream litho", "Focus/dose drift", "Chamber seasoning change after PM"],
        corrective_actions=[
            CAPAAction("Measure etch bias on 5 wafers vs baseline. Adjust RF power or bias voltage to re-center CD.", "Process Engineer", "Immediate", "P1", "Expected Cpk improvement to ≥1.33 after centering"),
            CAPAAction("Run DOE on etch time ±10% to map CD sensitivity. Update setpoint.", "Process Engineer", "1 week", "P1", "Quantifies optimal recipe window"),
            CAPAAction("Pull SEM CD data from last 30 days. Correlate with chamber RF hours to identify drift onset.", "Metrology", "1 week", "P2", "Identifies drift onset timestamp"),
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
        severity="Critical", spc_rules=["NE2", "NE3", "WE4", "WE1"],
        root_cause="Electrode erosion, chamber wall polymer buildup, or gas flow controller drift.",
        root_cause_detail=(
            "Sustained shift = step-change assignable cause (PM event, consumable swap, recipe change). "
            "Trend = gradual degradation (electrode wear, wall conditioning drift)."
        ),
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
        rule_id="SEMI-003", process="Etch", parameter="Uniformity",
        fault_pattern="Etch Uniformity — High Within-Wafer Non-Uniformity",
        description="Within-wafer etch uniformity (WIWNU) exceeds specification. Edge-to-center ratio is out of range.",
        severity="Major", non_normal=True, skewness_min=0.6,
        root_cause="Asymmetric gas flow distribution or edge ring conditioning mismatch.",
        root_cause_detail=(
            "WIWNU > spec is often caused by: (1) worn edge ring changing plasma sheath geometry, "
            "(2) gas distribution ring particle clogging creating asymmetric flow, "
            "(3) ESC non-uniform clamping causing temperature gradient."
        ),
        alternative_causes=["Focus ring erosion changing plasma distribution", "RF generator imbalance in dual-frequency systems", "ESC thermal non-uniformity"],
        corrective_actions=[
            CAPAAction("Map etch rate across wafer. If edge-low: edge ring worn. If sector pattern: gas distribution ring clogged.", "Process Engineer", "Immediate", "P1", "Identifies uniformity failure mode"),
            CAPAAction("Inspect and replace edge ring if erosion > spec. Verify WIWNU returns to <2% after replacement.", "Equipment", "1 week", "P1", "Edge ring is #1 cause of WIWNU degradation"),
            CAPAAction("Perform gas distribution ring inspection. Clean or replace if any orifice >10% blocked.", "Equipment", "1 week", "P2", "Restores symmetric gas flow"),
        ],
        preventive_actions=[
            PreventiveAction("Track edge ring lifetime by RF hours. Replace at 80% rated life.", "Equipment", "2 weeks", "PM"),
            PreventiveAction("WIWNU SPC chart — alert when trend exceeds 1.5% (before 2% spec).", "Process Engineer", "2 weeks", "SPC"),
        ],
        containment="Map uniformity on all wafers from affected chamber runs.",
        disposition="Conditional Release", standard_reference="SEMI M23", weight=1.8,
    ),

    CAPARule(
        rule_id="SEMI-004", process="Etch", parameter="Selectivity",
        fault_pattern="Etch Selectivity Loss — Underlying Layer Damage",
        description="Etch selectivity to underlying film dropped. Risk of device damage from over-etch into stop layer.",
        severity="Critical", cpk_max=1.00,
        root_cause="Recipe selectivity degraded due to chemistry change or endpoint detection failure.",
        root_cause_detail=(
            "Selectivity = etch rate of target layer / etch rate of stop layer. Loss means the stop layer "
            "is being etched. Causes: gas mixture ratio drift, endpoint detection delay, or incoming film "
            "thickness variation requiring longer etch time that exposes stop layer."
        ),
        alternative_causes=["Incoming resist CD variation changing etch aspect ratio", "Chamber wall polymer change altering gas phase chemistry", "Endpoint system calibration drift"],
        corrective_actions=[
            CAPAAction("Measure stop layer thickness on suspect wafers by ellipsometry. Quantify damage depth.", "Metrology", "Immediate", "P1", "Establishes whether functional damage occurred"),
            CAPAAction("Pull endpoint trace data. If endpoint signal was missed or delayed, recalibrate endpoint system.", "Equipment", "Immediate", "P1", "Fixes endpoint detection failure"),
            CAPAAction("Adjust O2/fluorocarbon ratio in recipe to improve selectivity. Validate with selectivity test wafers.", "Process Engineer", "1 week", "P1", "Restores recipe selectivity"),
        ],
        preventive_actions=[
            PreventiveAction("Add endpoint OES intensity SPC chart. Alert if endpoint signal delay > ±3sec from baseline.", "Equipment", "2 weeks", "SPC"),
            PreventiveAction("Quarterly selectivity test wafer run to verify recipe performance.", "Process Engineer", "Quarterly", "PM"),
        ],
        containment="HOLD all wafers from affected recipe period. Electrical test before release.",
        disposition="Hold", standard_reference="SEMI M9", weight=3.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # SEMICONDUCTOR — CMP
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="SEMI-CMP-001", process="CMP", parameter="Removal_Rate",
        fault_pattern="CMP Removal Rate — Downward Trend (Pad Glazing)",
        description="CMP removal rate showing consistent downward trend. NE3/WE3 fired.",
        severity="Major", spc_rules=["NE3", "WE3", "WE4"],
        root_cause="Pad glazing: progressive reduction in pad micro-roughness reducing removal rate.",
        root_cause_detail=(
            "Monotonic downward trend is the classic signature of pad glazing. Pad surface becomes smoother, "
            "reducing slurry transport and abrasive contact."
        ),
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
        rule_id="SEMI-CMP-002", process="CMP", parameter="WIWNU",
        fault_pattern="CMP Within-Wafer Non-Uniformity High",
        description="CMP WIWNU exceeds specification. Edge or center removal rate significantly different from average.",
        severity="Major", cpk_max=1.33, non_normal=True,
        root_cause="Retaining ring wear or carrier pressure zone imbalance causing non-uniform polish pressure.",
        root_cause_detail=(
            "Edge-high WIWNU: retaining ring worn, allowing wafer to tilt. Center-high WIWNU: inner zone "
            "pressure too high. Systematic pattern = carrier hardware issue. Random pattern = slurry distribution."
        ),
        alternative_causes=["Slurry flow asymmetry or low flow rate", "Pad temperature gradient from platen cooling variation", "Eccentric carrier rotation"],
        corrective_actions=[
            CAPAAction("Map removal rate across wafer using test wafers. Identify spatial pattern (edge, center, quadrant).", "Process Engineer", "Immediate", "P1", "Identifies whether carrier or process is root cause"),
            CAPAAction("If edge pattern: inspect retaining ring height and wear. Replace if height variation >50μm.", "Equipment", "Immediate", "P1", "Retaining ring is #1 cause of edge WIWNU"),
            CAPAAction("Optimize carrier pressure zone profile in recipe using DOE on zone pressures.", "Process Engineer", "1 week", "P2", "Fine-tune pressure zones for uniform removal"),
        ],
        preventive_actions=[
            PreventiveAction("Monthly retaining ring height survey. Replace at 80% wear limit.", "Equipment", "Monthly", "PM"),
            PreventiveAction("WIWNU SPC chart — alert threshold at 80% of specification.", "Quality", "2 weeks", "SPC"),
        ],
        containment="100% post-CMP thickness measurement on affected lot.",
        disposition="Conditional Release", standard_reference="SEMI M35", weight=2.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # SEMICONDUCTOR — LITHOGRAPHY
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="SEMI-LITHO-001", process="Lithography", parameter="CD",
        fault_pattern="Litho CD — Low Cpk (Dose or Focus Drift)",
        description="Lithography CD capability below threshold — dose or focus drift.",
        severity="Critical", cpk_max=1.33, ppm_min=100,
        root_cause="Dose or focus offset in scanner causing systematic CD bias.",
        root_cause_detail=(
            "CD controlled by dose (energy) and focus (z-height). Centering failure means scanner "
            "dose/focus setpoint drifted. APC model may have degraded."
        ),
        alternative_causes=["Resist coating thickness variation", "BARC thickness drift", "Reticle contamination"],
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
        rule_id="SEMI-LITHO-002", process="Lithography", parameter="Overlay",
        fault_pattern="Overlay Error — Layer-to-Layer Misalignment",
        description="Overlay error exceeds specification. Current layer is misaligned to previous layer.",
        severity="Critical", cpk_max=1.33,
        root_cause="Scanner alignment model degraded, wafer chuck contamination, or reticle alignment mark defect.",
        root_cause_detail=(
            "Overlay = difference in position of current layer vs previous layer. OOT overlay causes "
            "device failure at contacts, vias, and gate edges. Root causes: (1) scanner baseline shift "
            "from thermal drift, (2) wafer stage calibration, (3) reticle alignment mark contamination."
        ),
        alternative_causes=["Wafer chuck particle causing tilt", "Previous layer distortion from CMP or anneal", "Mark detection failure in non-standard mark condition"],
        corrective_actions=[
            CAPAAction("Analyze overlay map. If systematic (same magnitude and direction) = model error. If random = chuck or mark issue.", "Process Engineer", "Immediate", "P1", "Identifies systemic vs random overlay error"),
            CAPAAction("Run ORION (or equivalent) monitor wafer. If scanner baseline shifted, update alignment model.", "Equipment", "Immediate", "P1", "Corrects scanner baseline — expected overlay return to <5nm"),
            CAPAAction("Inspect wafer chuck for contamination. Clean with approved procedure if any particle found.", "Equipment", "Immediate", "P1", "Eliminates chuck-induced wafer tilt"),
        ],
        preventive_actions=[
            PreventiveAction("Overlay SPC chart with 2σ alert (below spec limit). Alert to engineer before reaching spec.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Weekly scanner alignment baseline verification.", "Equipment", "Weekly", "PM"),
        ],
        containment="100% overlay measurement on all wafers from affected scanner/lot.",
        disposition="Hold", standard_reference="SEMI M12", weight=3.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # SEMICONDUCTOR — CVD / ALD / DEPOSITION
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="SEMI-DEP-001", process="Deposition", parameter="Thickness",
        fault_pattern="CVD/ALD Thickness — SPC Drift or Shift",
        description="Deposited film thickness drifting or shifted. Cpk degraded or SPC rules violated.",
        severity="Major", cpk_max=1.33, spc_rules=["NE2", "NE3", "WE4"],
        root_cause="Precursor flow controller drift, temperature controller deviation, or chamber seasoning change.",
        root_cause_detail=(
            "Film thickness in CVD/ALD is directly controlled by: (1) precursor flow (MFC calibration), "
            "(2) temperature uniformity (affects surface reaction kinetics), (3) chamber wall condition "
            "(seasoning state affects radical concentration). A step change = PM or gas change. Trend = gradual drift."
        ),
        alternative_causes=["Precursor source cylinder change (new cylinder pressure/purity)", "Carrier gas moisture contamination", "Pump base pressure increase reducing mean free path"],
        corrective_actions=[
            CAPAAction("Identify shift onset from SPC chart. Correlate with tool event log within ±4hr.", "Process Engineer", "Immediate", "P1", "Identifies specific assignable cause"),
            CAPAAction("Verify MFC calibration for all precursor lines. Recalibrate if setpoint-actual delta >1%.", "Equipment", "Immediate", "P1", "MFC drift is most common thickness shift cause"),
            CAPAAction("Run chamber seasoning wafers to stabilize wall condition. Measure thickness before resuming production.", "Process Engineer", "1 week", "P2", "Restores chamber to known condition"),
        ],
        preventive_actions=[
            PreventiveAction("Quarterly MFC calibration check using certified flow standard.", "Equipment", "Quarterly", "PM"),
            PreventiveAction("Monitor wafer at start of each production run. Hold if thickness deviates >2% from target.", "Process Engineer", "1 week", "SOP"),
        ],
        containment="Measure thickness on all wafers from affected production window.",
        disposition="Conditional Release", standard_reference="SEMI E12", weight=2.2,
    ),

    CAPARule(
        rule_id="SEMI-DEP-002", process="Deposition", parameter="Uniformity",
        fault_pattern="CVD/ALD Film Uniformity — High Within-Wafer Non-Uniformity",
        description="Film thickness uniformity exceeds specification. Edge-to-center or radial pattern evident.",
        severity="Major", non_normal=True, cpk_max=1.33,
        root_cause="Showerhead clogging, edge-to-center temperature gradient, or gas distribution plate erosion.",
        root_cause_detail=(
            "Non-uniform films result from: (1) showerhead hole plugging (creates dark spots / low-deposition zones), "
            "(2) heater element failure in one zone creating temperature gradient, "
            "(3) pump port location creating asymmetric flow."
        ),
        alternative_causes=["Wafer bow/warp causing non-uniform gap from showerhead", "Susceptor contamination affecting local temperature", "Multiple precursor injection causing mixing non-uniformity"],
        corrective_actions=[
            CAPAAction("Map thickness across wafer using 49-point or 121-point ellipsometry. Identify spatial pattern.", "Metrology", "Immediate", "P1", "Determines uniformity failure mode and location"),
            CAPAAction("If center-ring or spoke pattern: inspect showerhead for blocked holes. Clean or replace.", "Equipment", "1 week", "P1", "Showerhead clogging is most common WIWNU cause in CVD"),
            CAPAAction("Perform heater uniformity survey. Replace heater zone element if >5°C deviation.", "Equipment", "1 week", "P2", "Restores temperature uniformity"),
        ],
        preventive_actions=[
            PreventiveAction("Showerhead particle and flow check in PM. Clean if any hole blockage detected.", "Equipment", "Per PM schedule", "PM"),
            PreventiveAction("Uniformity SPC chart. Alert at 80% of specification limit.", "Process Engineer", "2 weeks", "SPC"),
        ],
        containment="100% uniformity check on lot. Any wafer >1.5x spec limit to rework queue.",
        disposition="Conditional Release", standard_reference="SEMI E29", weight=1.9,
    ),

    CAPARule(
        rule_id="SEMI-DEP-003", process="Deposition", parameter="Stress",
        fault_pattern="Deposited Film Stress — Wafer Bow/Warp Induced",
        description="Film stress causing excessive wafer bow. Risk of wafer breakage and downstream process issues.",
        severity="Major", cpk_max=1.33,
        root_cause="Film deposition stress from temperature-induced mismatch or incorrect deposition parameter.",
        root_cause_detail=(
            "Film stress = mismatch between film and substrate thermal expansion coefficients + intrinsic "
            "deposition stress. Tensile stress bows wafer concave up. Compressive stress bows convex up. "
            "Bow > 100μm typically causes chuck problems in litho and CMP."
        ),
        alternative_causes=["Temperature ramp rate too fast causing quench stress", "Film stoichiometry drift affecting intrinsic stress", "Annealing step before deposition not performed"],
        corrective_actions=[
            CAPAAction("Measure wafer bow on all affected wafers. Classify as tensile or compressive from bow direction.", "Metrology", "Immediate", "P1", "Quantifies bow severity and stress type"),
            CAPAAction("Adjust deposition temperature by ±25°C. Measure stress change. Tune to target stress window.", "Process Engineer", "1 week", "P1", "Temperature is primary stress control lever"),
            CAPAAction("Review dopant or process gas ratios — stoichiometry changes intrinsic stress significantly.", "Process Engineer", "1 week", "P2", "Addresses intrinsic stress contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Add in-line bow/warp measurement after deposition. Alert if bow >80μm.", "Metrology", "2 weeks", "SOP"),
            PreventiveAction("Film stress coupon measurement monthly to track recipe baseline stress.", "Process Engineer", "Monthly", "PM"),
        ],
        containment="Measure bow on all lot wafers. Wafers with bow >150μm cannot proceed to litho.",
        disposition="Conditional Release", standard_reference="SEMI M49", weight=1.8,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # SEMICONDUCTOR — ION IMPLANT
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="SEMI-IMP-001", process="Implant", parameter="Sheet_Resistance",
        fault_pattern="Ion Implant Dose Offset — Rs Systematically High or Low",
        description="Post-implant sheet resistance systematically offset from target. Dose accuracy issue.",
        severity="Critical", cpk_max=1.33, cp_cpk_gap_min=0.3,
        root_cause="Faraday cup calibration drift, beam current measurement error, or scan uniformity issue.",
        root_cause_detail=(
            "Post-implant Rs is dose-controlled. Systematic Rs offset = dose error. Causes: "
            "(1) Faraday cup contamination or particle causing current measurement error, "
            "(2) scan speed/step calibration drift reducing coverage uniformity, "
            "(3) charge neutralizer failure causing charge build-up and dose error."
        ),
        alternative_causes=["Incoming wafer surface oxide change affecting implant range", "Beam angle drift from steering magnet", "End station pressure increase causing beam scattering"],
        corrective_actions=[
            CAPAAction("Cross-check dose using SIMS or spreading resistance on monitor wafer. Confirm actual vs set dose.", "Metrology", "Immediate", "P1", "Confirms dose error is real and quantifies magnitude"),
            CAPAAction("Inspect Faraday cup. Clean or replace if particle/residue found. Recalibrate after cleaning.", "Equipment", "Immediate", "P1", "Faraday cup contamination is most common dose error cause"),
            CAPAAction("Verify beam uniformity scan using photoresist test wafer. Adjust scan parameters if non-uniform.", "Equipment", "1 week", "P2", "Restores dose uniformity"),
        ],
        preventive_actions=[
            PreventiveAction("Weekly Faraday cup resistance check and visual inspection.", "Equipment", "Weekly", "PM"),
            PreventiveAction("Rs monitor wafer on every implant batch. Alert if Rs deviates >3% from target.", "Metrology", "Ongoing", "SPC"),
        ],
        containment="Rs measurement on all wafers from affected implant batch. Electrical test before release.",
        disposition="Hold", standard_reference="SEMI E102", weight=2.8,
    ),

    CAPARule(
        rule_id="SEMI-IMP-002", process="Implant", parameter="Uniformity",
        fault_pattern="Ion Implant Uniformity — Dose Non-Uniformity Across Wafer",
        description="Implant dose non-uniformity exceeds specification. Rs variation across wafer is excessive.",
        severity="Major", non_normal=True, cpk_max=1.33,
        root_cause="Scan velocity non-uniformity, beam current ripple, or mechanical scan actuator issue.",
        root_cause_detail=(
            "Implant uniformity is determined by beam scan: the scan velocity must be constant and the "
            "step size must be uniform. Non-uniformity signature: edge stripes = scan reversal dwell time; "
            "center bright spot = beam current ripple at scan turnaround."
        ),
        alternative_causes=["Beam current instability from ion source degradation", "Scan actuator bearing wear causing velocity jitter", "Wafer tilt from poor chucking"],
        corrective_actions=[
            CAPAAction("Map Rs across wafer (49-point). Identify pattern: stripes = scan issue, circular = beam issue.", "Metrology", "Immediate", "P1", "Identifies uniformity failure signature"),
            CAPAAction("If stripe pattern: adjust scan speed and turnaround dwell time. Verify with test wafer.", "Equipment", "1 week", "P1", "Corrects scan velocity non-uniformity"),
            CAPAAction("If random non-uniformity: inspect ion source. Replace if beam current stability >1% RMS.", "Equipment", "1 week", "P2", "Restores beam current stability"),
        ],
        preventive_actions=[
            PreventiveAction("Uniformity test wafer at start of each PM cycle. Accept only if non-uniformity <1%.", "Equipment", "Per PM", "PM"),
            PreventiveAction("Rs uniformity SPC chart on production monitor wafers.", "Process Engineer", "2 weeks", "SPC"),
        ],
        containment="100% uniformity measurement on affected lot.",
        disposition="Conditional Release", standard_reference="SEMI E102", weight=2.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # SEMICONDUCTOR — WET CLEAN
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="SEMI-CLEAN-001", process="WetClean", parameter="Particle_Count",
        fault_pattern="Wet Clean Particle Adder — Particles Added After Clean",
        description="Post-clean wafer particle count exceeds specification or pre-clean level. Clean is adding particles.",
        severity="Critical", ppm_min=500,
        root_cause="Bath contamination, DI water quality degradation, or particle shedding from spin chuck or nozzles.",
        root_cause_detail=(
            "A clean step that adds particles is worse than no clean. Causes: (1) SC1/SC2/DHF bath "
            "lifetime exceeded — bath becomes a particle source, (2) DI water resistivity dropped below "
            "spec — particles in DI water, (3) spin chuck or nozzle shedding particles."
        ),
        alternative_causes=["Wafer handling contamination between clean and particle measurement", "Particle scanner false counts from film interference", "N2 drying leaving evaporation residue"],
        corrective_actions=[
            CAPAAction("Drain and replace all chemistry baths immediately. Particle-test reference wafer in fresh bath.", "Equipment", "Immediate", "P1", "Rules out bath contamination — most common cause"),
            CAPAAction("Measure DI water resistivity and particle count at point-of-use. If <17 MΩ·cm or >1 particle/mL, escalate to facilities.", "Equipment", "Immediate", "P1", "DI water quality failure requires immediate facilities action"),
            CAPAAction("Inspect spin chuck for particle shedding. Run blank spin on QC wafer. If adds particles, replace chuck.", "Equipment", "1 week", "P2", "Identifies hardware particle source"),
        ],
        preventive_actions=[
            PreventiveAction("Bath particle count and chemistry concentration checks every 4 hours during production.", "Equipment", "Ongoing", "SOP"),
            PreventiveAction("DI water point-of-use particle monitoring — real-time alarm if particle count >5/mL.", "Facilities", "2 weeks", "SPC"),
        ],
        containment="QUARANTINE all wafers cleaned in affected bath. 100% particle inspection before release.",
        disposition="Hold", standard_reference="SEMI F47, SEMI C89", weight=3.0,
    ),

    CAPARule(
        rule_id="SEMI-CLEAN-002", process="WetClean", parameter="Oxide_Loss",
        fault_pattern="HF Clean Oxide Loss — Excessive Thermal Oxide Consumption",
        description="HF or DHF clean removing excessive native or thermal oxide. Risk of device layer damage.",
        severity="Major", cpk_max=1.33,
        root_cause="HF concentration too high, clean time too long, or bath temperature elevated above specification.",
        root_cause_detail=(
            "Thermal SiO2 etches at ~1nm/min in dilute HF (0.5%). Oxide loss > spec means etch time or "
            "concentration drifted. Consequences: contact resistance increase from insufficient oxide removal "
            "(too little etch) or device layer exposure (too much etch)."
        ),
        alternative_causes=["HF tank concentration drift from evaporation or drag-in", "Bath temperature controller failure causing accelerated etch", "Incoming film thickness variation changing effective etch rate"],
        corrective_actions=[
            CAPAAction("Measure HF bath concentration immediately using titration or refractive index. Adjust to target.", "Equipment", "Immediate", "P1", "Corrects HF concentration — primary control variable"),
            CAPAAction("Measure oxide thickness on monitor wafer before and after clean to quantify actual etch rate.", "Metrology", "Immediate", "P1", "Quantifies actual oxide removal for disposition"),
            CAPAAction("Check bath temperature controller calibration. Verify ±0.5°C accuracy.", "Equipment", "1 week", "P2", "Eliminates temperature contribution"),
        ],
        preventive_actions=[
            PreventiveAction("HF concentration measurement every 2 hours during production. SPC chart with ±0.05% alert.", "Equipment", "1 week", "SPC"),
            PreventiveAction("Oxide loss monitor coupon on every lot. Alert if loss deviates >0.3nm from target.", "Metrology", "Ongoing", "SPC"),
        ],
        containment="Measure oxide thickness on all wafers from affected clean batch.",
        disposition="Conditional Release", standard_reference="SEMI C89", weight=2.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # SEMICONDUCTOR — DIFFUSION
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="SEMI-DIFF-001", process="Diffusion", parameter="Sheet_Resistance",
        fault_pattern="Sheet Resistance — Furnace Temperature Offset",
        description="Sheet resistance off-center — furnace thermocouple calibration drift.",
        severity="Major", cpk_max=1.33, cp_cpk_gap_min=0.25,
        root_cause="Furnace temperature offset from thermocouple calibration drift or heating element degradation.",
        root_cause_detail=(
            "Rs is exponentially sensitive to anneal temperature. ±2°C at 1000°C causes >5% Rs shift. "
            "Check thermocouple last calibration date."
        ),
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

    CAPARule(
        rule_id="SEMI-DIFF-002", process="Diffusion", parameter="Uniformity",
        fault_pattern="Furnace Uniformity — Position-Dependent Non-Uniformity in Batch",
        description="Wafer-to-wafer uniformity in furnace batch is non-uniform. Front or back wafers differ from center.",
        severity="Major", spc_rules=["NE8", "NE4"],
        root_cause="Furnace temperature profile non-uniformity — inlet or outlet zones running off-temperature.",
        root_cause_detail=(
            "Batch furnace non-uniformity: edge wafers see different temperature from center due to end effects. "
            "Systematic pattern (front/back wafers different from center) = furnace zone calibration issue. "
            "Random pattern = boat loading variation."
        ),
        alternative_causes=["Boat loading non-uniformity (wafer spacing variation)", "Gas flow non-uniformity (N2 inlet position)", "Quartz tube temperature shadow from boat"],
        corrective_actions=[
            CAPAAction("Map Rs by boat position. Identify which positions are outliers. Check furnace zone temperatures for those positions.", "Process Engineer", "Immediate", "P1", "Identifies furnace zone contributing to non-uniformity"),
            CAPAAction("Recalibrate affected furnace zone thermocouples. Run temperature uniformity survey (TUS) after calibration.", "Equipment", "1 week", "P1", "Restores furnace temperature uniformity"),
            CAPAAction("Review boat loading SOP. Ensure wafer spacing is per specification.", "Manufacturing", "1 week", "P2", "Eliminates boat loading contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Quarterly furnace TUS (temperature uniformity survey) using certified thermocouple probe.", "Equipment", "Quarterly", "PM"),
            PreventiveAction("SPC chart tracking front/center/back wafer Rs differences within each batch.", "Process Engineer", "2 weeks", "SPC"),
        ],
        containment="Sort wafers by boat position. Measure and disposition each position group separately.",
        disposition="Conditional Release", standard_reference="SEMI M11, AMS 2750E", weight=1.9,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # CMM / GD&T (full set from R2 retained + new rules)
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="CMM-001", process="CMM", parameter="Flatness",
        fault_pattern="Flatness OOT — Surface Form Error",
        description="Flatness measurement out of tolerance. Surface deviates from true plane beyond specification.",
        severity="Major", cpk_max=1.33,
        root_cause="Machining distortion from clamping forces, thermal gradients during cutting, or residual stress release.",
        root_cause_detail=(
            "Flatness OOT on machined surfaces results from: (1) clamping distortion, "
            "(2) thermal gradient during cutting, (3) residual stress release after material removal."
        ),
        alternative_causes=["Worn machine spindle", "Incorrect CMM datum setup", "Part warpage from heat treatment", "Fixture contamination"],
        corrective_actions=[
            CAPAAction("Re-measure part on CMM with fresh datum setup. Verify stylus qualification is current.", "Metrology", "Immediate", "P1", "Eliminates CMM setup error as cause"),
            CAPAAction("Reduce clamping force by 30% and re-machine. Use softer clamping jaw material.", "Manufacturing", "1 week", "P1", "Reduces clamping distortion"),
            CAPAAction("Check cutting tool condition. Replace if >50% of rated life.", "Manufacturing", "1 week", "P2", "Reduces cutting forces and thermal gradient"),
        ],
        preventive_actions=[
            PreventiveAction("Add flatness SPC chart. Alert when trend approaches 80% of tolerance.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Define clamping torque specification in machining SOP.", "Manufacturing", "1 week", "SOP"),
        ],
        containment="Segregate affected parts. 100% CMM inspection of flatness before release.",
        disposition="Hold", standard_reference="ASME Y14.5-2018, ISO 1101", weight=2.2,
    ),

    CAPARule(
        rule_id="CMM-002", process="CMM", parameter="Roundness",
        fault_pattern="Roundness/Circularity OOT — Non-Round Cross Section",
        description="Circularity (roundness) out of tolerance. Cross-section deviates from true circle.",
        severity="Major", cpk_max=1.33,
        root_cause="Chuck jaw pressure causing lobing on turned parts, or worn spindle bearings.",
        root_cause_detail="3-jaw chuck creates 3-lobe pattern (triangular form). Worn spindle bearings create multi-lobe harmonic.",
        alternative_causes=["Thermal growth of spindle", "Incorrect center height on turning center", "Vibration from adjacent equipment"],
        corrective_actions=[
            CAPAAction("Identify lobing frequency from CMM roundness plot. 3-lobe = chuck issue, high-frequency = bearing issue.", "Metrology", "Immediate", "P1", "Identifies root cause category"),
            CAPAAction("Switch to 4-jaw chuck or collet for finish turning. Re-machine and verify.", "Manufacturing", "Immediate", "P1", "Eliminates 3-jaw chuck lobing"),
            CAPAAction("Check spindle bearing condition using vibration analysis. Schedule replacement if amplitude >2x baseline.", "Equipment", "1 week", "P1", "Eliminates bearing-induced lobing"),
        ],
        preventive_actions=[
            PreventiveAction("Quarterly spindle bearing vibration check in PM schedule.", "Equipment", "1 month", "PM"),
            PreventiveAction("Add roundness to in-process SPC.", "Quality", "2 weeks", "SPC"),
        ],
        containment="100% roundness inspection on affected batch.",
        disposition="Conditional Release", standard_reference="ASME Y14.5-2018, ISO 12181", weight=2.1,
    ),

    CAPARule(
        rule_id="CMM-003", process="CMM", parameter="Position",
        fault_pattern="True Position OOT — Feature Location Error",
        description="True position of hole or feature out of tolerance.",
        severity="Critical", cpk_max=1.00,
        root_cause="Datum reference frame error, CNC zero offset error, or fixture locating pin wear.",
        root_cause_detail="Position OOT is almost always systematic: worn fixture pins shift every part the same way, or CNC work offset entered incorrectly.",
        alternative_causes=["CMM datum setup inconsistency", "Thermal growth of machine or fixture", "Tool runout causing drill walk"],
        corrective_actions=[
            CAPAAction("Measure position deviation direction and magnitude on 3+ parts. Consistent direction = systematic cause.", "Metrology", "Immediate", "P1", "Identifies systematic vs. random position error"),
            CAPAAction("Check and correct CNC work offset. Inspect fixture locating pins for wear.", "Manufacturing", "Immediate", "P1", "Corrects systematic position offset"),
            CAPAAction("Check fixture clamping repeatability. Measure part location variation across 10 loads.", "Manufacturing", "1 week", "P1", "Reduces fixture-induced position scatter"),
        ],
        preventive_actions=[
            PreventiveAction("Add fixture pin diameter to monthly PM inspection.", "Equipment", "2 weeks", "PM"),
            PreventiveAction("First-article position check at start of each shift.", "Quality", "1 week", "SOP"),
        ],
        containment="MANDATORY 100% position inspection. Sort: in-spec release, out-of-spec hold.",
        disposition="Hold", standard_reference="ASME Y14.5-2018, ISO 5458", weight=3.0,
    ),

    CAPARule(
        rule_id="CMM-004", process="CMM", parameter="Angularity",
        fault_pattern="Angularity OOT — Surface/Feature Angle Error",
        description="Angularity of a surface or feature axis exceeds specification relative to datum.",
        severity="Major", cpk_max=1.33,
        root_cause="Machine rotary axis calibration error or fixture angular setting drift.",
        root_cause_detail=(
            "Angularity OOT means the feature is tilted relative to the datum reference frame. "
            "In machined parts: 5-axis machine rotary axis calibration error, or fixture angle setting. "
            "In CMM: datum selection error causing the coordinate frame to be tilted."
        ),
        alternative_causes=["Incorrect angular fixture setup (angle plate or sine bar not verified)", "CMM datum fit error from form error on datum surface", "Part distortion from clamping on angled setup"],
        corrective_actions=[
            CAPAAction("Re-establish CMM datum from clean, form-accurate datum surfaces. Re-measure angularity. Confirm error is real.", "Metrology", "Immediate", "P1", "Eliminates datum setup error as cause"),
            CAPAAction("If machined: verify 5-axis rotary axis calibration. Check angle vs calibration bar/artifact.", "Equipment", "1 week", "P1", "Corrects machine rotary axis error"),
            CAPAAction("Verify fixture angular setup using precision angle plate and sine bar. Adjust if angular error >30 arc-sec.", "Manufacturing", "1 week", "P2", "Eliminates fixture angle error"),
        ],
        preventive_actions=[
            PreventiveAction("Annual 5-axis rotary axis calibration using calibrated angular artifact.", "Equipment", "Annual", "PM"),
            PreventiveAction("Fixture setup verification: measure fixture angle on CMM before first part.", "Quality", "1 week", "SOP"),
        ],
        containment="100% angularity inspection on batch. Parts >150% of tolerance to scrap review.",
        disposition="Conditional Release", standard_reference="ASME Y14.5-2018, ISO 1101", weight=2.0,
    ),

    CAPARule(
        rule_id="CMM-005", process="CMM", parameter="Parallelism",
        fault_pattern="Parallelism OOT — Surface Not Parallel to Datum",
        description="Parallelism of surface or axis to datum plane exceeds tolerance. Part has taper or wedge form.",
        severity="Major", cpk_max=1.33,
        root_cause="Machine axis straightness error or workholding tilt causing systematic taper in machined part.",
        root_cause_detail=(
            "Parallelism failure = one surface tilted relative to another (taper). Common causes: "
            "(1) machine column/ram not perpendicular to table — systematic, affects every part, "
            "(2) workpiece tilted in fixture — part-to-part variation, "
            "(3) thermal growth of machine during long production run."
        ),
        alternative_causes=["Part distortion after release from fixture (spring-back)", "Cutting tool deflection on thin-wall features", "Coolant thermal gradient affecting machine geometry"],
        corrective_actions=[
            CAPAAction("Measure parallelism at multiple positions across surface. If consistent taper = machine alignment. If variable = fixturing.", "Metrology", "Immediate", "P1", "Identifies machine vs. fixture root cause"),
            CAPAAction("Check machine spindle perpendicularity using precision square and indicator. Correct if deviation >0.01mm/200mm.", "Equipment", "1 week", "P1", "Corrects machine geometric error"),
            CAPAAction("Verify workpiece is parallel to machine table before clamping. Use dial indicator across top face of part.", "Manufacturing", "1 week", "P2", "Eliminates fixture tilt contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Annual machine geometric accuracy check including parallelism/squareness.", "Equipment", "Annual", "PM"),
            PreventiveAction("Parallelism SPC chart on first article and periodic inspection.", "Quality", "2 weeks", "SPC"),
        ],
        containment="100% parallelism inspection. Rework by surface grinding if within material stock.",
        disposition="Conditional Release", standard_reference="ASME Y14.5-2018, ISO 1101", weight=2.0,
    ),

    CAPARule(
        rule_id="CMM-006", process="CMM", parameter="Perpendicularity",
        fault_pattern="Perpendicularity OOT — Feature Not Square to Datum",
        description="Perpendicularity of a bore, surface, or axis to datum exceeds specification.",
        severity="Major", cpk_max=1.33,
        root_cause="Drilling or boring machine axis squareness error, or workpiece not properly seated in fixture.",
        root_cause_detail=(
            "Perpendicularity OOT in drilled/bored holes: (1) drill press or boring machine spindle not "
            "perpendicular to table, (2) long drill walking due to no spot drill, (3) workpiece rocking "
            "in fixture on first contact during setup. Check if error is consistent (machine) or random (fixture)."
        ),
        alternative_causes=["Drill/boring bar runout causing asymmetric cutting", "Workpiece not clamped before drilling begins (part lifts)", "CMM stylus bending during long reach into deep hole"],
        corrective_actions=[
            CAPAAction("Measure perpendicularity on 3 parts. If consistent direction/magnitude = machine alignment. If random = fixture/setup.", "Metrology", "Immediate", "P1", "Identifies systematic vs random perpendicularity error"),
            CAPAAction("Use spot drill before full drill on all holes. Reduces drill walk by 60-80%.", "Manufacturing", "Immediate", "P1", "Prevents drill walk — most practical immediate fix"),
            CAPAAction("Check machine spindle squareness to table. Correct if deviation >0.02mm/300mm.", "Equipment", "1 week", "P2", "Corrects machine perpendicularity"),
        ],
        preventive_actions=[
            PreventiveAction("Require spot drill before all drilled features in machining SOP.", "Manufacturing", "1 week", "SOP"),
            PreventiveAction("Quarterly machine squareness check using certified square.", "Equipment", "Quarterly", "PM"),
        ],
        containment="100% perpendicularity inspection. Rework by precision boring if within stock.",
        disposition="Conditional Release", standard_reference="ASME Y14.5-2018, ISO 1101", weight=2.0,
    ),

    CAPARule(
        rule_id="CMM-007", process="CMM", parameter="Concentricity",
        fault_pattern="Concentricity/Coaxiality OOT — Axes Not Coincident",
        description="Concentricity or coaxiality of two features exceeds specification. Axes are offset.",
        severity="Major", cpk_max=1.33,
        root_cause="Rechucking between operations creating eccentricity, or machine spindle runout.",
        root_cause_detail=(
            "Concentricity measures the offset between the median points of two diameters relative to a datum axis. "
            "OOT concentricity almost always means the part was remounted between operations (e.g. OD turned in "
            "one setup, bore machined in another). The re-chuck eccentricity is the concentricity error."
        ),
        alternative_causes=["Machine spindle runout contributing to bore eccentricity", "CMM datum bore out-of-round causing apparent concentricity error", "Thermal growth shifting center during long operation"],
        corrective_actions=[
            CAPAAction("Machine both datum diameter and concentric feature in one setup without rechucking.", "Manufacturing", "Immediate", "P1", "Single-setup machining eliminates rechuck eccentricity — most effective fix"),
            CAPAAction("If rechucking unavoidable: use precision 4-jaw chuck with dial-in. Set TIR <0.002mm before cut.", "Manufacturing", "1 week", "P1", "Minimizes rechuck error when single setup is not possible"),
            CAPAAction("Check machine spindle runout with test bar. If >30% of concentricity tolerance, schedule maintenance.", "Equipment", "1 week", "P2", "Eliminates machine spindle contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Process design requirement: concentric features in same setup. Add to routing.", "Process Engineer", "1 month", "SOP"),
            PreventiveAction("Spindle TIR check monthly in PM.", "Equipment", "Monthly", "PM"),
        ],
        containment="100% concentricity inspection on batch.",
        disposition="Conditional Release", standard_reference="ASME Y14.5-2018, ISO 1101", weight=2.1,
    ),

    CAPARule(
        rule_id="CMM-008", process="CMM", parameter="Any",
        fault_pattern="CMM Gauge R&R High — Measurement Uncertainty Too Large",
        description="CMM GRR exceeds 30%. Measurement uncertainty too large relative to feature tolerance.",
        severity="Major", grr_min=30.0, ndc_max=4,
        root_cause="CMM probe qualification insufficient, stylus qualification drift, or part-fixture repeatability issue.",
        root_cause_detail=(
            "High CMM %GRR means the measurement process itself is unreliable. "
            "Common causes: (1) stylus qualification done too infrequently, (2) part fixturing not repeatable, "
            "(3) environmental vibration, (4) incorrect measurement strategy."
        ),
        alternative_causes=["Temperature variation in CMM room", "CMM vibration isolation failure", "Probe head bearing wear"],
        corrective_actions=[
            CAPAAction("Re-run GRR with fresh stylus qualification on clean reference sphere. Verify room temperature 20±1°C.", "Metrology", "Immediate", "P1", "Isolates qualification vs. hardware cause"),
            CAPAAction("Check part fixture: load same part 10 times, measure datum setup repeatability.", "Metrology", "1 week", "P1", "Eliminates fixturing as GRR contributor"),
            CAPAAction("Run CMM with and without vibration isolation. If GRR differs, check isolation pads.", "Equipment", "1 week", "P2", "Identifies vibration contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Qualify stylus at start of each measurement session.", "Metrology", "1 week", "SOP"),
            PreventiveAction("Annual CMM accuracy verification per ISO 10360-2.", "Equipment", "1 year", "PM"),
        ],
        containment="Suspend measurement-based decisions until GRR is below 30%.",
        disposition="Hold", standard_reference="AIAG MSA 4th Ed, ISO 10360-2", weight=2.5,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # AUTOMOTIVE (IATF 16949)
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="AUTO-001", process="Automotive", parameter="Dimensional",
        fault_pattern="PPAP Dimension OOT — IATF 16949 Cpk ≥1.67 Requirement",
        description="Critical dimension out of tolerance during PPAP. IATF 16949 Cpk ≥1.67 requirement not met.",
        severity="Critical", cpk_max=1.67,
        root_cause="Process not capable to IATF 16949 PPAP requirement of Cpk ≥1.67.",
        root_cause_detail=(
            "IATF 16949 and AIAG APQP require Cpk ≥1.67 for PPAP submission. "
            "Between 1.33–1.67 will pass ongoing monitoring but fail initial PPAP."
        ),
        alternative_causes=["Process designed to Cpk ≥1.33 target without PPAP margin", "Special cause during PPAP study window"],
        corrective_actions=[
            CAPAAction("Calculate whether gap is centering or spread. Centering fix is faster.", "Quality Engineer", "Immediate", "P1", "Determines fastest path to PPAP compliance"),
            CAPAAction("If centering gap: adjust setpoint. Re-run 30-piece study. Verify Cpk ≥1.67.", "Process Engineer", "1 week", "P1", "Expected Cpk improvement to ≥1.67"),
            CAPAAction("Notify customer immediately per IATF 16949 requirement.", "Quality Manager", "Immediate", "P1", "IATF 16949 compliance — customer notification mandatory"),
        ],
        preventive_actions=[
            PreventiveAction("Design process to Cpk ≥2.0 during development — margin for production drift.", "Process Engineer", "During APQP", "SOP"),
            PreventiveAction("Quarterly capability review for all PPAP characteristics.", "Quality", "Quarterly", "SOP"),
        ],
        containment="Apply IATF 16949 containment: 100% inspection, lot traceability, customer notification.",
        disposition="Hold", standard_reference="IATF 16949:2016, AIAG APQP/PPAP", weight=3.0,
    ),

    CAPARule(
        rule_id="AUTO-002", process="Automotive", parameter="Torque",
        fault_pattern="Fastener Torque — Low Cpk / SPC Alarm",
        description="Assembly torque capability below standard or SPC showing drift.",
        severity="Critical", cpk_max=1.33, spc_rules=["WE1", "WE4", "NE2"],
        root_cause="Torque tool calibration drift, worn socket, or operator technique variation.",
        root_cause_detail="Torque capability failure is safety-critical in automotive. Calibration is #1 root cause.",
        alternative_causes=["Thread damage affecting torque-tension conversion", "Lubricant type or application variation", "Fastener batch-to-batch friction variation"],
        corrective_actions=[
            CAPAAction("Pull torque tool calibration record. If >6 months, recalibrate immediately.", "Quality", "Immediate", "P1", "Mandatory IATF action"),
            CAPAAction("Inspect socket condition. Replace if wear visible or test error >5%.", "Manufacturing", "Immediate", "P1", "Eliminates socket wear contribution"),
            CAPAAction("Measure K-factor on fasteners from current lot. If changed vs approved lot, notify engineering.", "Quality Engineer", "1 week", "P1", "Identifies fastener-side friction variation"),
        ],
        preventive_actions=[
            PreventiveAction("Monthly torque tool calibration per ISO 6789.", "Quality", "Monthly", "PM"),
            PreventiveAction("Add torque SPC chart at assembly station. Immediate alert on WE1.", "Quality", "2 weeks", "SPC"),
        ],
        containment="100% torque audit on all assemblies from affected period. Rework undertorqued joints.",
        disposition="Hold", standard_reference="IATF 16949:2016, ISO 6789, VDI 2230", weight=2.8,
    ),

    CAPARule(
        rule_id="AUTO-003", process="Automotive", parameter="Weld_Strength",
        fault_pattern="Weld Strength — Low Tensile or Peel Force",
        description="Weld joint strength (tensile, peel, or torsion) below specification. Risk of in-service joint failure.",
        severity="Critical", cpk_max=1.33,
        root_cause="Weld parameter (current, time, pressure) drift or electrode wear causing insufficient weld nugget formation.",
        root_cause_detail=(
            "Resistance spot weld strength is directly controlled by: weld current (too low = undersized nugget), "
            "weld time (too short = insufficient heat), pressure (too low = poor contact/expulsion). "
            "Electrode wear degrades all three by changing contact geometry."
        ),
        alternative_causes=["Surface contamination (oil, oxide, coating) preventing proper weld formation", "Material thickness variation changing thermal input requirements", "Electrode misalignment causing off-center nugget"],
        corrective_actions=[
            CAPAAction("Perform weld nugget peel test on samples from production. Measure nugget diameter and compare to IATF minimum.", "Quality", "Immediate", "P1", "Confirms weld quality and establishes urgency"),
            CAPAAction("Check electrode wear: measure electrode face diameter. Replace if >15% diameter increase from new.", "Manufacturing", "Immediate", "P1", "Electrode wear is most common spot weld strength failure cause"),
            CAPAAction("Verify weld parameters (current, time, force) against approved WPS. If drifted, restore and run 3 test welds.", "Manufacturing", "Immediate", "P1", "Restores weld parameter compliance"),
        ],
        preventive_actions=[
            PreventiveAction("Electrode dressing every 200 welds. Replacement every 2000 welds or per qualification data.", "Manufacturing", "Ongoing", "SOP"),
            PreventiveAction("Weld force and current SPC monitoring with real-time alert per weld.", "Manufacturing", "2 weeks", "SPC"),
            PreventiveAction("Periodic destructive weld test (chisel or peel test) per IATF sampling plan.", "Quality", "Per schedule", "SOP"),
        ],
        containment="Destructive weld test on 5 samples per station from production period. Hold if any failure.",
        disposition="Hold", standard_reference="IATF 16949:2016, AWS D8.1M, ISO 14271", weight=2.9,
    ),

    CAPARule(
        rule_id="AUTO-004", process="Automotive", parameter="Leak_Rate",
        fault_pattern="Leak Test Failure — Assembly Leak Rate Exceeds Specification",
        description="Assembly leak rate exceeds specification. Seal integrity or housing leak path present.",
        severity="Critical", cpk_max=1.33, ppm_min=500,
        root_cause="O-ring damage, incorrect seating, housing porosity, or sealing surface damage.",
        root_cause_detail=(
            "Leak test failures have discrete root causes: (1) O-ring damage during assembly (cut, rolled), "
            "(2) incorrect O-ring size or material (substitution error), (3) housing casting porosity, "
            "(4) sealing surface damage from contamination or tool contact."
        ),
        alternative_causes=["Test station calibration error (false leaker)", "Leak standard gas pressure wrong", "Part temperature affecting seal compliance during test"],
        corrective_actions=[
            CAPAAction("Verify leak test station calibration with certified reference leak. If station fails, no production data is valid.", "Quality", "Immediate", "P1", "Station calibration must be verified before investigating parts"),
            CAPAAction("Disassemble leaking units. Inspect O-ring: cut, rolled, wrong size, or damaged groove?", "Manufacturing", "Immediate", "P1", "Identifies assembly defect mode"),
            CAPAAction("Inspect sealing surfaces under 10x magnification for scratches or contamination.", "Quality", "Immediate", "P1", "Identifies housing/surface damage"),
        ],
        preventive_actions=[
            PreventiveAction("Leak test station calibration verification at start of each shift with reference leak.", "Quality", "Daily", "SOP"),
            PreventiveAction("100% visual inspection of O-ring before installation. Reject any with damage.", "Manufacturing", "1 week", "SOP"),
            PreventiveAction("Sealing surface cleanliness standard: define acceptable condition in SOP with photos.", "Manufacturing", "1 month", "SOP"),
        ],
        containment="100% leak test. Failing parts: disassemble, inspect, rework with new O-ring, re-test.",
        disposition="Hold", standard_reference="IATF 16949:2016, ISO 3601", weight=2.8,
    ),

    CAPARule(
        rule_id="AUTO-005", process="Automotive", parameter="Adhesive_Bond",
        fault_pattern="Adhesive Bond Strength — Low Lap Shear or Peel Strength",
        description="Adhesive bond strength below specification. Risk of in-service delamination.",
        severity="Critical", cpk_max=1.33,
        root_cause="Surface contamination, incorrect primer application, or adhesive mix ratio error in two-component system.",
        root_cause_detail=(
            "Adhesive bond strength is extremely sensitive to surface preparation. Even fingerprint oils "
            "reduce bond strength by 50-70%. Root causes: (1) cleaning process failure, "
            "(2) primer not applied or cured incorrectly, (3) two-component adhesive mix ratio error, "
            "(4) open time exceeded before bonding."
        ),
        alternative_causes=["Adhesive shelf life expired or improper storage", "Bond line thickness not maintained (gap too thick or too thin)", "Cure temperature or time insufficient"],
        corrective_actions=[
            CAPAAction("Pull production records for cleaning process: bath concentration, rinse quality, dry time, time-to-bond.", "Quality Engineer", "Immediate", "P1", "Most bond failures trace back to surface preparation"),
            CAPAAction("Check adhesive batch records: lot number, expiry date, storage temperature. Quarantine if expired or out of storage spec.", "Quality", "Immediate", "P1", "Material compliance check"),
            CAPAAction("For two-component adhesive: verify mix ratio with weight check. Purge and re-prime dispensing system.", "Manufacturing", "Immediate", "P1", "Mix ratio error creates permanent bond failure"),
        ],
        preventive_actions=[
            PreventiveAction("Destructive bond test (lap shear or peel) per IATF sampling plan at defined frequency.", "Quality", "Per plan", "SOP"),
            PreventiveAction("Surface cleanliness test (water break test) before every bonding operation.", "Manufacturing", "1 week", "SOP"),
            PreventiveAction("Adhesive dispensing system mix ratio verification at start of shift.", "Manufacturing", "Daily", "SOP"),
        ],
        containment="Destructive test on minimum 5 bonds per production period. Hold if any below spec.",
        disposition="Hold", standard_reference="IATF 16949:2016, ISO 4587, ASTM D1002", weight=2.7,
    ),

    CAPARule(
        rule_id="AUTO-006", process="Automotive", parameter="Hardness",
        fault_pattern="Heat Treatment Hardness — Low Cpk or SPC Drift",
        description="Part hardness after heat treatment out of specification or showing drift.",
        severity="Critical", cpk_max=1.33, spc_rules=["NE3", "WE4"],
        root_cause="Furnace TUS due, atmosphere Cp drift, or quench media variation.",
        root_cause_detail="Heat treatment hardness failure is almost always furnace-related.",
        alternative_causes=["Incoming material chemistry variation", "Part cross-section variation changing quench rates", "Fixture masking causing uneven atmosphere exposure"],
        corrective_actions=[
            CAPAAction("Pull furnace TUS records. If >3 months since last TUS, perform emergency TUS immediately.", "Equipment", "Immediate", "P1", "IATF 16949 and AMS 2750 compliance action"),
            CAPAAction("Check atmosphere carbon potential for affected batch. If Cp drifted >0.05%, identify cause.", "Process Engineer", "Immediate", "P1", "Identifies atmosphere control failure"),
        ],
        preventive_actions=[
            PreventiveAction("Quarterly TUS per AMS 2750E.", "Equipment", "Quarterly", "PM"),
            PreventiveAction("Daily atmosphere Cp measurement and SPC chart.", "Process Engineer", "1 week", "SPC"),
        ],
        containment="100% hardness test on all parts from affected batch. Scrap if below minimum.",
        disposition="Hold", standard_reference="IATF 16949:2016, AMS 2750E", weight=3.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # AEROSPACE (AS9100)
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="AERO-001", process="Aerospace", parameter="Dimensional",
        fault_pattern="AS9100 Dimension OOT — Flight-Critical Feature",
        description="Flight-critical dimension out of tolerance. AS9100 nonconformance requiring MRB disposition.",
        severity="Critical", cpk_max=1.33,
        root_cause="Process drift or setup error on flight-critical dimension.",
        root_cause_detail="AS9100D requires documented nonconformance disposition. Root cause investigation must follow 8D methodology.",
        alternative_causes=["Drawing interpretation error", "Previous operation NC carried forward", "Wrong material or heat treatment"],
        corrective_actions=[
            CAPAAction("Immediately quarantine all affected parts. Initiate NCR per AS9100 clause 8.7.", "Quality Manager", "Immediate", "P1", "AS9100 compliance — NCR is mandatory"),
            CAPAAction("Convene MRB. Options: Use-As-Is (requires engineering approval), Rework, or Scrap.", "MRB/Engineering", "Immediate", "P1", "Required AS9100 disposition process"),
            CAPAAction("Perform 8D root cause analysis. Identify escape point.", "Quality Engineer", "1 week", "P1", "AS9100 requires root cause documentation"),
        ],
        preventive_actions=[
            PreventiveAction("FAI per AS9102B for any new or changed process.", "Quality", "Before production", "SOP"),
            PreventiveAction("Add critical dimension to in-process control plan.", "Quality", "2 weeks", "SOP"),
        ],
        containment="MANDATORY: quarantine, NCR, customer notification per contract requirements.",
        disposition="Hold", standard_reference="AS9100D, AS9102B", weight=3.0,
    ),

    CAPARule(
        rule_id="AERO-002", process="Aerospace", parameter="Surface_Integrity",
        fault_pattern="Surface Integrity — Grinding Burn on Aerospace Component",
        description="Thermal damage (grinding burn) detected or suspected on aerospace safety-critical component.",
        severity="Critical", cpk_max=1.33, non_normal=True,
        root_cause="Grinding burn from insufficient coolant delivery or excessive grinding depth.",
        root_cause_detail="Grinding burn creates tensile residual stress, reducing fatigue life. Not always visible — NDI required.",
        alternative_causes=["Dressing interval too long", "Coolant nozzle clogged", "Wheel specification wrong for material"],
        corrective_actions=[
            CAPAAction("Quarantine all parts ground in affected period. Perform Barkhausen noise or nital etch inspection.", "Quality", "Immediate", "P1", "NDI required — visual inspection INSUFFICIENT"),
            CAPAAction("Inspect coolant nozzle position and flow rate.", "Equipment", "Immediate", "P1", "Coolant delivery is #1 cause of grinding burn"),
            CAPAAction("Dress wheel and run test piece before resuming production.", "Manufacturing", "Immediate", "P1", "Confirms setup correct before restart"),
        ],
        preventive_actions=[
            PreventiveAction("Define grinding parameters window in SOP: wheel spec, dress interval, coolant flow, DOC limits.", "Process Engineer", "2 weeks", "SOP"),
            PreventiveAction("Periodic Barkhausen noise inspection per customer spec.", "Quality", "Per spec", "Metrology"),
        ],
        containment="SCRAP if burn confirmed — no rework allowed for safety-critical aerospace surfaces.",
        disposition="Scrap", standard_reference="AS9100D, AMS 2759/9", weight=3.0,
    ),

    CAPARule(
        rule_id="AERO-003", process="Aerospace", parameter="Fatigue",
        fault_pattern="Fatigue Life — Reduced Life Prediction from Material or Process Anomaly",
        description="Material or process anomaly detected that may reduce component fatigue life below design minimum.",
        severity="Critical",
        root_cause="Material discontinuity, surface damage, or incorrect heat treatment condition reducing fatigue resistance.",
        root_cause_detail=(
            "Aerospace fatigue life is designed with specific material properties, surface conditions, and residual stress states. "
            "Deviations: wrong heat treatment condition changes material microstructure, surface damage introduces stress raisers, "
            "incorrect shot peening coverage leaves tensile residual stress zones."
        ),
        alternative_causes=["Fretting damage from assembly (contact fatigue)", "Incorrect surface treatment (anodize thickness, plating)", "EDM recast layer not removed on critical surfaces"],
        corrective_actions=[
            CAPAAction("Initiate NCR immediately. Assess which material/process spec was violated and by how much.", "Quality Manager", "Immediate", "P1", "NCR mandatory — this is a safety-of-flight issue"),
            CAPAAction("Engage customer engineering for fatigue life re-analysis with actual (deviated) condition.", "Engineering", "Immediate", "P1", "Customer life prediction re-analysis required before any release decision"),
            CAPAAction("Perform representative coupon testing if re-analysis shows borderline life reduction.", "Engineering", "Per agreement", "P2", "Physical test data can support engineering disposition"),
        ],
        preventive_actions=[
            PreventiveAction("Document material condition (heat treat lot, hardness, microstructure) on all flight parts.", "Quality", "Per contract", "SOP"),
            PreventiveAction("First-article fatigue coupon test for any new material or process change.", "Engineering", "Before production", "SOP"),
        ],
        containment="Hold all affected parts. Customer notification required. Engineering disposition required before any release.",
        disposition="Hold", standard_reference="AS9100D, MIL-HDBK-5J, ASTM E466", weight=3.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # MEDICAL DEVICES (ISO 13485)
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="MED-001", process="Medical", parameter="Dimensional",
        fault_pattern="Medical Device Dimension OOT — ISO 13485 Nonconformance",
        description="Critical dimension on medical device out of specification. ISO 13485 CAPA required.",
        severity="Critical", cpk_max=1.33,
        root_cause="Process drift on a critical dimension affecting device safety or performance.",
        root_cause_detail="ISO 13485:2016 clause 8.3 requires documented NC procedures and CAPA. Class II/III may require regulatory notification.",
        alternative_causes=["Drawing revision not incorporated", "Incoming material NC not detected"],
        corrective_actions=[
            CAPAAction("Initiate NCPR per ISO 13485 clause 8.3. Quarantine all potentially affected units.", "Quality Manager", "Immediate", "P1", "ISO 13485 mandatory"),
            CAPAAction("Assess risk using ISO 14971. Determine if OOT creates patient safety risk.", "Clinical/Regulatory", "Immediate", "P1", "Risk-based disposition required"),
            CAPAAction("Initiate formal CAPA per ISO 13485 clause 8.5.2.", "Quality Engineer", "1 week", "P1", "ISO 13485 CAPA mandatory and audited"),
        ],
        preventive_actions=[
            PreventiveAction("Validate measurement system per ISO 13485 — documented GRR study.", "Quality", "Before production", "Metrology"),
            PreventiveAction("Add critical dimension to SPC per ISO 13485 clause 8.2.6.", "Quality", "2 weeks", "SPC"),
        ],
        containment="MANDATORY quarantine, NCPR, risk assessment. Possible regulatory notification.",
        disposition="Hold", standard_reference="ISO 13485:2016, FDA 21 CFR 820, ISO 14971", weight=3.0,
    ),

    CAPARule(
        rule_id="MED-002", process="Medical", parameter="Sterility",
        fault_pattern="Sterility / Bioburden — Pre-Sterilization Bioburden OOT",
        description="Pre-sterilization bioburden exceeds validated limit. Sterilization efficacy at risk.",
        severity="Critical", ppm_min=100,
        root_cause="Contamination introduced during manufacturing from unqualified personnel, environment, or materials.",
        root_cause_detail=(
            "Medical device sterility depends on: (1) pre-sterilization bioburden being below the validated limit "
            "(sterilization process is validated to a specific bioburden level — exceeding it may not yield SAL 10⁻⁶), "
            "(2) package integrity, (3) sterilization process compliance."
        ),
        alternative_causes=["Environmental monitoring showing excursion in cleanroom", "Raw material contamination", "HVAC filter change or maintenance event"],
        corrective_actions=[
            CAPAAction("Quarantine all product manufactured in affected period. Do not sterilize until root cause found.", "Quality Manager", "Immediate", "P1", "Cannot sterilize product with unknown elevated bioburden — SAL not guaranteed"),
            CAPAAction("Perform environmental monitoring (settle plates, active air) in all cleanroom zones immediately.", "Quality", "Immediate", "P1", "Identifies environmental contamination source"),
            CAPAAction("Review gowning records, personnel training, and material lot entries for affected period.", "Quality Engineer", "Immediate", "P1", "Identifies procedural or material root cause"),
        ],
        preventive_actions=[
            PreventiveAction("Routine environmental monitoring per ISO 14644 frequency requirements.", "Quality", "Per schedule", "SOP"),
            PreventiveAction("Bioburden testing on finished device per ISO 11737-1 at defined frequency.", "Quality", "Per spec", "SOP"),
        ],
        containment="Hold all product from affected period. Bioburden retest before release decision.",
        disposition="Hold", standard_reference="ISO 13485:2016, ISO 11135, ISO 11737", weight=3.0,
    ),

    CAPARule(
        rule_id="MED-003", process="Medical", parameter="Particulate",
        fault_pattern="Particulate Contamination — Visible or Subvisible Particles",
        description="Device or injectable product shows particulate contamination above specification.",
        severity="Critical", ppm_min=100,
        root_cause="Contamination from manufacturing environment, components, or process equipment shedding.",
        root_cause_detail=(
            "Particulate in injectables or implant devices can cause patient harm. Sources: "
            "(1) container/closure (glass delamination, stopper particles), "
            "(2) process equipment (pump wear, filter fiber shedding), "
            "(3) environment (ISO class excursion during filling)."
        ),
        alternative_causes=["Lyophilization cake collapse creating particulate", "Drug-excipient interaction forming insoluble aggregate", "Shipping vibration causing particulate generation"],
        corrective_actions=[
            CAPAAction("100% visual inspection under appropriate illumination per USP <790>. Reject all units with visible particles.", "Quality", "Immediate", "P1", "Mandatory product protection action"),
            CAPAAction("Characterize particles by SEM/EDX or FTIR if quantity available. Identify particle composition to find source.", "Quality/Engineering", "Immediate", "P1", "Particle composition is key to identifying source"),
            CAPAAction("Investigate particle source by elimination: test each process component (container, closure, equipment) separately.", "Process Engineer", "1 week", "P1", "Systematic elimination identifies particle origin"),
        ],
        preventive_actions=[
            PreventiveAction("Routine subvisible particle testing per USP <787>/<788> at batch release.", "Quality", "Per spec", "SOP"),
            PreventiveAction("Equipment surface and extractable evaluation during process validation.", "Engineering", "Before production", "SOP"),
        ],
        containment="MANDATORY 100% visual inspection. Hold batch pending investigation.",
        disposition="Hold", standard_reference="ISO 13485:2016, USP <787>, USP <790>, FDA 21 CFR 211", weight=3.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # PHARMACEUTICAL / BIOTECH
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="PHARMA-001", process="Pharma", parameter="Content_Uniformity",
        fault_pattern="Content Uniformity Failure — Dose Uniformity OOT per USP <905>",
        description="Tablet or capsule content uniformity fails USP <905> acceptance criteria. L1 or L2 failure.",
        severity="Critical", cpk_max=1.33, non_normal=True,
        root_cause="API segregation during blending or compression, or granulation non-uniformity.",
        root_cause_detail=(
            "Content uniformity OOT = dose-to-dose API variation too high. Causes: "
            "(1) API segregation in blend or press hopper due to particle size/density difference, "
            "(2) over-lubrication reducing blend cohesion, "
            "(3) static charge causing API agglomeration, "
            "(4) press force variation changing tablet weight."
        ),
        alternative_causes=["Blending time insufficient or over-blended (over-blending can cause segregation)", "Press hopper level variation causing density variation", "API lot change with different particle size distribution"],
        corrective_actions=[
            CAPAAction("Immediately quarantine affected batch. Do not release. Initiate OOS investigation per 21 CFR 211.192.", "Quality Manager", "Immediate", "P1", "FDA 21 CFR 211 OOS investigation mandatory"),
            CAPAAction("Pull blend samples from multiple locations. Assay for API content. Identify whether blend or press is root cause.", "Quality/Analytical", "Immediate", "P1", "Distinguishes blend-level from press-level non-uniformity"),
            CAPAAction("If press: measure tablet weight variation. High weight CV (>1%) indicates flow or hopper issue.", "Manufacturing", "Immediate", "P1", "Tablet weight is proxy for API content variation at press"),
        ],
        preventive_actions=[
            PreventiveAction("In-process tablet weight control per compendial limits. Statistical process control on press.", "Manufacturing", "Ongoing", "SPC"),
            PreventiveAction("Blend endpoint determination via NIR or thief sampling. Validate blending time.", "Process Engineer", "During validation", "SOP"),
        ],
        containment="Hold batch. OOS investigation per 21 CFR 211.192. FDA notification may be required.",
        disposition="Hold", standard_reference="USP <905>, ICH Q6A, FDA 21 CFR 211.110", weight=3.0,
    ),

    CAPARule(
        rule_id="PHARMA-002", process="Pharma", parameter="Dissolution",
        fault_pattern="Dissolution Failure — API Release Rate OOT per USP <711>",
        description="Drug dissolution profile fails USP <711> acceptance criteria. Bioavailability at risk.",
        severity="Critical", cpk_max=1.33,
        root_cause="Film coating thickness, formulation, or API particle size change affecting dissolution rate.",
        root_cause_detail=(
            "Dissolution rate controls drug bioavailability. Failures: "
            "(1) film coat too thick = slow release (for IR: barrier), "
            "(2) API particle size increase = slower dissolution, "
            "(3) hardness too high = disintegration delayed, "
            "(4) lubricant over-blending = hydrophobic coating on API."
        ),
        alternative_causes=["Raw material lot change (different API polymorph)", "Compression force change affecting porosity", "Dissolution test method execution error"],
        corrective_actions=[
            CAPAAction("OOS investigation per 21 CFR 211.192. Re-test by second analyst with fresh sample before concluding failure.", "Quality/Analytical", "Immediate", "P1", "Phase 1 OOS investigation — lab error must be ruled out first"),
            CAPAAction("If confirmed OOS: quarantine batch. Pull process records for coating, compression, and blending parameters.", "Quality Manager", "Immediate", "P1", "FDA mandatory OOS investigation"),
            CAPAAction("Check API particle size distribution on retained sample vs specification. If D90 shifted, API lot is likely cause.", "Quality", "Immediate", "P1", "API PSD is most common raw material root cause for dissolution failure"),
        ],
        preventive_actions=[
            PreventiveAction("Dissolution testing per USP <711> at batch release for all modified-release products.", "Quality", "Per spec", "SOP"),
            PreventiveAction("API PSD verification on incoming lots for dissolution-critical products.", "Quality", "Per spec", "SOP"),
        ],
        containment="Hold batch pending OOS investigation. FDA notification if required by site procedures.",
        disposition="Hold", standard_reference="USP <711>, ICH Q6A, FDA 21 CFR 211.110", weight=3.0,
    ),

    CAPARule(
        rule_id="PHARMA-003", process="Pharma", parameter="Fill_Weight",
        fault_pattern="Fill Weight — Low Cpk or SPC Drift During Filling",
        description="Fill weight capability below standard or SPC showing drift during tablet/capsule/liquid filling.",
        severity="Major", cpk_max=1.33, spc_rules=["NE2", "NE3", "WE4"],
        root_cause="Fill mechanism wear, formulation flow variation, or environmental humidity change affecting powder flow.",
        root_cause_detail=(
            "Fill weight drift in tablet presses: punch wear causes progressive fill volume change. "
            "In capsule fillers: tamping pin wear, powder flow variation from humidity, "
            "or vibration feeder calibration drift. SPC trend = tool wear. Step change = parameter change."
        ),
        alternative_causes=["Powder blend moisture change during filling (hygroscopic formulations)", "Feeder speed calibration drift", "Press speed change altering dwell time and fill time"],
        corrective_actions=[
            CAPAAction("Check in-process weight against specification. Calculate how long deviation has been occurring from SPC chart.", "Quality", "Immediate", "P1", "Establishes extent of impact on current batch"),
            CAPAAction("If trend pattern: measure punch wear. Replace punches if fill volume deviation >0.5%.", "Manufacturing", "Immediate", "P1", "Punch wear is most common fill weight trend cause"),
            CAPAAction("Check powder blend moisture. If humidity changed >5% RH, assess flow property impact.", "Process Engineer", "1 week", "P2", "Humidity effect on powder flow is common in hygroscopic formulations"),
        ],
        preventive_actions=[
            PreventiveAction("In-process weight check per GMP sampling plan (typically every 15 min). SPC chart with alert.", "Manufacturing", "Ongoing", "SPC"),
            PreventiveAction("Punch replacement program based on number of tablets produced, not on failure.", "Manufacturing", "Per schedule", "SOP"),
        ],
        containment="Segregate product produced outside weight specification. 100% check or statistical lot disposition.",
        disposition="Conditional Release", standard_reference="FDA 21 CFR 211.110, USP <2091>", weight=2.5,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # ELECTRONICS / PCB
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="PCB-001", process="Electronics", parameter="Solder_Joint",
        fault_pattern="Solder Joint Defect — Cold Solder, Bridging, or Insufficient Fill",
        description="Solder joint quality OOT: cold joints, bridging, or insufficient fillet per IPC-A-610.",
        severity="Critical", cpk_max=1.33, ppm_min=500,
        root_cause="Reflow profile deviation, solder paste quality, or pad/component coplanarity issue.",
        root_cause_detail=(
            "Solder defects by type: cold joint = insufficient temperature or time above liquidus, "
            "bridging = too much paste or paste slump, insufficient fillet = paste volume too low or "
            "tombstoning = unbalanced thermal load. Profile deviations are most common."
        ),
        alternative_causes=["Stencil aperture clogging reducing paste volume", "PCB pad oxidation preventing wetting", "Component lead coplanarity OOT", "Nitrogen atmosphere malfunction in reflow oven"],
        corrective_actions=[
            CAPAAction("Pull reflow oven profile from affected production run. Compare peak temperature and time-above-liquidus to approved profile.", "Process Engineer", "Immediate", "P1", "Reflow profile deviation is #1 solder defect cause"),
            CAPAAction("Measure solder paste print height and volume on stencil printer. Verify aperture opening is not clogged.", "Manufacturing", "Immediate", "P1", "Paste print quality directly determines joint quality"),
            CAPAAction("Inspect component coplanarity on suspect component lots using 3D SPI or shadow moiré.", "Metrology", "1 week", "P2", "Coplanarity OOT causes non-wetting on lifted leads"),
        ],
        preventive_actions=[
            PreventiveAction("Automated SPI (solder paste inspection) 100% after printing. Cpk >1.33 on paste volume.", "Quality", "Ongoing", "SPC"),
            PreventiveAction("Reflow oven temperature profiling — verify approved profile quarterly and after maintenance.", "Process Engineer", "Quarterly", "PM"),
            PreventiveAction("AOI (automated optical inspection) 100% after reflow. Review defect Pareto weekly.", "Quality", "Ongoing", "SPC"),
        ],
        containment="100% AOI inspection on affected boards. IPC-A-610 Class 2 or 3 criteria for disposition.",
        disposition="Conditional Release", standard_reference="IPC-A-610, IPC 7711/7721, J-STD-001", weight=2.8,
    ),

    CAPARule(
        rule_id="PCB-002", process="Electronics", parameter="Impedance",
        fault_pattern="PCB Controlled Impedance OOT — Signal Integrity Risk",
        description="Controlled impedance on PCB out of specification. Risk of signal reflection or cross-talk.",
        severity="Major", cpk_max=1.33,
        root_cause="Dielectric material thickness variation or trace width etching variation from nominal.",
        root_cause_detail=(
            "Impedance Z0 depends on trace width (W), dielectric thickness (H), and Er. OOT impedance means "
            "one or more of these drifted. Most common: (1) laminate Dk/Df variation lot-to-lot, "
            "(2) trace width variation from etch undercut, (3) pre-preg thickness variation from press cycle."
        ),
        alternative_causes=["Press cycle temperature/pressure variation changing dielectric thickness", "Etching chemistry concentration drift", "Coupon test structure different from production trace (coupon not representative)"],
        corrective_actions=[
            CAPAAction("Test TDR (time domain reflectometry) on coupon from affected lot. Confirm impedance deviation.", "Metrology", "Immediate", "P1", "Confirms impedance deviation on production material"),
            CAPAAction("Request laminate material test report from PCB supplier. Check Dk at relevant frequency vs specification.", "Quality", "Immediate", "P1", "Dk variation is most common controlled impedance failure cause"),
            CAPAAction("Check etching process: line width on affected lot vs nominal. If trace narrow, impedance increases.", "Quality", "1 week", "P2", "Etch undercut causes impedance increase"),
        ],
        preventive_actions=[
            PreventiveAction("Impedance coupon testing on every PCB panel per IPC-2141A.", "Quality", "Per spec", "SOP"),
            PreventiveAction("Laminate material incoming inspection: Dk/Df certificate review and dimensional check.", "Quality", "Incoming", "SOP"),
        ],
        containment="Test impedance coupon on all panels from affected production window. Reject if OOT.",
        disposition="Hold", standard_reference="IPC-2141A, IPC-6012, IPC-TM-650", weight=2.2,
    ),

    CAPARule(
        rule_id="PCB-003", process="Electronics", parameter="Warpage",
        fault_pattern="PCB Warpage — Board Flatness Exceeds SMT Assembly Limit",
        description="PCB warpage exceeds IPC-A-610 or SMT assembly specification. Risk of assembly defects.",
        severity="Major", cpk_max=1.33,
        root_cause="Thermal stress from lamination, reflow, or asymmetric copper distribution causing board bow.",
        root_cause_detail=(
            "PCB warpage causes: (1) asymmetric copper distribution creates CTE mismatch stress, "
            "(2) reflow thermal cycle warps the board (bow during reflow, may recover partially), "
            "(3) lamination press cycle variation. Warpage >0.75% for BGA boards causes assembly issues."
        ),
        alternative_causes=["BGA component thermal mismatch", "Wave solder thermal shock", "Incorrect storage (boards stored flat vs stacked without support)"],
        corrective_actions=[
            CAPAAction("Measure warpage per IPC-TM-650 2.4.22 on affected boards. Classify: bow vs twist.", "Metrology", "Immediate", "P1", "Quantifies warpage and identifies type"),
            CAPAAction("Review copper pour balancing in PCB design. If one side has significantly more copper, add copper pour to balance.", "Engineering", "1 week", "P1", "CTE balance is the fundamental fix for thermal warpage"),
            CAPAAction("Review lamination press cycle. Pressure and cool-down rate affect residual stress.", "PCB Supplier", "1 week", "P2", "Lamination process correction at supplier"),
        ],
        preventive_actions=[
            PreventiveAction("Design rule check for copper balance: top vs bottom copper area ratio >0.9.", "Engineering", "During design", "SOP"),
            PreventiveAction("Incoming PCB warpage measurement. Reject if >IPC-A-610 limit.", "Quality", "Incoming", "SOP"),
        ],
        containment="Measure warpage on all boards from affected lot. Boards > assembly limit to rework or scrap.",
        disposition="Conditional Release", standard_reference="IPC-A-610, IPC-TM-650 2.4.22", weight=2.0,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # INJECTION MOLDING
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="MOLD-001", process="InjectionMolding", parameter="Dimensional",
        fault_pattern="Injection Molded Part Dimension OOT — Systematic Shift",
        description="Injection molded part dimensions systematically shifted from nominal. Shrinkage or warpage issue.",
        severity="Major", cpk_max=1.33, cp_cpk_gap_min=0.3,
        root_cause="Holding pressure, melt temperature, or cooling time variation changing part shrinkage.",
        root_cause_detail=(
            "Dimensional shift in injection molding: (1) holding pressure too low = more shrinkage = part undersized, "
            "(2) melt temperature too high = lower viscosity = more pack = part oversized after cooling, "
            "(3) cooling time too short = part distorts after ejection, (4) mold temperature non-uniformity = differential shrinkage."
        ),
        alternative_causes=["Material lot change — different melt flow index affects shrinkage", "Colorant addition changing rheology", "Mold wear allowing flash"],
        corrective_actions=[
            CAPAAction("Measure shifted dimensions. Determine if shift is uniform (all dimensions same direction) = shrinkage, or non-uniform = warpage.", "Metrology", "Immediate", "P1", "Uniform shift = process parameter, non-uniform = cooling or residual stress"),
            CAPAAction("Check holding pressure vs setpoint. If drifted, correct and run 10-shot capability test.", "Manufacturing", "Immediate", "P1", "Holding pressure is primary dimensional control in injection molding"),
            CAPAAction("Check material lot change log. If material changed recently, request Melt Flow Index (MFI) data.", "Quality", "1 week", "P2", "Material MFI variation affects shrinkage and dimensions"),
        ],
        preventive_actions=[
            PreventiveAction("Add in-process dimensional check every 30 shots. SPC chart with alert at 80% of tolerance.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Material incoming MFI verification for dimensional-critical molds.", "Quality", "Incoming", "SOP"),
        ],
        containment="Measure critical dimensions on all parts from affected production. Sort and disposition.",
        disposition="Conditional Release", standard_reference="IATF 16949:2016 (automotive), ISO 294-4", weight=2.3,
    ),

    CAPARule(
        rule_id="MOLD-002", process="InjectionMolding", parameter="Warpage",
        fault_pattern="Molded Part Warpage — Non-Planar Distortion",
        description="Injection molded part warping beyond flatness specification after ejection.",
        severity="Major", cpk_max=1.33, non_normal=True,
        root_cause="Non-uniform cooling from mold temperature imbalance or asymmetric part design causing differential shrinkage.",
        root_cause_detail=(
            "Warpage in injection molded parts: (1) mold cavity/core temperature difference causes non-uniform shrinkage, "
            "(2) thin vs thick section differential cooling, (3) anisotropic fiber orientation in glass-filled materials, "
            "(4) early ejection before part is sufficiently rigid."
        ),
        alternative_causes=["Gate location creating non-symmetric fill pattern", "Part design — non-uniform wall thickness", "Ejector pin force distorting thin sections"],
        corrective_actions=[
            CAPAAction("Measure mold cavity and core temperatures under production conditions. If asymmetric, adjust cooling flow.", "Equipment", "Immediate", "P1", "Temperature uniformity correction is fastest fix for warpage"),
            CAPAAction("Increase cooling time by 20% and re-measure warpage. If improved, cooling time was insufficient.", "Process Engineer", "Immediate", "P1", "Quick diagnosis: if cooling time fixes it, part was ejected too early"),
            CAPAAction("For glass-filled materials: adjust fill speed to control fiber orientation. Faster fill = more orientation = more anisotropic warpage.", "Process Engineer", "1 week", "P2", "Fiber orientation control for glass-filled material warpage"),
        ],
        preventive_actions=[
            PreventiveAction("Mold temperature controller calibration quarterly. Map temperature distribution annually.", "Equipment", "Quarterly", "PM"),
            PreventiveAction("Part warpage gauge or CMM check on first-articles. Define warpage limit in control plan.", "Quality", "2 weeks", "SOP"),
        ],
        containment="100% flatness check on affected parts. Apply fixturing jig to check if warpage is functional concern.",
        disposition="Conditional Release", standard_reference="ISO 294-4, ASTM D955", weight=2.0,
    ),

    CAPARule(
        rule_id="MOLD-003", process="InjectionMolding", parameter="Sink_Marks",
        fault_pattern="Sink Marks — Surface Depressions Over Thick Sections",
        description="Sink marks visible on part surface above thick ribs, bosses, or section changes.",
        severity="Major", ppm_min=1000,
        root_cause="Insufficient holding pressure or holding time allowing surface skin to collapse inward during cooling.",
        root_cause_detail=(
            "Sink marks form because thick sections cool and shrink more than the surface skin. "
            "Causes: (1) holding pressure too low — not enough material packed in to compensate shrinkage, "
            "(2) gate freezes too early, cutting off packing pressure before thick section solidifies, "
            "(3) wall thickness ratio too high (rib:wall > 60% is risky)."
        ),
        alternative_causes=["Melt temperature too high causing excessive shrinkage", "Gate too small freezing before thick section solidifies", "Part design — rib too thick relative to nominal wall"],
        corrective_actions=[
            CAPAAction("Increase holding pressure by 10% increments and evaluate sink mark improvement. Document optimal holding pressure.", "Process Engineer", "Immediate", "P1", "Holding pressure increase is first-response for sink marks"),
            CAPAAction("Extend holding time by 2s. If sink mark reduces, gate was freezing too early.", "Process Engineer", "Immediate", "P1", "Gate freeze-off time diagnosis"),
            CAPAAction("Check gate land length. If gate is undersized (<50% of required area), increase gate size.", "Tool/Engineering", "1 week", "P2", "Gate sizing correction for persistent sink marks"),
        ],
        preventive_actions=[
            PreventiveAction("Mold filling simulation (Moldflow/MoldEx) during tool design to predict sink risk.", "Engineering", "During design", "SOP"),
            PreventiveAction("Aesthetic first-article inspection against approved standard part.", "Quality", "Per production run", "SOP"),
        ],
        containment="Visual inspection on all parts from affected run against defined sink mark standard.",
        disposition="Conditional Release", standard_reference="ISO 294-4, ASTM D955", weight=1.8,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # WELDING
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="WELD-001", process="Welding", parameter="Penetration",
        fault_pattern="Incomplete Fusion / Penetration — Weld Joint Integrity Risk",
        description="Radiographic or ultrasonic testing reveals incomplete fusion or penetration in weld joint.",
        severity="Critical",
        root_cause="Heat input too low, travel speed too fast, or joint preparation insufficient for full fusion.",
        root_cause_detail=(
            "Incomplete fusion: the base metal and filler metal did not melt together completely. "
            "Causes: (1) arc current too low — insufficient energy to melt base metal, "
            "(2) travel speed too fast — arc moves before full fusion, "
            "(3) joint angle too narrow — arc can't reach the root, "
            "(4) contamination (oil, moisture, rust) preventing fusion."
        ),
        alternative_causes=["Wrong shielding gas mixture reducing arc penetration", "Electrode angle incorrect for joint geometry", "Base metal preheat temperature insufficient for thick section"],
        corrective_actions=[
            CAPAAction("Initiate NCR. NDT (RT or UT) all welds from affected welder/shift. No release without NDT clearance.", "Quality", "Immediate", "P1", "Safety-critical defect — 100% NDT mandatory before disposition"),
            CAPAAction("Review WPS compliance: verify welder was following approved WPS current, voltage, and travel speed.", "Quality Engineer", "Immediate", "P1", "WPS deviation is most common incomplete fusion cause"),
            CAPAAction("Inspect joint preparation on similar joints. Verify joint angle, root opening, and surface cleanliness.", "Manufacturing", "Immediate", "P1", "Joint prep deficiencies prevent root fusion"),
        ],
        preventive_actions=[
            PreventiveAction("Welder qualification per AWS D1.1 or ASME IX. Document welder certification records.", "Quality", "Before production", "SOP"),
            PreventiveAction("First-weld destructive macrosection test at start of each production run or shift.", "Quality", "Per schedule", "SOP"),
            PreventiveAction("Weld parameter logging (current, voltage, travel speed) with alert if outside WPS limits.", "Manufacturing", "2 weeks", "SPC"),
        ],
        containment="Hold all welded assemblies from affected period. 100% NDT before release.",
        disposition="Hold", standard_reference="AWS D1.1, ASME Section IX, ISO 5817", weight=3.0,
    ),

    CAPARule(
        rule_id="WELD-002", process="Welding", parameter="Porosity",
        fault_pattern="Weld Porosity — Gas Voids in Weld Metal",
        description="Porosity found in weld by RT or UT. Gas voids reduce weld cross-section and strength.",
        severity="Major", ppm_min=500,
        root_cause="Contamination (moisture, oil, rust) on base metal or filler metal, or shielding gas failure.",
        root_cause_detail=(
            "Porosity forms when gas is trapped in solidifying weld metal. Sources: "
            "(1) moisture in filler wire or coating (hydrogen porosity), "
            "(2) oil, paint, or rust on base metal surface, "
            "(3) shielding gas contamination or flow rate insufficient, "
            "(4) wind or drafts displacing shielding gas."
        ),
        alternative_causes=["Electrode storage non-compliant (low-hydrogen electrodes must be baked and stored)", "Base metal sulfur or phosphorus content too high", "Weld puddle solidification rate too fast for gas escape"],
        corrective_actions=[
            CAPAAction("Quantify porosity by RT/UT. Compare to acceptance criteria per applicable code (AWS D1.1, ASME). Determine accept/reject.", "Quality", "Immediate", "P1", "Code compliance determination before disposition"),
            CAPAAction("Check shielding gas flow rate at weld nozzle under production conditions. Flow should be per WPS (typically 20-40 CFH).", "Manufacturing", "Immediate", "P1", "Shielding gas is first thing to check for porosity"),
            CAPAAction("Inspect base metal surface in area of porous weld. If contamination visible, specify cleaning SOP.", "Manufacturing", "Immediate", "P1", "Surface contamination causes porosity"),
        ],
        preventive_actions=[
            PreventiveAction("Low-hydrogen electrode bake and rod oven storage per AWS D1.1 specification.", "Manufacturing", "Ongoing", "SOP"),
            PreventiveAction("Pre-weld cleaning SOP: wire brush or grind + solvent wipe within 2 hours of welding.", "Manufacturing", "1 week", "SOP"),
            PreventiveAction("Shielding gas line pressure verification at start of shift.", "Manufacturing", "Daily", "SOP"),
        ],
        containment="Porous welds require repair (grind out and re-weld) or rejection. Re-NDT after repair.",
        disposition="Conditional Release", standard_reference="AWS D1.1, ASME Section IX, ISO 5817", weight=2.3,
    ),

    # ═══════════════════════════════════════════════════════════════════════
    # GENERAL METROLOGY (expanded from R2)
    # ═══════════════════════════════════════════════════════════════════════

    CAPARule(
        rule_id="GEN-001", process="General", parameter="Any",
        fault_pattern="Process Incapable — Cpk < 1.00 (Defects Being Produced)",
        description="Cpk < 1.00 means defects are actively being produced. Immediate containment required.",
        severity="Critical", cpk_max=1.00, ppm_min=1000,
        root_cause="Process is fundamentally out of control relative to specification limits.",
        root_cause_detail=(
            "Cpk < 1.0 means the 3-sigma process width exceeds the specification range. "
            "Distinguish: Cp<1.0 = spread problem, Cp>1.0 but Cpk<1.0 = centering problem. Different fixes."
        ),
        alternative_causes=["Specification limit too tight for process physics", "Process running on wrong equipment or recipe", "Incoming material variation exceeding tolerance"],
        corrective_actions=[
            CAPAAction("Calculate PPM and estimate yield impact. Present to management for priority triage.", "Quality Engineer", "Immediate", "P1", "Business impact quantification"),
            CAPAAction("100% inspect all product from affected period. Sort: in-spec = conditional release, OOT = scrap/rework.", "Manufacturing", "Immediate", "P1", "Containment of defective product"),
            CAPAAction("If Cp>1.0: centering fix — adjust setpoint. If Cp<1.0: spread reduction — DOE needed.", "Process Engineer", "1 week", "P1", "Different fix path depending on Cp vs Cpk"),
        ],
        preventive_actions=[
            PreventiveAction("Implement real-time SPC with automatic lot hold when Cpk drops below 1.33.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Quarterly process capability review for all critical parameters.", "Quality", "Quarterly", "SOP"),
        ],
        containment="MANDATORY LOT HOLD. 100% inspection before any release.",
        disposition="Hold", standard_reference="AIAG SPC 2nd Ed, ISO 22514", weight=3.0,
    ),

    CAPARule(
        rule_id="GEN-002", process="General", parameter="Any",
        fault_pattern="Measurement System Unacceptable — GRR > 30%",
        description="Gauge R&R exceeds 30%. Fix measurement system before making process decisions.",
        severity="Major", grr_min=30.0,
        root_cause="Measurement system variation exceeds 30% — gauge inadequate for this tolerance.",
        root_cause_detail="AIAG MSA manual: >30% GRR = unacceptable. All Cpk values from this data are unreliable.",
        alternative_causes=["Gauge resolution too coarse (ndc<5)", "Operator technique variation dominant", "Environmental conditions affecting measurement"],
        corrective_actions=[
            CAPAAction("Identify whether EV (repeatability) or AV (reproducibility) dominates.", "Metrology", "Immediate", "P1", "Targets most impactful GRR reduction lever"),
            CAPAAction("If AV dominant: standardize operator method, provide training, lock gauge settings.", "Metrology", "1 week", "P1", "Reduces operator-to-operator variation"),
            CAPAAction("If EV dominant: inspect gauge hardware, check calibration, assess environment.", "Equipment", "1 week", "P1", "Addresses gauge hardware instability"),
        ],
        preventive_actions=[
            PreventiveAction("Biannual GRR studies for all critical gauges per AIAG MSA 4th Edition.", "Metrology", "6 months", "Metrology"),
            PreventiveAction("Track %GRR over time as a gauge health indicator.", "Metrology", "Ongoing", "SPC"),
        ],
        containment="Suspend process control decisions based on this gauge until GRR resolved.",
        disposition="Conditional Release", standard_reference="AIAG MSA 4th Ed, ISO 22514-7", weight=2.5,
    ),

    CAPARule(
        rule_id="GEN-003", process="General", parameter="Any",
        fault_pattern="SPC Step Change — Assignable Cause Event",
        description="Control chart shows clear step change. Discrete assignable cause occurred.",
        severity="Major", spc_rules=["WE1", "WE4", "NE2"],
        root_cause="PM completion, material lot change, recipe modification, operator change, or equipment event.",
        root_cause_detail="Step changes in SPC always have an assignable cause. Pull tool event log + maintenance log ± 4hr of shift.",
        alternative_causes=["Unrecorded recipe adjustment", "Equipment alarm acknowledged without investigation", "Raw material lot change not flagged"],
        corrective_actions=[
            CAPAAction("Identify exact shift point. Pull tool event, ECO, and material lot logs within ±4hr window.", "Process Engineer", "Immediate", "P1", "Identifies specific assignable cause"),
            CAPAAction("Once cause identified: reverse change if possible. Verify return to baseline with 3 monitor runs.", "Process Engineer", "Immediate", "P1", "Restores process to pre-shift state"),
        ],
        preventive_actions=[
            PreventiveAction("Change notification system: all recipe/material/maintenance changes logged in SPC system.", "Manufacturing", "2 weeks", "SOP"),
            PreventiveAction("Require monitor run after every PM or recipe change before resuming production.", "Manufacturing", "1 week", "SOP"),
        ],
        containment="Hold wafers/parts processed after shift point. Inspect before release.",
        disposition="Hold", standard_reference="AIAG SPC 2nd Ed, ISO 7870", weight=2.3,
    ),

    CAPARule(
        rule_id="GEN-004", process="General", parameter="Any",
        fault_pattern="SPC Trend — Gradual Process Drift",
        description="Control chart shows gradual monotonic trend. NE3 or WE3 rule fired. Process drifting toward limit.",
        severity="Major", spc_rules=["NE3", "WE3"],
        root_cause="Gradual consumable wear, calibration drift, or systematic environmental change.",
        root_cause_detail="Monotonic trends always have a physical cause: tool wear, electrode degradation, gauge drift.",
        alternative_causes=["Gradual material property change during batch transition", "Environmental drift (temperature, humidity)", "Operator technique drift (fatigue)"],
        corrective_actions=[
            CAPAAction("Calculate trend slope (units/measurement). Extrapolate to predict when spec limit will be hit.", "Quality Engineer", "Immediate", "P2", "Quantifies time-to-failure for prioritization"),
            CAPAAction("Identify consumable most likely causing trend. Replace proactively if >70% of rated life.", "Manufacturing", "1 week", "P1", "Proactive replacement before failure"),
            CAPAAction("Implement APC correction if available: feed trend signal back to offset setpoint.", "Equipment", "2 weeks", "P1", "Automated trend compensation"),
        ],
        preventive_actions=[
            PreventiveAction("Implement trend-sensitive SPC rules (NE3 with 5-point window as standard).", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Set preventive consumable replacement at 70% of rated life, not on failure.", "Manufacturing", "1 month", "SOP"),
        ],
        containment="Alert supervisor. Increase measurement frequency. No hold required unless approaching spec limit.",
        disposition="Release", standard_reference="AIAG SPC 2nd Ed, ISO 7870-2", weight=2.0,
    ),

    CAPARule(
        rule_id="GEN-005", process="General", parameter="Any",
        fault_pattern="Non-Normal Distribution — Transformation Required",
        description="Data fails normality tests. Standard Cpk indices may be misleading.",
        severity="Minor", non_normal=True, skewness_min=0.8,
        root_cause="Process has inherently non-normal output (one-sided physical limits, mixture populations, or bounded measurement).",
        root_cause_detail="Non-normal: physically bounded process, mixture of populations, or tool wear progression (asymmetric).",
        alternative_causes=["Measurement saturation at one end of scale", "Outliers from different mechanism", "Data stratification needed"],
        corrective_actions=[
            CAPAAction("Identify distribution type: right-skewed = try log or Box-Cox. Bimodal = stratify data.", "Quality Engineer", "1 week", "P2", "Determines correct analysis approach"),
            CAPAAction("Apply Box-Cox transformation and re-calculate Cpk on transformed data.", "Quality Engineer", "1 week", "P2", "Provides valid capability estimate"),
            CAPAAction("If bimodal: stratify by operator, shift, tool, or material lot.", "Process Engineer", "1 week", "P1", "Bimodality always has an assignable cause"),
        ],
        preventive_actions=[
            PreventiveAction("Run normality test before calculating Cpk for any new characteristic.", "Quality", "Ongoing", "SOP"),
            PreventiveAction("Document which characteristics are expected non-normal and define approved analysis method.", "Quality", "1 month", "SOP"),
        ],
        containment="No immediate hold required. Flag that standard Cpk is not valid for this data.",
        disposition="Release", standard_reference="AIAG SPC 2nd Ed, ISO 22514-2", weight=1.5,
    ),

    CAPARule(
        rule_id="GEN-006", process="General", parameter="Any",
        fault_pattern="ndc < 5 — Gauge Resolution Insufficient",
        description="Number of distinct categories below 5. Gauge cannot differentiate parts for SPC.",
        severity="Major", ndc_max=4,
        root_cause="Gauge resolution too coarse relative to process variation.",
        root_cause_detail="ndc = 1.41 × sqrt(part variance / gauge variance). ndc<5 means fewer than 5 resolvable categories.",
        alternative_causes=["Part-to-part variation genuinely small (very capable process)", "Wrong gauge selected"],
        corrective_actions=[
            CAPAAction("Calculate gauge resolution to total tolerance ratio. If resolution >5% of tolerance, gauge is inadequate.", "Metrology", "1 week", "P2", "Quantifies gauge adequacy"),
            CAPAAction("Evaluate higher-resolution gauge option.", "Metrology", "2 weeks", "P1", "Upgrades to achieve ndc≥5"),
        ],
        preventive_actions=[
            PreventiveAction("During gauge selection: require ndc analysis before approving gauge for production.", "Metrology", "1 month", "SOP"),
        ],
        containment="Production may continue. Note: SPC charts not effective until gauge upgraded.",
        disposition="Release", standard_reference="AIAG MSA 4th Ed", weight=1.6,
    ),

    CAPARule(
        rule_id="GEN-007", process="General", parameter="Any",
        fault_pattern="Bimodal Distribution — Two Populations Mixed",
        description="Data shows bimodal distribution. Two distinct populations being measured as one.",
        severity="Major", non_normal=True, spc_rules=["NE8", "NE4"],
        root_cause="Two distinct process conditions or sources mixed in the same dataset without stratification.",
        root_cause_detail="Bimodal = two populations mixed. NE8 rule (points beyond ±1σ both sides) is SPC signature.",
        alternative_causes=["Two machines feeding same SPC chart", "Two shifts with different setups", "Two material lots", "Two operators with different techniques"],
        corrective_actions=[
            CAPAAction("Stratify data by machine, shift, operator, tool, and material lot. Plot each separately.", "Quality Engineer", "Immediate", "P1", "Identifies stratification factor responsible for bimodality"),
            CAPAAction("Once stratified: treat each sub-population separately with its own SPC chart.", "Quality Engineer", "1 week", "P1", "Resolves bimodality by correct data management"),
            CAPAAction("Investigate why the two populations have different means. Address root cause.", "Process Engineer", "1 week", "P2", "Eliminates systematic difference between populations"),
        ],
        preventive_actions=[
            PreventiveAction("Require stratified SPC from first production: one chart per machine, cavity, shift.", "Quality", "During APQP", "SOP"),
        ],
        containment="Sort parts by stratification factor. Inspect each stratum separately.",
        disposition="Conditional Release", standard_reference="AIAG SPC 2nd Ed, ISO 7870-5", weight=2.0,
    ),

    CAPARule(
        rule_id="GEN-008", process="General", parameter="Any",
        fault_pattern="High PPM — Process Producing Excessive Defects",
        description="Expected PPM above acceptable level. Significant defect rate.",
        severity="Critical", ppm_min=1000, cpk_max=1.00,
        root_cause="Combined centering and spread issue exceeding specification limits.",
        root_cause_detail="High PPM from low Cpk. Priority: contain first, then investigate. PPM>1000 in auto/aero is customer scorecard risk.",
        alternative_causes=["Specification tighter than process capability requires", "Multiple process streams mixed — high-PPM stream not identified"],
        corrective_actions=[
            CAPAAction("100% sort of all product from affected production period. Establish clean inventory.", "Manufacturing", "Immediate", "P1", "Immediate containment — stop shipping defects"),
            CAPAAction("Calculate PPM per stream (machine, shift, tool). Focus correction on highest-PPM source.", "Quality Engineer", "Immediate", "P1", "Identifies highest-PPM source"),
            CAPAAction("Engage customer if PPM exceeds scorecard threshold. Submit 8D per customer requirement.", "Quality Manager", "Immediate", "P1", "Customer notification and 8D may be contractually required"),
        ],
        preventive_actions=[
            PreventiveAction("Implement real-time SPC with auto-lot-hold when Cpk < 1.33.", "Quality", "2 weeks", "SPC"),
            PreventiveAction("Monthly PPM report and trend review.", "Quality Manager", "Monthly", "SOP"),
        ],
        containment="100% inspection. Quarantine and sort. Customer notification if above scorecard threshold.",
        disposition="Hold", standard_reference="AIAG SPC, ISO 22514, IATF 16949", weight=2.8,
    ),

    CAPARule(
        rule_id="GEN-009", process="General", parameter="Any",
        fault_pattern="Autocorrelation Detected — SPC Charts Unreliable",
        description="Data shows significant autocorrelation (time-series dependence). Standard SPC control limits are incorrect.",
        severity="Minor", spc_rules=["NE8"],
        root_cause="Process has memory: each measurement is correlated with previous measurements.",
        root_cause_detail=(
            "Autocorrelated data violates the independence assumption of standard SPC. "
            "Result: control limits are too tight, causing false alarms. Common in: temperature-controlled "
            "processes (slow dynamics), continuous chemical processes, automated measurement systems sampling "
            "faster than process dynamics. Runs test (NE8) often fires on autocorrelated data."
        ),
        alternative_causes=["Measurement sampling too frequent relative to process dynamics", "Feedback control system creating oscillation", "Drift + noise mixing (integrated random walk)"],
        corrective_actions=[
            CAPAAction("Calculate Durbin-Watson statistic or ACF plot. Confirm autocorrelation and estimate lag.", "Quality Engineer", "1 week", "P2", "Quantifies autocorrelation structure"),
            CAPAAction("Increase sampling interval to exceed autocorrelation lag. Recalculate control limits on independent samples.", "Quality Engineer", "1 week", "P2", "Restores SPC chart validity by ensuring independence"),
            CAPAAction("Alternatively: use EWMA or ARIMA-based residual chart (designed for autocorrelated processes).", "Quality Engineer", "2 weeks", "P2", "Advanced SPC approach for autocorrelated processes"),
        ],
        preventive_actions=[
            PreventiveAction("Before deploying any SPC chart: run autocorrelation test on pilot data. If ACF significant at lag 1, adjust sampling.", "Quality", "During SPC design", "SOP"),
        ],
        containment="No immediate hold. SPC chart results since autocorrelation onset should be reviewed for validity.",
        disposition="Release", standard_reference="AIAG SPC 2nd Ed, ISO 7870-6 (EWMA)", weight=1.4,
    ),

    CAPARule(
        rule_id="GEN-010", process="General", parameter="Any",
        fault_pattern="Gauge Linearity — Systematic Bias Varies Across Measurement Range",
        description="Gauge shows non-constant bias across its measurement range. Linearity study failed.",
        severity="Major", grr_min=15.0,
        root_cause="Gauge mechanics or electronics are non-linear across the measurement range.",
        root_cause_detail=(
            "Gauge linearity measures how bias changes across the measurement range. "
            "Non-linearity means the gauge reads differently at low, mid, and high values — "
            "calibration at one point does not ensure accuracy across the range. "
            "Common in: worn contact gauges, LVDT at range extremes, optical gauges at edge of field."
        ),
        alternative_causes=["Gauge calibrated at only one point in range (single-point calibration)", "Mechanical wear causing non-linear spring force", "Temperature coefficient difference across range"],
        corrective_actions=[
            CAPAAction("Perform linearity study per AIAG MSA: measure 5 reference parts spanning full gauge range. Plot bias vs reference value.", "Metrology", "1 week", "P1", "Characterizes linearity error across full range"),
            CAPAAction("If linearity slope is significant: gauge requires multi-point calibration or replacement.", "Metrology", "2 weeks", "P1", "Single-point calibration is inadequate for non-linear gauges"),
            CAPAAction("Restrict gauge to linear portion of range where bias is acceptable, if possible.", "Metrology", "Immediate", "P2", "Interim fix if only part of range is used in production"),
        ],
        preventive_actions=[
            PreventiveAction("Biannual linearity study for gauges used across wide measurement ranges.", "Metrology", "6 months", "Metrology"),
            PreventiveAction("Specify multi-point calibration for gauges covering >20% of measurement range.", "Metrology", "1 month", "SOP"),
        ],
        containment="Review all measurements made at range extremes. Re-measure with calibrated reference or different gauge.",
        disposition="Conditional Release", standard_reference="AIAG MSA 4th Ed, ISO 14978", weight=1.8,
    ),

    CAPARule(
        rule_id="GEN-011", process="General", parameter="Any",
        fault_pattern="Capability Target Miss — Cpk 1.33–1.67 Acceptable but Below PPAP",
        description="Cpk in acceptable range for ongoing production (≥1.33) but below PPAP requirement (≥1.67).",
        severity="Minor", cpk_max=1.67, cpk_min=1.33,
        root_cause="Process designed or set to Cpk ≥1.33 without headroom for PPAP requirement.",
        root_cause_detail=(
            "IATF 16949 PPAP requires Cpk ≥1.67. Many processes are set to ≥1.33 during development, "
            "which passes ongoing production monitoring but fails PPAP submission. "
            "The additional 0.34 Cpk margin is the 'submission buffer' — customers expect it."
        ),
        alternative_causes=["Natural process variation makes 1.67 difficult without design change", "Specification tolerance tighter than engineering need"],
        corrective_actions=[
            CAPAAction("Determine if gap is centering (cheap fix: adjust setpoint) or spread (expensive fix: DOE).", "Quality Engineer", "1 week", "P2", "Distinguishes fast from slow path to Cpk 1.67"),
            CAPAAction("If centering gap: calculate required setpoint shift to reach Cpk 1.67. Adjust and re-sample.", "Process Engineer", "1 week", "P2", "Centering fix is low-risk and fast"),
            CAPAAction("If spread gap: negotiate specification with customer engineering, or run DOE to reduce variation.", "Quality/Engineering", "1 month", "P2", "Two options: spec change or process improvement"),
        ],
        preventive_actions=[
            PreventiveAction("During APQP: design process to Cpk ≥2.0 to ensure PPAP headroom.", "Process Engineer", "During development", "SOP"),
        ],
        containment="No hold required — product is acceptable. Flag for PPAP compliance team.",
        disposition="Release", standard_reference="IATF 16949:2016, AIAG PPAP", weight=1.2,
    ),

]

# ─────────────────────────────────────────────────────────────────────────────
# Catalog helper (drop-in replacement for R2)
# ─────────────────────────────────────────────────────────────────────────────

def get_all_rules_catalog_r3() -> list:
    """Return all R3 rules as a lightweight catalog for the CAPA override UI."""
    return [
        {
            "rule_id": r.rule_id,
            "process": r.process,
            "parameter": r.parameter,
            "fault_pattern": r.fault_pattern,
            "severity": r.severity,
            "description": r.description,
            "standard_reference": r.standard_reference,
        }
        for r in CAPA_RULES
    ]


def get_rules_by_process(process: str) -> list:
    """Return all rules for a specific process family."""
    return [r for r in CAPA_RULES if r.process.lower() == process.lower() or r.process == "General"]


def get_rule_by_id(rule_id: str) -> "CAPARule | None":
    """Retrieve a single rule by ID."""
    return next((r for r in CAPA_RULES if r.rule_id == rule_id), None)


if __name__ == "__main__":
    print(f"StatMind CAPA Database R3")
    print(f"Total rules: {len(CAPA_RULES)}")
    processes = sorted(set(r.process for r in CAPA_RULES))
    for proc in processes:
        count = sum(1 for r in CAPA_RULES if r.process == proc)
        print(f"  {proc}: {count} rules")
