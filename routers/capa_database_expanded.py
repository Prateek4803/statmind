"""
StatMind N15 — Expanded CAPA Database
Additional rules beyond the 31 in capa_database_r2.py.
Covers: CVD/Deposition, Implant, Overlay, Injection Molding,
Pharma/Biotech (cGMP), Electronics Assembly (IPC-A-610),
Funnel/Sawtooth/Variance patterns, CMP WIWNU.
Target: 80+ total rules combined with capa_database_r2.py
"""
from capa_database_r2 import CAPARule, CAPAAction, PreventiveAction

EXPANDED_RULES = [

    # ── SEMICONDUCTOR EXPANDED ────────────────────────────────────────────────

    CAPARule(
        rule_id="CVD-001", process="CVD/Deposition", parameter="Deposition_Rate",
        fault_pattern="CVD Deposition Rate Drift — Film Thickness Offset",
        description="CVD deposition rate showing systematic offset or drift. Film thickness Cpk below threshold.",
        severity="Major", cpk_max=1.33, cp_cpk_gap_min=0.2,
        root_cause="Precursor gas flow controller calibration drift or chamber wall coating buildup changing effective gas distribution.",
        root_cause_detail="Deposition rate is controlled by precursor gas flow, temperature, and pressure. Systematic offset (Cp>Cpk) points to setpoint calibration issue. Trend (NE3/WE3) points to chamber wall loading effect — coating builds up on walls over wafer count, changing gas distribution.",
        alternative_causes=["RF power drift for PECVD processes","Susceptor temperature uniformity degradation","Precursor source bubbler temperature drift","Chamber wall seasoning change after wet clean"],
        corrective_actions=[
            CAPAAction("Measure deposition rate on monitor wafer. Compare to qualification recipe baseline. Adjust MFC setpoint if >±3% from target.","Process Engineer","Immediate","P1","Expected deposition rate centering within ±1%"),
            CAPAAction("Run chamber seasoning wafers if post-wet-clean. Typically 5-10 seasoning wafers required before production.","Process Engineer","Immediate","P1","Restores wall condition to steady state"),
            CAPAAction("Check precursor MFC calibration. Recalibrate if >90 days or >2% offset on reference flow.","Equipment","1 week","P2","Eliminates flow controller drift"),
        ],
        preventive_actions=[
            PreventiveAction("Add deposition rate SPC with 3-sigma limits. Alert when NE3 rule fires (trend indication).","Process Engineer","2 weeks","SPC"),
            PreventiveAction("Define seasoning protocol in SOP: mandatory after every wet clean or idle >48 hours.","Manufacturing","1 week","SOP"),
        ],
        containment="Measure thickness on all wafers from affected period. Sort: in-spec release, OOT hold.",
        disposition="Conditional Release", standard_reference="SEMI M1, SEMI E10", weight=2.0,
    ),

    CAPARule(
        rule_id="CVD-002", process="CVD/Deposition", parameter="Film_Uniformity",
        fault_pattern="CVD Uniformity Degradation — Center-to-Edge Non-Uniformity",
        description="Within-wafer non-uniformity (WIWNU) increasing. Standard deviation of film thickness across wafer rising.",
        severity="Major", cpk_max=1.33, spc_rules=["NE3","WE3"],
        root_cause="Showerhead clogging causing non-uniform gas distribution, or susceptor temperature gradient developing.",
        root_cause_detail="WIWNU is a signature of gas distribution or temperature uniformity issues. Progressive WIWNU increase (trend) = gradual clog buildup in showerhead or heater element degradation. Sudden WIWNU increase = showerhead damage or zone heater failure.",
        alternative_causes=["Wafer bow causing non-uniform gap to showerhead","Edge ring erosion changing edge gas flow","Carrier gas purity change"],
        corrective_actions=[
            CAPAAction("Map WIWNU pattern: if center-high = showerhead center clog, if edge-low = edge ring issue, if asymmetric = showerhead damage or temperature zone failure.","Metrology","Immediate","P1","Identifies root cause sub-type"),
            CAPAAction("Inspect showerhead holes with magnification. Schedule showerhead clean or replacement if >20% of holes show deposit buildup.","Equipment","1 week","P1","Restores gas distribution uniformity"),
            CAPAAction("Run temperature uniformity scan across susceptor. Replace zone heater if >5°C non-uniformity.","Equipment","1 week","P2","Eliminates thermal non-uniformity contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Add WIWNU SPC (3-sigma sigma chart, not just mean chart). Alert on sigma increase.","Process Engineer","2 weeks","SPC"),
            PreventiveAction("Showerhead inspection in PM checklist at defined wafer count intervals.","Equipment","1 month","PM"),
        ],
        containment="Map all wafers from affected period. Wafers with WIWNU >spec to rework or scrap.",
        disposition="Conditional Release", standard_reference="SEMI M1", weight=2.1,
    ),

    CAPARule(
        rule_id="IMPL-001", process="Ion Implant", parameter="Dose_Uniformity",
        fault_pattern="Implant Dose Non-Uniformity — Scanner Beam Current Variation",
        description="Ion implant dose uniformity (WIWNU) out of specification. Non-uniform dopant distribution across wafer.",
        severity="Critical", cpk_max=1.33,
        root_cause="Ion beam current instability or scanner velocity uniformity degradation during implant.",
        root_cause_detail="Dose uniformity is controlled by beam current × scan speed. Non-uniformity = either beam current varying during scan (aperture contamination, source instability) or scanner velocity non-uniform (mechanical backlash, servo control issue). Measure Faraday cup profile to distinguish.",
        alternative_causes=["Beam focus drift causing beam broadening","End station angle calibration drift","Photoresist outgassing causing beam contamination during scan"],
        corrective_actions=[
            CAPAAction("Run Faraday cup beam profile measurement. If beam current non-uniform: source/extraction issue. If current uniform but wafer non-uniform: scanner mechanical issue.","Equipment","Immediate","P1","Identifies beam vs. scanner root cause"),
            CAPAAction("If source issue: inspect source aperture for contamination. Clean or replace source components. Run beam characterization before production.","Equipment","Immediate","P1","Restores beam current uniformity"),
            CAPAAction("If scanner issue: run scanner linearity test. Recalibrate or replace scanner servo if velocity error >0.5%.","Equipment","1 week","P1","Eliminates scanner contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Dose uniformity SPC on every production lot. Alert on any point beyond ±3% from target.","Process Engineer","1 week","SPC"),
            PreventiveAction("Source current stability check in PM checklist. Replace source at defined arc-hours.","Equipment","1 month","PM"),
        ],
        containment="MANDATORY 100% Rs or CD measurement on all wafers from affected period to verify dose.",
        disposition="Hold", standard_reference="SEMI E10, SEMI M13", weight=2.8,
    ),

    CAPARule(
        rule_id="LITHO-002", process="Lithography", parameter="Overlay",
        fault_pattern="Overlay Error — Layer-to-Layer Misalignment",
        description="Overlay error between current and previous layers exceeds specification. Risk of open circuits or shorts.",
        severity="Critical", cpk_max=1.33, ppm_min=100,
        root_cause="Scanner alignment model mismatch, wafer chuck chuck error, or lens heating drift during production run.",
        root_cause_detail="Overlay error components: translation (tool offset), rotation (wafer placement), magnification (scanner magnification error), and intrafield (lens distortion). Each has a different root cause. APC overlay model may not be capturing all terms, especially if wafer stress changes from previous layer.",
        alternative_causes=["Reticle placement error or reticle expansion","WIS (wafer induced shift) from process stress","Stage vibration from adjacent equipment","Mark asymmetry causing alignment signal error"],
        corrective_actions=[
            CAPAAction("Decompose overlay into components (translation, rotation, magnification, residual). Use overlay map analysis to identify dominant term.","Process Engineer","Immediate","P1","Identifies specific correction needed"),
            CAPAAction("If translation: adjust scanner job offset by measured overlay delta. Re-expose test wafer to verify.","Equipment","Immediate","P1","Expected overlay correction to within spec"),
            CAPAAction("If intrafield (grid): update lens model or contact scanner OEM for lens calibration.","Equipment","1 week","P1","Addresses lens distortion contribution"),
            CAPAAction("Check wafer chuck flatness. If chuck damage suspected, run chuck qualification wafer.","Equipment","1 week","P2","Eliminates chuck-induced overlay error"),
        ],
        preventive_actions=[
            PreventiveAction("APC overlay feedback loop with daily calibration wafer. Alert if translation >20% of overlay spec.","Equipment","2 weeks","APC"),
            PreventiveAction("Overlay SPC per lot with decomposition into components.","Process Engineer","2 weeks","SPC"),
        ],
        containment="MANDATORY overlay measurement on all wafers at affected layer. Rework (strip + re-expose) if overlay >spec.",
        disposition="Hold", standard_reference="SEMI M12, SEMI E89", weight=3.0,
    ),

    CAPARule(
        rule_id="CMP-002", process="CMP", parameter="WIWNU",
        fault_pattern="CMP WIWNU — Radial Non-Uniformity Pattern",
        description="CMP within-wafer non-uniformity showing systematic radial pattern. Edge fast or center fast profile.",
        severity="Major", cpk_max=1.33, non_normal=True,
        root_cause="Pressure profile across carrier head not uniform. Center pressure zone or edge ring pressure out of calibration.",
        root_cause_detail="CMP uniformity is primarily controlled by carrier head zone pressures and retaining ring pressure. Center-fast profile = center zone pressure too high relative to edge. Edge-fast = retaining ring pressure too high or edge zone pressure elevated. Asymmetric pattern = carrier head tilt or pad non-uniformity.",
        alternative_causes=["Pad break-in insufficient — new pad typically has different uniformity than run-in pad","Slurry distribution non-uniform from nozzle positioning","Platen temperature gradient from coolant flow variation"],
        corrective_actions=[
            CAPAAction("Map WIWNU pattern in polar coordinates. Identify: center-fast (adjust center zone -0.5 PSI), edge-fast (reduce retaining ring +0.3 PSI or reduce edge zone), asymmetric (head tilt or pad issue).","Process Engineer","Immediate","P1","Identifies specific pressure correction"),
            CAPAAction("Adjust carrier head zone pressures per WIWNU map. Run test wafer. Iterate until WIWNU <spec.","Process Engineer","Immediate","P1","Expected WIWNU improvement to within spec"),
            CAPAAction("Inspect pad for wear pattern. If pad wear correlates with WIWNU map, replace pad and condition before production.","Equipment","1 week","P2","Eliminates pad-induced non-uniformity"),
        ],
        preventive_actions=[
            PreventiveAction("Map WIWNU after every pad change and after every carrier head PM. Define acceptance criteria before production.","Process Engineer","2 weeks","SOP"),
            PreventiveAction("Add WIWNU sigma SPC chart (in addition to mean chart). Alert when sigma exceeds 1% absolute.","Quality","2 weeks","SPC"),
        ],
        containment="Map all wafers. Sort by post-CMP thickness uniformity. Rework: re-CMP if within thickness budget, scrap if not.",
        disposition="Conditional Release", standard_reference="SEMI M1", weight=2.2,
    ),

    # ── STATISTICAL PATTERN RULES ─────────────────────────────────────────────

    CAPARule(
        rule_id="STAT-001", process="General", parameter="Any",
        fault_pattern="Funnel Pattern — Over-Adjustment (Tampering)",
        description="SPC data shows funnel pattern: variation decreasing then increasing, or alternating over/under correction. Classic over-adjustment signature.",
        severity="Major", spc_rules=["NE8"],
        root_cause="Operator or APC system is adjusting the process in response to random variation (tampering). Makes process WORSE, not better.",
        root_cause_detail="Funnel rule (Deming's funnel experiment): adjusting a stable process based on each individual measurement increases variation by √2. If an operator adjusts the setpoint every time a measurement deviates from target, the resulting process has 41% more variation than the unadjusted process. APC systems can cause this if tuned with too-aggressive feedback.",
        alternative_causes=["APC algorithm with gain too high (over-correction)","Operator incorrectly trained to adjust on every part","Specification so tight that any deviation triggers adjustment"],
        corrective_actions=[
            CAPAAction("Verify operators understand: DO NOT adjust setpoint unless SPC rule fires (not just because measurement is off-nominal). Retrain.","Manufacturing/Quality","Immediate","P1","Eliminates manual tampering — expected variation reduction to baseline"),
            CAPAAction("If APC system: reduce feedback gain by 50%. Run monitor wafers. If variation decreases, gain was too high.","Equipment","1 week","P1","Fixes over-aggressive APC feedback"),
            CAPAAction("Calculate pre-tampering sigma from MR chart. Show team the before/after comparison to reinforce no-adjustment training.","Quality Engineer","1 week","P2","Evidence-based training reinforcement"),
        ],
        preventive_actions=[
            PreventiveAction("Add to operator training: 'Only adjust when SPC rule fires, never on individual measurements.' Document in SOP.","Manufacturing","1 week","SOP"),
            PreventiveAction("For APC: implement EWMA-filtered feedback (not raw measurement). Reduces APC over-correction.","Equipment","2 weeks","APC"),
        ],
        containment="No hold required — no defects produced by over-adjustment (just excess variation). Fix the adjustment behavior.",
        disposition="Release", standard_reference="Deming 'Out of the Crisis', AIAG SPC 2nd Ed", weight=2.0,
    ),

    CAPARule(
        rule_id="STAT-002", process="General", parameter="Any",
        fault_pattern="Sawtooth Pattern — Alternating Tool or Cavity Variation",
        description="SPC data alternates systematically high-low-high-low. Classic signature of two alternating sources (tools, cavities, shifts, operators).",
        severity="Major", spc_rules=["NE8","NE4"],
        root_cause="Two systematically different process sources are being plotted together without stratification.",
        root_cause_detail="A true sawtooth (period=2) almost always means two alternating sources: Tool A measures high, Tool B measures low, alternating. Common causes: two-cavity mold with different dimensions, alternating operators with different technique, A/B shift difference, alternating load positions on a batch furnace. The solution is ALWAYS stratification — separate SPC charts per source.",
        alternative_causes=["Two measurement tools alternating in use with different offsets","Front-of-boat vs back-of-boat systematic difference in furnace","Alternating material lots with different baseline properties"],
        corrective_actions=[
            CAPAAction("Identify the alternating pattern period. If period=2, investigate what alternates every 2 measurements. If period=N, investigate what cycle has period N.","Process/Quality Engineer","Immediate","P1","Identifies alternating source"),
            CAPAAction("Separate data by suspected stratification factor. If two separate charts show no pattern, stratification is confirmed. Fix the offset between sources.","Process Engineer","1 week","P1","Resolves systematic between-source offset"),
        ],
        preventive_actions=[
            PreventiveAction("Require separate SPC charts per tool, cavity, operator from process design phase.","Quality","During APQP","SOP"),
            PreventiveAction("Add tool/cavity ID to data collection system. Never mix sources on same chart.","Quality","2 weeks","SOP"),
        ],
        containment="Sort product by source (tool A vs B, cavity 1 vs 2). Inspect each stratum separately.",
        disposition="Conditional Release", standard_reference="AIAG SPC 2nd Ed, ISO 7870-5", weight=2.0,
    ),

    CAPARule(
        rule_id="STAT-003", process="General", parameter="Any",
        fault_pattern="Sudden Variance Increase — No Mean Shift",
        description="Process standard deviation increased significantly without a corresponding mean shift. Variance chart (MR or S) alarms but Xbar/I chart does not.",
        severity="Major", spc_rules=["WE1"],  # on variance chart
        root_cause="Machine vibration, loose fixturing, or material property variation increasing — causes variability without shifting mean.",
        root_cause_detail="Variance increase without mean shift is the signature of: (1) mechanical looseness (vibration adds random noise), (2) incoming material lot with wider variation, (3) fixturing not repeatable (random clamping variation), (4) environmental noise (temperature fluctuation, vibration from adjacent equipment). It is NOT a setpoint issue.",
        alternative_causes=["Probe or gauge contact force variation","Measurement system degradation (stylus wear, probe contamination)","Multiple operators with different technique (AV component of GRR increasing)"],
        corrective_actions=[
            CAPAAction("Check MR chart or S chart for the alarm point. Correlate with maintenance log ±4 hours. Look for mechanical events (new fixturing, new lot, PM, personnel change).","Process Engineer","Immediate","P1","Identifies assignable cause of variance increase"),
            CAPAAction("Inspect all mechanical connections in process path for looseness. Check fixturing clamping torque.","Equipment","1 week","P1","Eliminates mechanical vibration contribution"),
            CAPAAction("Run GRR study on measurement system. If %GRR increased, measurement system is the root cause.","Metrology","1 week","P2","Rules out measurement system as variance source"),
        ],
        preventive_actions=[
            PreventiveAction("Add variance/range SPC charts (not just mean chart). Mean chart alone is blind to variance changes.","Quality","2 weeks","SPC"),
            PreventiveAction("Vibration monitoring on precision equipment. Alert when vibration exceeds baseline by 20%.","Equipment","1 month","PM"),
        ],
        containment="No immediate hold required unless variance increase affects yield. Monitor SPC closely.",
        disposition="Release", standard_reference="AIAG SPC 2nd Ed", weight=1.8,
    ),

    # ── INJECTION MOLDING ─────────────────────────────────────────────────────

    CAPARule(
        rule_id="MOLD-001", process="Injection Molding", parameter="Dimensional",
        fault_pattern="Mold Cavity-to-Cavity Variation — Multi-Cavity Bimodal Distribution",
        description="Parts from multi-cavity mold showing bimodal distribution or high part-to-part variation. Different cavities producing different dimensions.",
        severity="Major", cpk_max=1.33, non_normal=True, spc_rules=["NE8"],
        root_cause="Unequal cavity filling due to runner imbalance, worn cavity tooling, or differential cavity wear between cavities.",
        root_cause_detail="Multi-cavity bimodality is always cavity-to-cavity. Runner balance determines how melt fills each cavity — unbalanced runners cause some cavities to overfill (larger dimension) and others to underfill (smaller). Individual cavity wear also creates progressive dimension change in specific cavities over tool life.",
        alternative_causes=["Differential tool cooling between cavities","Gate wear in specific cavities affecting fill","Cavity surface finish difference from differential polishing wear"],
        corrective_actions=[
            CAPAAction("Separate parts by cavity (mark cavities during run). Measure each cavity independently. Identify which cavities are outlying.","Quality/Manufacturing","Immediate","P1","Identifies problem cavity vs overall process issue"),
            CAPAAction("For fill imbalance: run rheological balance study. Adjust runner dimensions of over-filled cavities to restrict flow.","Tooling Engineer","1 week","P1","Rebalances cavity fill — expected dimensional consistency"),
            CAPAAction("For worn cavities: inspect cavity surfaces. Measure cavity nominal vs worn dimensions. Weld and re-machine worn cavities or replace cavity inserts.","Tooling","2 weeks","P1","Eliminates cavity-specific wear contribution"),
        ],
        preventive_actions=[
            PreventiveAction("Separate SPC charts per cavity. Minimum requirement for multi-cavity tools.","Quality","2 weeks","SPC"),
            PreventiveAction("Cavity dimension audit at defined tool cycle counts. Define maximum cavity wear before rework.","Tooling","1 month","PM"),
        ],
        containment="Sort by cavity. Cavities outside spec: hold production from those cavities. Others: conditional release.",
        disposition="Conditional Release", standard_reference="AIAG PPAP, ISO 9001:2015", weight=2.2,
    ),

    # ── PHARMA/BIOTECH (cGMP) ────────────────────────────────────────────────

    CAPARule(
        rule_id="PHARMA-001", process="Pharmaceutical", parameter="Dissolution",
        fault_pattern="Dissolution OOT — Tablet Dissolution Failure (USP <711>)",
        description="Tablet dissolution out-of-specification result. OOS/OOT requiring Phase I/Phase II investigation per FDA guidance.",
        severity="Critical", cpk_max=1.33,
        root_cause="Blend uniformity failure, granulation moisture content variation, or compression force outside validated range causing dissolution profile change.",
        root_cause_detail="Dissolution failure in solid oral dosage forms is caused by: (1) API particle size change affecting dissolution rate, (2) blend non-uniformity creating tablet-to-tablet content variation, (3) compression force outside validated range (over-compression = slower dissolution, under-compression = fast disintegration but content uniformity risk), (4) coating defects blocking dissolution medium access.",
        alternative_causes=["Equipment changeover (different tablet press punch/die set)","Excipient lot change with different physical properties","Environmental humidity during manufacturing affecting granulation"],
        corrective_actions=[
            CAPAAction("Initiate OOS investigation per 21 CFR 211.192 and FDA Guidance on Investigation of OOS Results. Phase I: laboratory/analyst error. Phase II: full process investigation.","QC/Quality","Immediate","P1","FDA-required OOS procedure — mandatory for cGMP compliance"),
            CAPAAction("Retain and quarantine batch. Do not destroy retain samples until investigation complete.","Quality","Immediate","P1","Evidence preservation for regulatory compliance"),
            CAPAAction("Run content uniformity testing if dissolution failure confirmed. Identify if it is a uniformity issue or dissolution issue.","QC","Immediate","P1","Distinguishes blend failure from dissolution formulation failure"),
        ],
        preventive_actions=[
            PreventiveAction("Dissolution SPC per batch with warning and action limits. Alert before OOS occurs.","QC","2 weeks","SPC"),
            PreventiveAction("Compression force SPC in-process. Alert when force deviates >10% from target.","Manufacturing","2 weeks","SPC"),
        ],
        containment="MANDATORY batch quarantine. FDA notification may be required for marketed product.",
        disposition="Hold", standard_reference="21 CFR 211.192, FDA OOS Guidance 2006, USP <711>", weight=3.0,
    ),

    # ── ELECTRONICS ASSEMBLY (IPC-A-610) ─────────────────────────────────────

    CAPARule(
        rule_id="ELEC-001", process="Electronics Assembly", parameter="Solder_Volume",
        fault_pattern="Solder Paste Volume OOT — SPI Inspection Failure",
        description="Solder paste volume (measured by SPI - Solder Paste Inspection) out of specification. Risk of solder bridges or opens.",
        severity="Major", cpk_max=1.33,
        root_cause="Stencil aperture clogging, squeegee pressure out of specification, or solder paste rheology change (expired paste or improper storage).",
        root_cause_detail="SPI failure for solder paste volume: (1) Low volume = stencil aperture clogging (most common), squeegee pressure too low, or solder paste viscosity too high (cold paste), (2) High volume = stencil gasketing issue, squeegee speed too fast, or paste rheology too thin. Inspect stencil condition immediately after SPI failure.",
        alternative_causes=["Stencil thickness out of spec (wrong stencil installed)","Board support fixture not level (uneven paste pressure)","Paste beyond shelf life or not brought to room temperature before use"],
        corrective_actions=[
            CAPAAction("Inspect stencil under microscope at failing aperture locations. Clean stencil if >10% of apertures show clogging.","Process Engineer","Immediate","P1","Restores paste volume to specification"),
            CAPAAction("Verify squeegee pressure setting. Check squeegee blade condition — replace if blade edge shows wear or nicks.","Process Engineer","Immediate","P1","Eliminates squeegee-induced volume variation"),
            CAPAAction("Check solder paste pot age and storage temperature log. If paste is >24hr out of refrigerator or beyond shelf life, discard and open new canister.","Manufacturing","Immediate","P1","Eliminates paste rheology as cause"),
        ],
        preventive_actions=[
            PreventiveAction("SPI volume Cpk SPC by aperture type. Alert when volume Cpk drops below 1.33.","Quality","2 weeks","SPC"),
            PreventiveAction("Stencil cleaning after every N boards (define N based on aperture density). Use automated stencil cleaner.","Manufacturing","1 week","SOP"),
        ],
        containment="Remove affected boards. Re-inspect all boards printed with suspect paste/stencil. Reflow-inspect 100% of boards in affected run.",
        disposition="Conditional Release", standard_reference="IPC-A-610, IPC-7711/7721", weight=2.3,
    ),

    # ── GENERAL ADDITIONAL ────────────────────────────────────────────────────

    CAPARule(
        rule_id="GEN-METRO-009", process="General", parameter="Any",
        fault_pattern="Cpk Between 1.33–1.67 — Below PPAP Threshold",
        description="Process capability between 1.33 and 1.67. Meets ongoing monitoring but FAILS PPAP requirement of Cpk ≥ 1.67.",
        severity="Major", cpk_max=1.67, cpk_min=1.33,
        root_cause="Process designed to Cpk ≥ 1.33 target without PPAP margin. Or process degraded from initial PPAP level.",
        root_cause_detail="IATF 16949 and AIAG PPAP require Cpk ≥ 1.67 for PPAP submission (Cpk ≥ 1.33 for ongoing production). A Cpk of 1.45 will pass ongoing monitoring but will fail a new PPAP submission. The 1.33–1.67 zone is the 'warning band' — process is capable for production but cannot be submitted for a new part approval.",
        alternative_causes=["Process degraded from initial PPAP level (was 1.67, now 1.45)","Special cause during sampling period lowered Cpk estimate","Measurement system degradation adding variation"],
        corrective_actions=[
            CAPAAction("Determine if gap is centering or spread. If centering (Cp>1.67 but Cpk=1.45): centering fix is fast. If spread (Cp<1.67): process improvement needed.","Quality Engineer","1 week","P2","Directs fastest improvement path"),
            CAPAAction("For upcoming PPAP: target Cpk ≥ 2.0 during development to provide margin for production drift.","Process Engineer","Before PPAP","P1","Ensures PPAP will pass with margin"),
        ],
        preventive_actions=[
            PreventiveAction("Monitor Cpk trend. Alert when Cpk drops below 1.67 (PPAP threshold) not just below 1.33 (minimum).","Quality","2 weeks","SPC"),
        ],
        containment="Production may continue (Cpk ≥ 1.33). Do not submit for new PPAP until Cpk ≥ 1.67.",
        disposition="Conditional Release", standard_reference="IATF 16949:2016, AIAG PPAP", weight=1.8,
    ),

    CAPARule(
        rule_id="GEN-METRO-010", process="General", parameter="Any",
        fault_pattern="Marginal GRR (10–30%) — Measurement System Improvement Needed",
        description="%GRR between 10% and 30%. Marginal measurement system. AIAG MSA 4th Ed: acceptable only with management approval based on application importance.",
        severity="Minor", grr_min=10.0,
        root_cause="Gauge resolution borderline for tolerance, or operator technique not fully standardized.",
        root_cause_detail="10–30% GRR is the 'marginal' zone. AIAG MSA says this 'may be acceptable based on application, cost of gauge, cost of repairs, etc.' It means: the gauge is providing useful information but not at the level required for capability studies. Cpk calculations from this data will be pessimistic (too low). Before investing in process improvement, verify gauge is not the root cause.",
        alternative_causes=["Tolerance set too tight relative to available measurement technology","Environmental conditions affecting measurement (temperature, vibration)"],
        corrective_actions=[
            CAPAAction("Determine if EV or AV dominates. If AV>EV: operator training and standardized technique will help most. If EV>AV: gauge hardware improvement needed.","Metrology","1 week","P2","Targets most impactful GRR reduction lever"),
            CAPAAction("Calculate ndc. If ndc ≥ 5: gauge is adequate for SPC even with %GRR in marginal zone. If ndc < 5: gauge upgrade required.","Metrology","1 week","P2","Determines if current gauge is usable for SPC"),
        ],
        preventive_actions=[
            PreventiveAction("Annual GRR study for all marginal gauges. Track %GRR trend — if increasing, prioritize upgrade.","Metrology","Annual","Metrology"),
        ],
        containment="Production may continue. Note: capability studies from this data may underestimate true process Cpk.",
        disposition="Release", standard_reference="AIAG MSA 4th Ed", weight=1.4,
    ),
]
