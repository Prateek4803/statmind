"""
StatMind — Session 5: CAPA Rule Database
Semiconductor process failure patterns → structured CAPA actions
No LLM required — fully deterministic rule-based engine
"""

from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CAPAAction:
    action: str
    owner: str           # Process Engineer | Metrology | Equipment | Manufacturing
    timeline: str        # Immediate | 1 week | 2 weeks | 1 month
    priority: str        # P1 | P2 | P3
    expected_impact: str

@dataclass
class PreventiveAction:
    action: str
    owner: str
    timeline: str
    system_change: str   # SPC | APC | SOP | Recipe | Training | PM | Metrology

@dataclass
class CAPARule:
    rule_id: str
    process: str             # Etch | CMP | Lithography | Diffusion | Metrology | General
    parameter: str           # CD | Etch_Rate | Thickness | Uniformity | Overlay | etc.
    fault_pattern: str       # Short label shown in UI
    description: str         # Full description of the failure mode
    severity: str            # Critical | Major | Minor

    # Trigger conditions (None = not evaluated)
    cpk_max: Optional[float]         # triggers if Cpk BELOW this
    cpk_min: Optional[float]         # triggers if Cpk ABOVE this (for "too tight" cases)
    ppk_max: Optional[float]
    cp_cpk_gap_min: Optional[float]  # Cp-Cpk gap triggers centering rules
    ppm_min: Optional[float]         # triggers if PPM above this
    spc_rules: list                  # WE1/WE2/WE3/WE4/NE2/NE3 etc — any match triggers
    grr_min: Optional[float]         # triggers if %GRR above this
    ndc_max: Optional[int]           # triggers if ndc below this
    non_normal: bool                 # triggers if normality verdict is Non-Normal
    skewness_min: Optional[float]    # triggers if |skewness| above this

    # CAPA content
    root_cause: str
    root_cause_detail: str
    alternative_causes: list
    corrective_actions: list         # list of CAPAAction
    preventive_actions: list         # list of PreventiveAction
    containment: str
    disposition: str                 # Hold | Release | Conditional Release | Scrap | Rework

    # Scoring weight (higher = ranked first when multiple rules match)
    weight: float = 1.0


# ── RULE DATABASE ─────────────────────────────────────────────────────────────

CAPA_RULES: list[CAPARule] = [

    # ═══════════════════════════════════════════════════════════
    # ETCH PROCESS
    # ═══════════════════════════════════════════════════════════

    CAPARule(
        rule_id="ETCH-001",
        process="Etch", parameter="CD",
        fault_pattern="CD Low Cpk — Process Centering",
        description="Critical Dimension (CD) shows adequate potential (Cp) but poor centering (Cpk). Process mean is offset from target.",
        severity="Major",
        cpk_max=1.33, cpk_min=None, ppk_max=1.33, cp_cpk_gap_min=0.3,
        ppm_min=None, spc_rules=[], grr_min=None, ndc_max=None,
        non_normal=False, skewness_min=None,
        root_cause="Etch bias offset — process mean shifted from target CD due to recipe parameter drift (RF power, pressure, or gas flow).",
        root_cause_detail="Large Cp-Cpk gap confirms spread is adequate but centering is the issue. Most likely cause is incremental RF power drift, chamber wall conditioning change, or gas flow calibration offset.",
        alternative_causes=[
            "Photoresist CD offset carrying through to etch",
            "Focus/dose drift in upstream litho step",
            "Chamber seasoning state change after PM",
        ],
        corrective_actions=[
            CAPAAction("Measure current etch bias (CD_etch - CD_resist) across 5 wafers and compare to baseline. Adjust RF power or bias voltage to re-center within ±2nm of target.", "Process Engineer", "Immediate", "P1", "Expected Cpk improvement from current to ≥1.33 after centering"),
            CAPAAction("Run DOE on etch time ±10% to characterize CD sensitivity. Update recipe setpoint.", "Process Engineer", "1 week", "P1", "Quantifies optimal recipe window"),
            CAPAAction("Pull SEM CD data from last 30 days and correlate with chamber RF hours. Identify drift onset.", "Metrology", "1 week", "P2", "Identifies if drift is gradual or step-change"),
        ],
        preventive_actions=[
            PreventiveAction("Add CD bias SPC chart with ±3σ limits. Alarm on WE1 violation.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Add RF power and DC bias to APC feedback loop. Update APC model with new setpoints.", "Equipment", "1 month", "APC"),
            PreventiveAction("Update SOP to include etch bias measurement after each chamber PM.", "Manufacturing", "2 weeks", "SOP"),
        ],
        containment="Hold wafers processed in last 24hr for CD SEM verification before release.",
        disposition="Conditional Release",
        weight=2.0,
    ),

    CAPARule(
        rule_id="ETCH-002",
        process="Etch", parameter="Etch_Rate",
        fault_pattern="Etch Rate Drift — SPC Shift Pattern",
        description="Etch rate showing sustained shift or trend on control chart. Nelson NE2/NE3 or WE4 rules violated.",
        severity="Critical",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=["NE2", "NE3", "WE4", "WE1"],
        grr_min=None, ndc_max=None, non_normal=False, skewness_min=None,
        root_cause="Assignable cause: electrode erosion, chamber wall polymer buildup, or gas flow controller drift causing sustained etch rate change.",
        root_cause_detail="Sustained shift (NE2/WE4) indicates a step-change assignable cause — most likely a PM event, consumable swap, or recipe modification. Trend (NE3) indicates gradual degradation: electrode wear or wall conditioning drift.",
        alternative_causes=[
            "Helium backside cooling pressure change affecting wafer temperature",
            "ESC (electrostatic chuck) temperature drift",
            "Source gas purity change or cylinder swap",
        ],
        corrective_actions=[
            CAPAAction("Identify alarm trigger point on chart. Correlate with maintenance log, consumable changes, or recipe modifications within ±8hr window.", "Process Engineer", "Immediate", "P1", "Identifies root cause for step change"),
            CAPAAction("Run qualification wafers to measure current etch rate vs. target. If >5% delta, perform chamber clean and re-qualification.", "Equipment", "Immediate", "P1", "Restores etch rate to baseline"),
            CAPAAction("Inspect electrode condition. If >80% of rated life, replace electrode and re-season chamber.", "Equipment", "1 week", "P2", "Eliminates electrode erosion contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Implement EWMA SPC on etch rate with λ=0.2. Tighter detection of small shifts.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Add etch rate to PM checklist — must be within ±3% of baseline before wafer production resumes.", "Equipment", "2 weeks", "PM"),
            PreventiveAction("Implement APC endpoint detection to correct for etch rate drift in real-time.", "Equipment", "1 month", "APC"),
        ],
        containment="Pull last 50 wafers from chamber for etch depth verification (ellipsometry or cross-section). Segregate suspect lot.",
        disposition="Hold",
        weight=2.5,
    ),

    CAPARule(
        rule_id="ETCH-003",
        process="Etch", parameter="Uniformity",
        fault_pattern="Non-Normal Etch Uniformity — Bimodal Distribution",
        description="Etch uniformity data is non-normal, indicating possible bimodal distribution from two distinct process states.",
        severity="Major",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=["NE8", "NE4"],
        grr_min=None, ndc_max=None, non_normal=True, skewness_min=None,
        root_cause="Two distinct process states (bimodal): alternating chamber conditioning states, wafer position effects (center vs. edge), or intermittent gas flow switching.",
        root_cause_detail="Non-normality combined with NE8 (points beyond ±1σ both sides) is the signature of a mixture distribution — two populations being measured as one. Most common cause in etch: alternating wafer boat positions, two gas flow modes, or periodic chamber reconditioning.",
        alternative_causes=[
            "Wafer carrier slot position effect (top vs. bottom of boat)",
            "Alternating day/night shift process differences",
            "ESC thermal cycling causing periodic chucking variation",
        ],
        corrective_actions=[
            CAPAAction("Stratify uniformity data by wafer slot position, shift, and day of week. Identify which stratification explains the bimodality.", "Process Engineer", "Immediate", "P1", "Identifies source population causing bimodal distribution"),
            CAPAAction("Run 10 wafers labeling each with slot position. Map uniformity spatially using 49-point measurement.", "Metrology", "1 week", "P1", "Confirms if position effect is root cause"),
            CAPAAction("If shift effect confirmed, standardize gas purge and seasoning wafer procedure between shifts.", "Manufacturing", "1 week", "P2", "Eliminates between-shift variation"),
        ],
        preventive_actions=[
            PreventiveAction("Implement stratified control charts by slot position or shift.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Add seasoning wafer procedure to start-of-shift SOP.", "Manufacturing", "1 week", "SOP"),
            PreventiveAction("Train all operators on chamber conditioning sensitivity.", "Manufacturing", "2 weeks", "Training"),
        ],
        containment="Quarantine wafers from affected batch. Sort by slot position and re-measure uniformity before release.",
        disposition="Conditional Release",
        weight=1.8,
    ),

    CAPARule(
        rule_id="ETCH-004",
        process="Etch", parameter="CD",
        fault_pattern="Etch CD — High GRR, Unreliable Measurement",
        description="Gauge R&R exceeds 30%, meaning measurement system variation is too high relative to process variation. Cannot trust CD measurements.",
        severity="Major",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=[],
        grr_min=30.0, ndc_max=4, non_normal=False, skewness_min=None,
        root_cause="Measurement system inadequacy — SEM recipe instability, sample tilt, recipe-to-recipe matching, or operator-dependent SEM focus adjustment.",
        root_cause_detail="High %GRR means the measurement noise is masking real process signal. Cpk calculated from this data is unreliable. Fix measurement system before making process changes.",
        alternative_causes=[
            "SEM beam condition drift between operators",
            "Algorithm difference between measurement recipes",
            "Part fixturing inconsistency causing different measurement angles",
        ],
        corrective_actions=[
            CAPAAction("Re-run GRR study with standardized SEM recipe. Lock focus, beam current, and magnification. Check if %GRR improves below 10%.", "Metrology", "Immediate", "P1", "Confirms measurement system as root cause"),
            CAPAAction("If reproducibility (AV) dominates: train all operators on SEM operation SOP. Implement recipe lock to prevent operator adjustments.", "Metrology", "1 week", "P1", "Reduces operator-to-operator variation"),
            CAPAAction("If repeatability (EV) dominates: inspect SEM column condition. Check beam current stability over 4hr. Schedule column maintenance if drift >2%.", "Equipment", "1 week", "P1", "Addresses gauge hardware instability"),
        ],
        preventive_actions=[
            PreventiveAction("Implement weekly SEM gauge check using golden wafer. Track %bias over time.", "Metrology", "2 weeks", "Metrology"),
            PreventiveAction("Lock SEM recipe parameters. Require Metrology Engineer sign-off for any recipe changes.", "Metrology", "1 week", "SOP"),
            PreventiveAction("Add SEM beam current to equipment PM checklist.", "Equipment", "1 month", "PM"),
        ],
        containment="Suspend process control decisions based on current CD data until measurement system is qualified.",
        disposition="Hold",
        weight=2.2,
    ),

    CAPARule(
        rule_id="ETCH-005",
        process="Etch", parameter="Etch_Rate",
        fault_pattern="Etch Rate — Alternating Pattern (Stratification)",
        description="Etch rate alternates up-down in regular pattern. NE4 rule violation — indicates two interspersed populations.",
        severity="Minor",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=["NE4"],
        grr_min=None, ndc_max=None, non_normal=False, skewness_min=None,
        root_cause="Stratification: two alternating process conditions being measured together — alternating wafer lots, alternating tool qualification states, or alternating shift practices.",
        root_cause_detail="Regular alternating pattern almost always means two distinct sub-populations are interleaved in the data stream. Check if alternation correlates with wafer lot alternation, shift rotation, or periodic tool cleaning cycles.",
        alternative_causes=[
            "Alternating gas cylinder usage (A/B manifold switching)",
            "Alternating measurement tool (metrology tool A vs B)",
            "Every-other-wafer carrier effect",
        ],
        corrective_actions=[
            CAPAAction("Plot etch rate colored by lot ID, shift, and tool. Identify which stratification factor explains the alternation.", "Process Engineer", "Immediate", "P2", "Identifies stratification source"),
            CAPAAction("Check if two measurement tools are being used alternately. Run back-to-back on single tool to confirm.", "Metrology", "Immediate", "P2", "Rules out measurement stratification"),
        ],
        preventive_actions=[
            PreventiveAction("Segregate SPC data by tool, shift, and lot type to prevent artificial stratification.", "Process Engineer", "1 week", "SPC"),
        ],
        containment="No immediate hold required — monitor and investigate.",
        disposition="Release",
        weight=1.2,
    ),

    # ═══════════════════════════════════════════════════════════
    # CMP PROCESS
    # ═══════════════════════════════════════════════════════════

    CAPARule(
        rule_id="CMP-001",
        process="CMP", parameter="Removal_Rate",
        fault_pattern="CMP Removal Rate — Low Cpk with Centering Issue",
        description="CMP removal rate capability is inadequate. Process is off-center from target removal rate.",
        severity="Major",
        cpk_max=1.33, cpk_min=None, ppk_max=1.33, cp_cpk_gap_min=0.25,
        ppm_min=None, spc_rules=[], grr_min=None, ndc_max=None,
        non_normal=False, skewness_min=None,
        root_cause="Slurry delivery rate offset, pad conditioning aggressiveness change, or platen pressure drift causing removal rate to deviate from target.",
        root_cause_detail="Centering issue (Cp>>Cpk) in CMP most commonly caused by slurry flow rate calibration drift, conditioner arm wear changing effective pad surface area, or platen temperature change altering slurry viscosity.",
        alternative_causes=[
            "Pad age effect — removal rate decreasing as pad glazes over",
            "Slurry mixing ratio drift (oxidizer concentration)",
            "Carrier film wear affecting pressure uniformity",
        ],
        corrective_actions=[
            CAPAAction("Measure actual slurry flow rate at point of use (not just controller setpoint). Recalibrate flow controller if >5% deviation.", "Equipment", "Immediate", "P1", "Eliminates slurry delivery as cause"),
            CAPAAction("Run removal rate test wafers before and after conditioner replacement. Quantify conditioner contribution.", "Process Engineer", "1 week", "P1", "Expected removal rate centering improvement of 5-15 Å/min"),
            CAPAAction("Check platen temperature stability over 4hr. If drift >1°C, inspect chiller system.", "Equipment", "1 week", "P2", "Ensures thermal contribution is eliminated"),
        ],
        preventive_actions=[
            PreventiveAction("Implement removal rate SPC with EWMA chart. Alert when removal rate drifts >3% from target.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Add slurry flow rate to real-time APC. Feed removal rate data back to adjust polish time.", "Equipment", "1 month", "APC"),
            PreventiveAction("Add pad age (wafers polished) as a co-variable in removal rate model. Implement pad life endpoint.", "Process Engineer", "1 month", "Recipe"),
        ],
        containment="Measure oxide thickness on all wafers from affected lot. Sort by thickness — wafers outside ±3% of target to rework queue.",
        disposition="Conditional Release",
        weight=2.0,
    ),

    CAPARule(
        rule_id="CMP-002",
        process="CMP", parameter="WIWNU",
        fault_pattern="CMP Within-Wafer Non-Uniformity — High Spread",
        description="WIWNU (within-wafer non-uniformity) shows high variation. Cpk low with no major centering issue (Cp ≈ Cpk).",
        severity="Major",
        cpk_max=1.33, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=[], grr_min=None, ndc_max=None,
        non_normal=False, skewness_min=None,
        root_cause="Pressure zone non-uniformity in CMP carrier head or pad surface degradation causing radially non-uniform removal.",
        root_cause_detail="When Cp ≈ Cpk (centered but spread is the problem), CMP WIWNU points to carrier head membrane wear, retaining ring wear, or edge exclusion effects. Also check pad groove pattern wear.",
        alternative_causes=[
            "Pad glazing — uneven conditioning across pad radius",
            "Carrier membrane air leak causing uneven pressure zones",
            "Wafer backside contamination affecting chuck uniformity",
        ],
        corrective_actions=[
            CAPAAction("Run 49-point uniformity map on 5 wafers. Identify if non-uniformity is center-fast, edge-fast, or random. Pattern determines root cause.", "Metrology", "Immediate", "P1", "Identifies spatial signature of non-uniformity"),
            CAPAAction("Inspect carrier head membrane for wear or pinhole leaks. Measure pressure zone response at each zone individually.", "Equipment", "1 week", "P1", "Eliminates carrier head as root cause"),
            CAPAAction("Replace pad if pad age > 75% of rated life or if conditioning rate shows >10% degradation.", "Equipment", "1 week", "P2", "Restores pad surface uniformity"),
        ],
        preventive_actions=[
            PreventiveAction("Implement 49-point uniformity SPC chart. Track center-edge difference as separate control parameter.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Add carrier head membrane inspection to every-50-wafer PM routine.", "Equipment", "2 weeks", "PM"),
            PreventiveAction("Track pad life in MES. Auto-alert at 70% pad life to schedule replacement during next planned downtime.", "Manufacturing", "1 month", "SOP"),
        ],
        containment="Map all wafers from affected lot. Wafers with WIWNU >3% to inspection queue.",
        disposition="Conditional Release",
        weight=1.9,
    ),

    CAPARule(
        rule_id="CMP-003",
        process="CMP", parameter="Removal_Rate",
        fault_pattern="CMP Removal Rate — Downward Trend (Pad Glazing)",
        description="CMP removal rate showing consistent downward trend on I-MR chart. NE3 (trend) or WE3 rule fired.",
        severity="Major",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=["NE3", "WE3", "WE4"],
        grr_min=None, ndc_max=None, non_normal=False, skewness_min=None,
        root_cause="Pad glazing: progressive reduction in pad micro-roughness reducing removal rate over pad lifetime. Conditioner aggressiveness may be insufficient.",
        root_cause_detail="Monotonic downward trend in CMP removal rate is the classic signature of pad glazing. The pad surface becomes smoother over time, reducing slurry transport and abrasive contact. Check conditioner arm sweep speed and downforce.",
        alternative_causes=[
            "Slurry concentration depletion over time (reservoir draining)",
            "Gradual slurry temperature increase reducing oxidizer effectiveness",
            "Progressive carrier film wear reducing effective polishing pressure",
        ],
        corrective_actions=[
            CAPAAction("Correlate alarm point with pad wafer count. If trend onset matches pad installation, glazing is confirmed. Replace pad immediately.", "Equipment", "Immediate", "P1", "Eliminates pad glazing — expected removal rate recovery to baseline"),
            CAPAAction("Increase conditioner downforce by 0.5 lbf and conditioner sweep speed by 10%. Run qualification wafers to confirm recovery.", "Process Engineer", "Immediate", "P1", "Aggressive conditioning may restore pad texture without full replacement"),
            CAPAAction("Check slurry reservoir level and mixing ratio. Verify oxidizer concentration is within spec.", "Equipment", "Immediate", "P2", "Rules out slurry degradation as co-contributing factor"),
        ],
        preventive_actions=[
            PreventiveAction("Implement pad life endpoint control: replace pad when removal rate drops >5% from initial value regardless of wafer count.", "Process Engineer", "1 week", "Recipe"),
            PreventiveAction("Add post-PM removal rate qualification wafer requirement — must be within ±3% of target before production resumes.", "Equipment", "2 weeks", "PM"),
            PreventiveAction("Chart conditioner effectiveness metric (removal rate / pad age) as leading indicator.", "Process Engineer", "2 weeks", "SPC"),
        ],
        containment="Pull wafers polished during trend period. Measure thickness — under-polished wafers to rework, over-polished to scrap review.",
        disposition="Conditional Release",
        weight=2.1,
    ),

    CAPARule(
        rule_id="CMP-004",
        process="CMP", parameter="Thickness",
        fault_pattern="CMP Post-Polish Thickness — Non-Normal (Skewed)",
        description="Post-CMP thickness distribution is skewed, indicating asymmetric process. Likely edge exclusion or die-level pattern density effect.",
        severity="Minor",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=[], grr_min=None, ndc_max=None,
        non_normal=True, skewness_min=0.8,
        root_cause="Pattern density effect: high-density device areas polish faster than low-density areas, causing within-die thickness variation that appears as distribution skew when sampling across sites.",
        root_cause_detail="Skewed CMP thickness distribution is typically caused by die-level pattern density loading — high-density areas receive more mechanical contact from the pad and polish faster. Also check if measurement sites are uniformly distributed vs. clustered near wafer edge.",
        alternative_causes=[
            "Measurement site selection bias (over-sampling edge or center)",
            "Dishing in metal CMP at wide metal features",
            "Erosion in STI CMP at narrow active areas",
        ],
        corrective_actions=[
            CAPAAction("Review measurement site map. Ensure uniform coverage across die and wafer radius. Remove any edge-only or center-only bias.", "Metrology", "Immediate", "P2", "Eliminates sampling bias as root cause"),
            CAPAAction("Run pattern density analysis on device layout. Calculate average polish rate correction for high vs. low density regions.", "Process Engineer", "1 week", "P2", "Quantifies pattern density loading effect"),
            CAPAAction("If dishing confirmed: reduce polish pressure in final step or add barrier layer polish optimization.", "Process Engineer", "2 weeks", "P2", "Reduces asymmetric removal at wide features"),
        ],
        preventive_actions=[
            PreventiveAction("Implement density-corrected polish time model in APC. Account for die-level pattern density in removal rate prediction.", "Process Engineer", "1 month", "APC"),
            PreventiveAction("Add dummy fill to reduce pattern density variation across die if design rules permit.", "Process Engineer", "1 month", "Recipe"),
        ],
        containment="No immediate containment required. Flag for process optimization review.",
        disposition="Release",
        weight=1.4,
    ),

    # ═══════════════════════════════════════════════════════════
    # LITHOGRAPHY
    # ═══════════════════════════════════════════════════════════

    CAPARule(
        rule_id="LITHO-001",
        process="Lithography", parameter="CD",
        fault_pattern="Litho CD — Low Cpk (Dose or Focus Drift)",
        description="Lithography CD capability is below threshold. Process mean offset indicates dose or focus drift.",
        severity="Critical",
        cpk_max=1.33, cpk_min=None, ppk_max=1.33, cp_cpk_gap_min=0.2,
        ppm_min=100, spc_rules=[], grr_min=None, ndc_max=None,
        non_normal=False, skewness_min=None,
        root_cause="Dose or focus offset in scanner causing systematic CD bias across wafer or lot.",
        root_cause_detail="In lithography, CD is primarily controlled by dose (energy) and focus (z-height). Centering failure (Cp>>Cpk) means the scanner dose or focus setpoint has drifted. APC system may not be correcting fast enough or the correction model has degraded.",
        alternative_causes=[
            "Resist coating thickness variation altering effective dose sensitivity",
            "BARC (bottom anti-reflective coating) thickness drift affecting CD",
            "Reticle CD error or particle contamination on reticle",
            "Scanner illumination uniformity degradation",
        ],
        corrective_actions=[
            CAPAAction("Pull focus-exposure matrix (FEM) data from last qualification run. Determine current best focus and best dose. Compare to recipe setpoints — update if delta > ±2nm focus or ±0.3% dose.", "Process Engineer", "Immediate", "P1", "Expected CD centering to within ±1nm of target"),
            CAPAAction("Inspect reticle for particles or damage using reticle inspection tool. Clean reticle if contamination found.", "Manufacturing", "Immediate", "P1", "Rules out reticle contamination as cause"),
            CAPAAction("Check scanner APC model validity date. If >2 weeks since last calibration, run APC calibration wafers.", "Equipment", "1 week", "P1", "Restores APC correction accuracy"),
            CAPAAction("Measure BARC thickness on last 10 wafers. If >±5Å drift from target, investigate BARC coating process.", "Metrology", "1 week", "P2", "Rules out resist stack contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Implement APC dose and focus feedback using after-develop inspection (ADI) CD data. Correct every lot.", "Equipment", "2 weeks", "APC"),
            PreventiveAction("Add resist CD SPC chart at ADI. Use as leading indicator for before-etch yield risk.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Schedule reticle inspection every 500 exposures or weekly, whichever comes first.", "Manufacturing", "1 week", "PM"),
        ],
        containment="Hold all wafers exposed on affected scanner since last confirmed good lot. Inspect ADI CD on 3 wafers per lot before releasing.",
        disposition="Hold",
        weight=3.0,
    ),

    CAPARule(
        rule_id="LITHO-002",
        process="Lithography", parameter="Overlay",
        fault_pattern="Overlay — Low Cpk (Registration Error)",
        description="Overlay (layer-to-layer registration) showing systematic error. Potential device yield impact from misalignment.",
        severity="Critical",
        cpk_max=1.33, cpk_min=None, ppk_max=1.33, cp_cpk_gap_min=0.2,
        ppm_min=None, spc_rules=[], grr_min=None, ndc_max=None,
        non_normal=False, skewness_min=None,
        root_cause="Scanner stage positioning error, wafer chuck chucking repeatability, or reticle stage calibration drift causing consistent overlay offset.",
        root_cause_detail="Systematic overlay error (centering issue) in lithography is caused by: scanner baseline drift, lens heating effects from high-throughput operation, wafer expand/contract from temperature, or inter-field/intra-field correction model degradation.",
        alternative_causes=[
            "Wafer thermal expansion from vacuum chuck temperature variation",
            "Grid correction model out of date (>1 week)",
            "Previous layer alignment mark quality degradation",
            "Lens aberration drift from dose accumulation",
        ],
        corrective_actions=[
            CAPAAction("Run overlay measurement on 3 wafers from affected lot. Decompose into translation, rotation, magnification, and higher-order components. Update scanner correction model.", "Process Engineer", "Immediate", "P1", "Expected overlay correction to within 10% of spec"),
            CAPAAction("Check scanner chuck temperature stability. If chuck temp drifting >0.1°C, inspect chuck cooling system.", "Equipment", "Immediate", "P1", "Eliminates thermal expansion contribution"),
            CAPAAction("Run baseline qualification (BLQ) wafers on scanner. If BLQ fails, escalate to scanner vendor.", "Equipment", "1 week", "P1", "Confirms scanner hardware vs. software correction issue"),
        ],
        preventive_actions=[
            PreventiveAction("Implement lot-to-lot overlay APC. Measure every lot, feed correction back to scanner for next lot.", "Equipment", "2 weeks", "APC"),
            PreventiveAction("Add overlay SPC chart with separate X and Y components. Alert on WE1 violation.", "Process Engineer", "1 week", "SPC"),
            PreventiveAction("Schedule scanner lens calibration every 2 weeks regardless of overlay performance.", "Equipment", "1 month", "PM"),
        ],
        containment="Hold affected lots. Measure overlay on every wafer in affected lot. Wafers with overlay >50% of spec limit to rework (strip and rework).",
        disposition="Hold",
        weight=2.8,
    ),

    CAPARule(
        rule_id="LITHO-003",
        process="Lithography", parameter="CD",
        fault_pattern="Litho CD — Non-Normal Distribution (Focus Gradient)",
        description="Resist CD distribution is non-normal with high skewness, indicating a focus gradient or leveling error across wafer.",
        severity="Major",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=[], grr_min=None, ndc_max=None,
        non_normal=True, skewness_min=0.7,
        root_cause="Focus variation across wafer from wafer non-flatness, chuck leveling error, or autofocus system calibration. High skewness = one wafer region consistently at focus edge.",
        root_cause_detail="CD sensitivity to focus is asymmetric (CDs get bigger below focus, smaller above focus at typical dose/focus matrix slopes). Non-normal CD with skew indicates wafer tilt or curvature is pushing some die toward focus limit.",
        alternative_causes=[
            "Wafer warpage (>30µm bow) causing local focus offset",
            "Leveling sensor contamination giving incorrect wafer height map",
            "Wafer backside particle causing localized tilt",
        ],
        corrective_actions=[
            CAPAAction("Measure wafer flatness (SFQR/SBIR) on 5 representative wafers. Identify if wafer bow >30µm is contributing.", "Metrology", "Immediate", "P2", "Quantifies wafer flatness contribution to focus variation"),
            CAPAAction("Map CD spatially across wafer (9+ site measurement). Identify if CD non-uniformity is radial, directional, or localized.", "Metrology", "1 week", "P1", "Spatial CD map diagnoses focus gradient signature"),
            CAPAAction("Inspect wafer chuck leveling pins and vacuum grooves for contamination. Clean and re-level.", "Equipment", "1 week", "P2", "Eliminates chuck-induced tilt"),
        ],
        preventive_actions=[
            PreventiveAction("Implement wafer shape pre-measurement before litho exposure. Reject wafers with bow >40µm.", "Manufacturing", "2 weeks", "SOP"),
            PreventiveAction("Add focus monitor sites at wafer edge in existing CD measurement recipe.", "Metrology", "2 weeks", "Metrology"),
        ],
        containment="Measure 9-site CD map on all wafers from affected lot. Release wafers where all sites within spec. Hold edge-fail wafers.",
        disposition="Conditional Release",
        weight=1.7,
    ),

    CAPARule(
        rule_id="LITHO-004",
        process="Lithography", parameter="CD",
        fault_pattern="Litho CD — SPC Step Change (Reticle or Recipe Event)",
        description="Lithography CD showing step change in SPC — WE1/WE4/NE2 violated. Indicates discrete event at specific time.",
        severity="Critical",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=["WE1", "WE4", "NE2"],
        grr_min=None, ndc_max=None, non_normal=False, skewness_min=None,
        root_cause="Discrete process change event: reticle swap, recipe modification, resist lot change, or scanner qualification run introducing a step offset.",
        root_cause_detail="Step change in litho CD is always an assignable cause. The discrete nature eliminates gradual drift as cause. Most common: reticle swap (check reticle CD bias), resist lot change (check sensitivity curve), or APC model reset after PM.",
        alternative_causes=[
            "Scanner mode change (throughput optimization changing dose uniformity)",
            "Illumination source replacement changing effective dose",
            "Resist developer lot change altering development rate",
        ],
        corrective_actions=[
            CAPAAction("Identify exact wafer and timestamp of step change from SPC chart. Pull tool event log ±2 hours. Identify any recipe change, PM completion, or material lot change.", "Process Engineer", "Immediate", "P1", "Identifies specific assignable cause of step change"),
            CAPAAction("If reticle swap identified: measure CD bias on new reticle vs. old reticle. Apply dose correction to compensate for reticle CD delta.", "Process Engineer", "Immediate", "P1", "Corrects CD offset from reticle-to-reticle variation"),
            CAPAAction("If resist lot change: run resist sensitivity characterization. Update dose recipe to compensate for lot-to-lot sensitivity variation.", "Process Engineer", "1 week", "P1", "Compensates for resist lot variation"),
        ],
        preventive_actions=[
            PreventiveAction("Implement reticle qualification procedure: measure CD bias on every new reticle before production use. Enter offset into scanner correction.", "Manufacturing", "2 weeks", "SOP"),
            PreventiveAction("Add resist lot change to process change notification (PCN) workflow. Require requalification before using new lot.", "Manufacturing", "1 week", "SOP"),
            PreventiveAction("Implement APC model validation after every scanner PM. Do not release to production until APC-corrected CD is within ±2nm of target.", "Equipment", "2 weeks", "APC"),
        ],
        containment="Hold all wafers exposed after step change point. Inspect ADI CD. Release only wafers where CD is within spec.",
        disposition="Hold",
        weight=2.7,
    ),

    # ═══════════════════════════════════════════════════════════
    # DIFFUSION / ANNEAL
    # ═══════════════════════════════════════════════════════════

    CAPARule(
        rule_id="DIFF-001",
        process="Diffusion", parameter="Sheet_Resistance",
        fault_pattern="Sheet Resistance — Low Cpk (Furnace Temperature Offset)",
        description="Sheet resistance (Rs) capability below threshold. Systematic offset from target indicating furnace temperature calibration issue.",
        severity="Major",
        cpk_max=1.33, cpk_min=None, ppk_max=1.33, cp_cpk_gap_min=0.25,
        ppm_min=None, spc_rules=[], grr_min=None, ndc_max=None,
        non_normal=False, skewness_min=None,
        root_cause="Furnace temperature offset from thermocouple calibration drift or heating element degradation causing systematic over- or under-drive of dopant activation.",
        root_cause_detail="Rs is exponentially sensitive to anneal temperature. A centering issue in Rs (Cp>>Cpk) nearly always points to thermocouple calibration drift. Even ±2°C at 1000°C can cause >5% Rs shift. Check thermocouple last calibration date.",
        alternative_causes=[
            "Dopant implant dose variation from upstream implanter",
            "Wafer position in furnace boat causing temperature gradient",
            "Ambient humidity affecting oxide cap during anneal",
        ],
        corrective_actions=[
            CAPAAction("Pull furnace thermocouple calibration records. If last calibration >30 days or temperature offset >1°C, recalibrate immediately.", "Equipment", "Immediate", "P1", "Expected Rs centering to within ±2% of target after temperature correction"),
            CAPAAction("Run 3 monitor wafers at current recipe and 3 at ±5°C to bracket current actual temperature. Use Rs-temperature sensitivity to calculate actual temperature offset.", "Process Engineer", "Immediate", "P1", "Quantifies actual furnace temperature offset"),
            CAPAAction("Correlate Rs offset direction with dopant type. If n-type: higher Rs = lower temp (less activation). Update recipe temperature to compensate.", "Process Engineer", "1 week", "P1", "Restores Rs to target through recipe correction"),
        ],
        preventive_actions=[
            PreventiveAction("Implement monthly furnace thermocouple calibration. Add to PM schedule with mandatory Rs monitor wafer run.", "Equipment", "1 week", "PM"),
            PreventiveAction("Add Rs to lot-to-lot SPC chart with ±3σ limits. Alert when Rs drifts >3% from mean.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Implement APC temperature correction based on Rs feedback. Adjust temperature setpoint by ±2°C increments.", "Equipment", "1 month", "APC"),
        ],
        containment="Measure Rs on all wafers from affected lots. Sort by Rs value — wafers outside ±5% of target to failure review board.",
        disposition="Conditional Release",
        weight=2.0,
    ),

    CAPARule(
        rule_id="DIFF-002",
        process="Diffusion", parameter="Junction_Depth",
        fault_pattern="Junction Depth — Non-Normal Distribution",
        description="Junction depth (Xj) distribution is non-normal, indicating non-uniform drive-in or multiple temperature zones.",
        severity="Major",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=[], grr_min=None, ndc_max=None,
        non_normal=True, skewness_min=0.5,
        root_cause="Non-uniform temperature profile across furnace tube creating wafer-to-wafer Xj variation. Multiple temperature zones (boat edge vs. center) creating bimodal distribution.",
        root_cause_detail="Non-normal Xj distribution in diffusion almost always points to temperature non-uniformity in the furnace tube. Edge wafers (boats 1-3 and last 3) see different temperatures than center wafers. This creates multimodal Xj distribution if sampling across boat positions.",
        alternative_causes=[
            "Implant dose non-uniformity from upstream implanter (±1% uniformity target)",
            "Native oxide variation on wafer surface affecting diffusion front",
            "Wafer-to-wafer spacing in boat creating gas flow variation",
        ],
        corrective_actions=[
            CAPAAction("Re-label Xj data by boat position. Plot Xj vs. boat slot number. If U-shaped or gradient pattern, confirms temperature non-uniformity.", "Process Engineer", "Immediate", "P1", "Identifies if boat position effect is root cause"),
            CAPAAction("Exclude edge boat positions (1-3 and last 3) from product wafers. Use monitor wafers at boat edges.", "Manufacturing", "Immediate", "P2", "Eliminates edge-zone wafers from product exposure"),
            CAPAAction("Run furnace temperature uniformity survey with profiling thermocouple. Map temperature at 5 positions across tube. Adjust heating zone setpoints.", "Equipment", "1 week", "P1", "Quantifies and corrects temperature uniformity"),
        ],
        preventive_actions=[
            PreventiveAction("Implement boat position-based SPC — separate charts for edge vs. center positions.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Add quarterly furnace temperature uniformity qualification to PM schedule.", "Equipment", "1 month", "PM"),
            PreventiveAction("Update boat loading SOP to standardize product wafer positions to center of boat.", "Manufacturing", "1 week", "SOP"),
        ],
        containment="Sort wafers by boat position. Re-measure Xj on edge-position wafers. Hold if Xj outside ±8% of target.",
        disposition="Conditional Release",
        weight=1.8,
    ),

    CAPARule(
        rule_id="DIFF-003",
        process="Diffusion", parameter="Sheet_Resistance",
        fault_pattern="Sheet Resistance — SPC Trend (Heating Element Aging)",
        description="Sheet resistance showing monotonic upward or downward trend across lots. Indicates gradual furnace degradation.",
        severity="Major",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=["NE3", "WE3", "WE4"],
        grr_min=None, ndc_max=None, non_normal=False, skewness_min=None,
        root_cause="Heating element resistance increase with age causing gradual temperature drop. Higher Rs over time = lower effective anneal temperature.",
        root_cause_detail="Monotonic Rs trend in diffusion is the classic signature of heating element aging. As resistance wire ages, it draws less current at the same voltage setpoint, causing actual temperature to drop. The PID controller compensates but has limits.",
        alternative_causes=[
            "Quartz tube contamination from process byproducts altering thermal conductivity",
            "Gradual thermocouple junction drift (common in high-temp furnaces)",
            "Changing wafer lot implant dose if implanter is drifting simultaneously",
        ],
        corrective_actions=[
            CAPAAction("Check heating element resistance. If >5% above nominal resistance, schedule element replacement at next maintenance window.", "Equipment", "1 week", "P1", "Planned element replacement prevents sudden furnace failure"),
            CAPAAction("Implement temperature compensation: increase setpoint by amount needed to maintain Rs at target. Continue monitoring.", "Process Engineer", "Immediate", "P2", "Maintains Rs on target while permanent fix is scheduled"),
            CAPAAction("Run 5 monitor wafers immediately to characterize current Rs vs. target. Quantify trend slope for remaining process life estimate.", "Metrology", "Immediate", "P2", "Quantifies remaining useful life before Rs goes OOC"),
        ],
        preventive_actions=[
            PreventiveAction("Add heating element resistance check to monthly PM checklist. Replace before >3% resistance increase.", "Equipment", "1 month", "PM"),
            PreventiveAction("Implement Rs control chart with run rules specifically sensitive to trends (NE3 with 5-point window).", "Process Engineer", "1 week", "SPC"),
        ],
        containment="Continue production with temperature compensation active. Alert Quality when Rs approaches ±3σ. No immediate hold.",
        disposition="Release",
        weight=1.9,
    ),

    CAPARule(
        rule_id="DIFF-004",
        process="Diffusion", parameter="Thickness",
        fault_pattern="Oxide Thickness — High GRR (4-Point Probe or Ellipsometry)",
        description="Oxide or film thickness GRR is too high. Measurement system cannot reliably distinguish between good and bad wafers.",
        severity="Major",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=[],
        grr_min=20.0, ndc_max=4, non_normal=False, skewness_min=None,
        root_cause="Ellipsometer or 4-point probe calibration drift, measurement site contamination, or measurement recipe parameters not optimized for this film stack.",
        root_cause_detail="High GRR in thickness measurement is commonly caused by: ellipsometer lamp aging (reducing signal-to-noise), incorrect optical model for the film stack, wafer chucking repeatability issues, or ambient light/vibration in the measurement area.",
        alternative_causes=[
            "Measurement recipe using wrong optical model causing systematic repeatability error",
            "Wafer backside particles causing non-repeatable tilt on chuck",
            "Temperature-sensitive film causing measurement variation over time",
        ],
        corrective_actions=[
            CAPAAction("Run GRR on golden reference wafer with certified thickness. If reference also shows high GRR, problem is in metrology tool. If reference GRR is good, problem is sample-related.", "Metrology", "Immediate", "P1", "Differentiates tool vs. sample root cause"),
            CAPAAction("Check ellipsometer lamp hours. If >80% of rated life, replace lamp. Re-run GRR study.", "Equipment", "1 week", "P1", "Lamp aging is the most common ellipsometer GRR failure mode"),
            CAPAAction("Verify optical model is correct for current film stack (refractive index, k value). Update model if film composition has changed.", "Metrology", "1 week", "P2", "Ensures correct physical model for measurement"),
        ],
        preventive_actions=[
            PreventiveAction("Implement weekly ellipsometer GRR check using reference wafer. Alert if %repeatability >5%.", "Metrology", "2 weeks", "Metrology"),
            PreventiveAction("Add lamp hours tracking to metrology equipment log. Schedule replacement at 70% of rated life.", "Equipment", "1 month", "PM"),
        ],
        containment="Suspend Rs and thickness-based process control decisions. Use visual inspection and electrical test as alternative screening.",
        disposition="Hold",
        weight=2.1,
    ),

    # ═══════════════════════════════════════════════════════════
    # GENERAL / CROSS-PROCESS
    # ═══════════════════════════════════════════════════════════

    CAPARule(
        rule_id="GEN-001",
        process="General", parameter="Any",
        fault_pattern="Process Incapable — Cpk < 1.00 (Defects Being Made)",
        description="Process Cpk is below 1.00, meaning defects are being actively produced. Immediate containment required.",
        severity="Critical",
        cpk_max=1.00, cpk_min=None, ppk_max=1.00, cp_cpk_gap_min=None,
        ppm_min=1000, spc_rules=[], grr_min=None, ndc_max=None,
        non_normal=False, skewness_min=None,
        root_cause="Process is fundamentally out of control relative to specification limits. Either specification is too tight for current process capability, or process needs significant improvement.",
        root_cause_detail="Cpk < 1.0 means 6σ process spread exceeds the specification window. This is a design-for-manufacturability issue (spec too tight) or a process capability gap. Distinguish between centering issue (Cp>1.0, Cpk<1.0) vs. spread issue (Cp<1.0).",
        alternative_causes=[
            "Specification limit set incorrectly (too tight vs. device requirement)",
            "Process running on wrong equipment or recipe",
            "Incoming material variation exceeding process tolerance",
        ],
        corrective_actions=[
            CAPAAction("Calculate PPM and estimate yield impact. Present to Product Engineering for priority assessment and immediate containment decision.", "Process Engineer", "Immediate", "P1", "Business impact quantification for escalation"),
            CAPAAction("Segregate and reinspect all product from affected period. Sort: within spec = conditional release, outside spec = scrap or rework queue.", "Manufacturing", "Immediate", "P1", "Containment of defective product"),
            CAPAAction("Review if specification limit is driven by device physics or is historically conservative. Engage Device Engineering to assess relaxation potential.", "Process Engineer", "1 week", "P2", "Identifies if spec tightening is needed vs. process improvement"),
        ],
        preventive_actions=[
            PreventiveAction("Implement real-time SPC with automatic lot hold trigger when Cpk drops below 1.33.", "Process Engineer", "2 weeks", "SPC"),
            PreventiveAction("Conduct process capability study every quarter. Add to engineering review calendar.", "Process Engineer", "1 month", "SOP"),
        ],
        containment="MANDATORY LOT HOLD. Pull all product from affected tool/process since last confirmed Cpk>1.33. 100% inspection before release.",
        disposition="Hold",
        weight=3.0,
    ),

    CAPARule(
        rule_id="GEN-002",
        process="General", parameter="Any",
        fault_pattern="Measurement System Unacceptable — GRR > 30%",
        description="Gauge R&R exceeds 30%. Process control decisions based on this data are unreliable. Fix measurement before fixing process.",
        severity="Major",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=[],
        grr_min=30.0, ndc_max=None, non_normal=False, skewness_min=None,
        root_cause="Measurement system variation is too large relative to process variation. Cannot distinguish good from bad product reliably.",
        root_cause_detail="When %GRR > 30%, the measurement noise is obscuring real process signal. Any Cpk, SPC alarm, or capability conclusion from this data is suspect. Rule of thumb: fix the measurement system first, then re-evaluate process capability.",
        alternative_causes=["See specific tool GRR rules for process-specific guidance."],
        corrective_actions=[
            CAPAAction("Identify if repeatability (EV) or reproducibility (AV) dominates. If AV: standardize operator method. If EV: inspect gauge hardware.", "Metrology", "Immediate", "P1", "Targets most impactful GRR reduction lever"),
            CAPAAction("Re-run GRR study after corrective action. Must achieve <30% before resuming process control.", "Metrology", "1 week", "P1", "Verifies measurement system improvement"),
        ],
        preventive_actions=[
            PreventiveAction("Schedule biannual GRR studies for all critical measurement parameters.", "Metrology", "1 month", "SOP"),
            PreventiveAction("Implement measurement system capability chart — track %GRR over time as leading quality indicator.", "Metrology", "1 month", "Metrology"),
        ],
        containment="Do not make process adjustments based on current measurement data. Continue production but escalate for alternative verification method.",
        disposition="Conditional Release",
        weight=2.5,
    ),

    CAPARule(
        rule_id="GEN-003",
        process="General", parameter="Any",
        fault_pattern="Process Shift — Step Change (Assignable Cause)",
        description="SPC control chart shows clear step change. An assignable cause event occurred at a specific point in time.",
        severity="Major",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=["WE1", "WE4", "NE2"],
        grr_min=None, ndc_max=None, non_normal=False, skewness_min=None,
        root_cause="Discrete assignable cause event: PM completion, material lot change, recipe modification, operator change, or equipment event at the time of the step change.",
        root_cause_detail="Step changes in SPC are never random — they always have an assignable cause. The investigation method is: identify exact shift point on chart, pull tool event log, maintenance log, and material lot log within ±4 hours, correlate.",
        alternative_causes=[
            "Unrecorded recipe change or parameter adjustment",
            "Equipment alarm that was acknowledged without investigation",
            "Raw material lot change not flagged in system",
        ],
        corrective_actions=[
            CAPAAction("Identify exact shift point from SPC chart (first alarm point or visual step location). Pull tool event log, ECO log, and material lot change log within ±4hr window.", "Process Engineer", "Immediate", "P1", "Identifies specific assignable cause"),
            CAPAAction("Once cause identified: reverse change if possible (restore previous recipe, revert to prior material lot). Verify return to baseline with 3 monitor wafers.", "Process Engineer", "Immediate", "P1", "Restores process to pre-shift state"),
        ],
        preventive_actions=[
            PreventiveAction("Implement change notification system: any recipe, material, or maintenance change must be logged in SPC system with timestamp.", "Manufacturing", "2 weeks", "SOP"),
            PreventiveAction("Require monitor wafer run after every PM or recipe change before resuming production.", "Manufacturing", "1 week", "SOP"),
        ],
        containment="Hold wafers processed after shift point. Inspect and sort before release.",
        disposition="Hold",
        weight=2.3,
    ),

    CAPARule(
        rule_id="GEN-004",
        process="General", parameter="Any",
        fault_pattern="ndc < 5 — Gauge Cannot Distinguish Parts",
        description="Number of distinct categories (ndc) is below 5. Gauge resolution is insufficient for process control or acceptance testing.",
        severity="Major",
        cpk_max=None, cpk_min=None, ppk_max=None, cp_cpk_gap_min=None,
        ppm_min=None, spc_rules=[],
        grr_min=None, ndc_max=4, non_normal=False, skewness_min=None,
        root_cause="Measurement resolution is too coarse relative to part-to-part variation. The gauge cannot detect real process differences.",
        root_cause_detail="ndc < 5 means the gauge is essentially a go/no-go indicator, not a measurement tool. This happens when part variation is small relative to gauge resolution — either the process is very capable (good problem) or the gauge is inadequate.",
        alternative_causes=[
            "Part-to-part variation is genuinely very low (good process) — gauge resolution fine for go/no-go but not for SPC",
            "Wrong gauge selected for this measurement — resolution spec too coarse",
        ],
        corrective_actions=[
            CAPAAction("Evaluate if low ndc is because process is very capable (part variation small) or gauge is coarse. Calculate ratio of gauge resolution to spec tolerance.", "Metrology", "Immediate", "P2", "Determines if problem is measurement system or part variation"),
            CAPAAction("If gauge is inadequate: evaluate higher-resolution measurement option. For CD: replace optical CD with SEM or scatterometry.", "Metrology", "1 week", "P1", "Upgrades measurement capability to achieve ndc ≥ 5"),
        ],
        preventive_actions=[
            PreventiveAction("During measurement system selection, require ndc ≥ 5 analysis before approving gauge for production use.", "Metrology", "1 month", "SOP"),
        ],
        containment="Continue production. Flag that SPC control effectiveness is limited with current gauge.",
        disposition="Release",
        weight=1.6,
    ),
]

