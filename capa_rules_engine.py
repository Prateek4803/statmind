"""
StatMind — Session 5: Rule-Based CAPA Engine
Pattern-matches statistical results against CAPA database
No LLM, no API key — fully deterministic
"""

import dataclasses
from typing import Optional
from capa_database import CAPA_RULES, CAPARule, CAPAAction, PreventiveAction


def score_rule(rule: CAPARule, stats: dict) -> float:
    """
    Score a rule against statistical inputs. Returns match score (0 = no match).
    Higher score = stronger/more specific match.
    """
    score = 0.0
    matched_any = False

    cpk  = stats.get("cpk")
    ppk  = stats.get("ppk")
    cp   = stats.get("cp")
    ppm  = stats.get("ppm_within")
    grr  = stats.get("grr_pct")
    ndc  = stats.get("ndc")
    normality = stats.get("normality_verdict", "")  # "Normal","Likely Normal","Non-Normal"
    skewness  = stats.get("skewness", 0)
    alarms    = stats.get("alarm_rules", [])         # list of rule strings e.g. ["WE1","NE2"]
    process   = stats.get("process", "").lower()
    parameter = stats.get("parameter", "").lower()

    # Process / parameter filter — if rule specifies, only match if process matches
    if rule.process not in ("General", "") and process:
        process_map = {
            "etch": ["etch", "rie", "drie", "wet"],
            "cmp": ["cmp", "polish", "planarization"],
            "lithography": ["litho", "lithography", "photo", "resist", "exposure"],
            "diffusion": ["diffusion", "anneal", "furnace", "oxidation", "implant"],
            "metrology": ["metrology", "measure", "sem", "ellipsometer"],
        }
        keywords = process_map.get(rule.process.lower(), [rule.process.lower()])
        if not any(kw in process for kw in keywords):
            # No process match — soft filter (don't discard, just don't boost)
            pass

    # ── Capability triggers ──
    if rule.cpk_max is not None and cpk is not None:
        if cpk < rule.cpk_max:
            score += 2.0 * (rule.cpk_max - cpk) / rule.cpk_max  # closer to 0 = higher score
            matched_any = True

    if rule.ppk_max is not None and ppk is not None:
        if ppk < rule.ppk_max:
            score += 1.0
            matched_any = True

    if rule.cp_cpk_gap_min is not None and cp is not None and cpk is not None:
        gap = cp - cpk
        if gap >= rule.cp_cpk_gap_min:
            score += 1.5 * gap  # bigger gap = higher score
            matched_any = True

    if rule.ppm_min is not None and ppm is not None:
        if ppm > rule.ppm_min:
            score += 1.0
            matched_any = True

    # ── GRR triggers ──
    if rule.grr_min is not None and grr is not None:
        if grr > rule.grr_min:
            score += 2.5 * (grr / 100)
            matched_any = True

    if rule.ndc_max is not None and ndc is not None:
        if ndc <= rule.ndc_max:
            score += 1.5
            matched_any = True

    # ── SPC alarm triggers ──
    if rule.spc_rules and alarms:
        matches = [r for r in alarms if r in rule.spc_rules]
        if matches:
            score += len(matches) * 1.5
            matched_any = True

    # ── Normality triggers ──
    if rule.non_normal and normality == "Non-Normal":
        score += 2.0
        matched_any = True

    if rule.skewness_min is not None and abs(skewness) >= rule.skewness_min:
        score += 1.0
        matched_any = True

    if not matched_any:
        return 0.0

    return round(score * rule.weight, 3)


def run_capa_engine(
    normality_result=None,
    capability_result=None,
    spc_result=None,
    grr_result=None,
    process_context: str = "",
    parameter_name: str = "",
    process_type: str = "",    # Etch | CMP | Lithography | Diffusion | ""
) -> dict:
    """
    Main entry point. Scores all rules and returns ranked CAPA results.
    Returns: {
        "matched_rules": [...],     # top matches with scores
        "primary_capa": {...},      # highest-scoring rule as full CAPA report
        "all_triggered_rules": [...],
        "stats_summary": {...},
        "auto_severity": str,
        "process_context": str,
    }
    """
    # Build unified stats dict from all inputs
    stats = _extract_stats(normality_result, capability_result, spc_result, grr_result)
    stats["process"] = (process_type + " " + parameter_name + " " + process_context).lower()
    stats["parameter"] = parameter_name.lower()

    # Score all rules
    scored = []
    for rule in CAPA_RULES:
        s = score_rule(rule, stats)
        if s > 0:
            scored.append((s, rule))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return {
            "matched_rules": [],
            "primary_capa": None,
            "stats_summary": stats,
            "auto_severity": "Minor",
            "message": "No rule violations detected. Process appears to be in acceptable control.",
        }

    # Build output
    matched = []
    for score, rule in scored[:8]:  # top 8 matches
        matched.append({
            "rule_id": rule.rule_id,
            "process": rule.process,
            "fault_pattern": rule.fault_pattern,
            "severity": rule.severity,
            "score": score,
            "description": rule.description,
        })

    # Primary CAPA from top match
    top_score, top_rule = scored[0]
    primary = _build_capa_report(top_rule, stats, process_context, parameter_name)

    # Auto-severity: use highest severity across all matched rules
    sev_order = {"Critical": 3, "Major": 2, "Minor": 1}
    max_sev = max((sev_order.get(r.severity, 0) for _, r in scored), default=0)
    auto_sev = {3: "Critical", 2: "Major", 1: "Minor"}.get(max_sev, "Minor")

    return {
        "matched_rules": matched,
        "primary_capa": primary,
        "stats_summary": stats,
        "auto_severity": auto_sev,
        "top_rule_id": top_rule.rule_id,
        "message": f"Matched {len(scored)} rule(s). Primary: {top_rule.fault_pattern}",
    }


def get_capa_for_rule(rule_id: str, stats: dict, process_context: str, parameter_name: str) -> dict:
    """Get CAPA report for a specific rule_id (user manual override)."""
    rule = next((r for r in CAPA_RULES if r.rule_id == rule_id), None)
    if not rule:
        return {"error": f"Rule {rule_id} not found"}
    return _build_capa_report(rule, stats, process_context, parameter_name)


def _extract_stats(norm, cap, spc, grr) -> dict:
    """Flatten all statistical results into a single stats dict."""
    stats = {}

    if cap:
        stats["cpk"]    = cap.get("cpk")
        stats["cp"]     = cap.get("cp")
        stats["ppk"]    = cap.get("ppk")
        stats["pp"]     = cap.get("pp")
        stats["cpu"]    = cap.get("cpu")
        stats["cpl"]    = cap.get("cpl")
        stats["ppm_within"] = cap.get("ppm_within")
        stats["ppm_overall"]= cap.get("ppm_overall")
        stats["sigma_level"]= cap.get("sigma_level")
        stats["std_within"] = cap.get("std_within")
        stats["std_overall"]= cap.get("std_overall")
        stats["mean"]   = cap.get("mean")
        stats["usl"]    = cap.get("usl")
        stats["lsl"]    = cap.get("lsl")

    if norm:
        stats["normality_verdict"] = norm.get("overall_verdict", "")
        stats["skewness"] = norm.get("skewness", 0)
        stats["kurtosis"] = norm.get("kurtosis", 3)
        stats["n"]        = norm.get("n")
        if not stats.get("mean"):
            stats["mean"] = norm.get("mean")

    if spc:
        all_alarms = (spc.get("western_electric_alarms") or []) + (spc.get("nelson_alarms") or [])
        stats["alarm_rules"] = list(set(a.get("rule","") for a in all_alarms))
        stats["total_alarms"] = spc.get("total_alarms", 0)
        stats["in_control"]   = spc.get("in_control", True)
        stats["chart_type"]   = spc.get("chart_type", "")
        stats["spc_verdict"]  = spc.get("stability_verdict", "")

    if grr:
        stats["grr_pct"] = grr.get("gauge_rr", {}).get("pct_study_var")
        stats["ndc"]     = grr.get("ndc")
        stats["grr_ev"]  = grr.get("repeatability", {}).get("pct_study_var")
        stats["grr_av"]  = grr.get("reproducibility", {}).get("pct_study_var")
        stats["grr_verdict"] = grr.get("verdict")

    return stats


def _build_capa_report(rule: CAPARule, stats: dict, process_context: str, parameter_name: str) -> dict:
    """Convert a matched rule + stats into a full CAPA report dict."""

    # Fill metrics from actual stats
    metrics = {
        "current_cpk":    stats.get("cpk"),
        "target_cpk":     1.33,
        "current_ppm":    stats.get("ppm_within"),
        "target_ppm":     round((1 - 1.33/1.5) * (stats.get("ppm_within") or 0) * 0.1, 0) if stats.get("ppm_within") else None,
        "sigma_level":    stats.get("sigma_level"),
        "grr_pct":        stats.get("grr_pct"),
        "normality":      stats.get("normality_verdict"),
        "total_alarms":   stats.get("total_alarms"),
    }

    # Build evidence list from actual data
    evidence = []
    cpk = stats.get("cpk")
    cp  = stats.get("cp")
    if cpk is not None:
        evidence.append(f"Cpk = {cpk:.3f} {'< 1.00 (producing defects)' if cpk < 1.0 else '< 1.33 (below industry standard)' if cpk < 1.33 else '≥ 1.33'}")
    if cp is not None and cpk is not None and (cp - cpk) > 0.2:
        evidence.append(f"Cp = {cp:.3f} vs Cpk = {cpk:.3f}: centering gap of {cp-cpk:.3f} indicates off-center process")
    ppm = stats.get("ppm_within")
    if ppm is not None and ppm > 10:
        evidence.append(f"Expected {ppm:,.0f} PPM defects (within-subgroup estimate)")
    if stats.get("total_alarms"):
        evidence.append(f"{stats['total_alarms']} SPC rule violation(s) detected: {', '.join(stats.get('alarm_rules',[]))}")
    grr = stats.get("grr_pct")
    if grr is not None:
        evidence.append(f"Gauge R&R = {grr:.1f}% {'(Unacceptable — >30%)' if grr>30 else '(Marginal — 10–30%)' if grr>10 else '(Acceptable — <10%)'}")
    ndc = stats.get("ndc")
    if ndc is not None:
        evidence.append(f"ndc = {ndc} {'(inadequate — <5 required)' if ndc < 5 else '(adequate)'}")
    norm = stats.get("normality_verdict")
    if norm == "Non-Normal":
        sk = stats.get("skewness", 0)
        evidence.append(f"Data is Non-Normal (skewness = {sk:.3f}) — standard Cpk indices may be misleading")
    if not evidence:
        evidence.append("Statistical thresholds triggered based on input data")

    return {
        "rule_id": rule.rule_id,
        "process": rule.process,
        "parameter": parameter_name or rule.parameter,
        "fault_pattern": rule.fault_pattern,
        "process_context": process_context,

        "executive_summary": (
            f"{rule.fault_pattern} detected on {parameter_name or rule.parameter}. "
            f"Severity: {rule.severity}. "
            f"{rule.description}"
        ),

        "problem_statement": {
            "description": rule.description,
            "severity": rule.severity,
            "affected_process": f"{rule.process} — {parameter_name or rule.parameter}",
            "statistical_evidence": evidence,
        },

        "root_cause_analysis": {
            "primary_hypothesis": rule.root_cause,
            "detail": rule.root_cause_detail,
            "confidence": "High" if stats.get("total_alarms", 0) > 3 or (cpk is not None and cpk < 1.0) else "Medium",
            "alternative_hypotheses": rule.alternative_causes,
            "investigation_actions": [a.action for a in rule.corrective_actions if a.priority == "P1"][:2],
        },

        "corrective_actions": [
            {
                "action": a.action,
                "owner": a.owner,
                "timeline": a.timeline,
                "priority": a.priority,
                "expected_impact": a.expected_impact,
            }
            for a in rule.corrective_actions
        ],

        "preventive_actions": [
            {
                "action": a.action,
                "owner": a.owner,
                "timeline": a.timeline,
                "system_change": a.system_change,
            }
            for a in rule.preventive_actions
        ],

        "disposition": {
            "recommendation": rule.disposition,
            "rationale": f"Based on {rule.fault_pattern} — {rule.description[:100]}",
            "containment": rule.containment,
        },

        "metrics": metrics,

        "confidence_level": "High" if stats.get("total_alarms", 0) > 3 or (cpk is not None and cpk < 1.0) else "Medium",
        "report_sections_confidence": {
            "problem_statement": "High",
            "root_cause": "Medium" if rule.alternative_causes else "High",
            "corrective_actions": "High",
            "preventive_actions": "High",
        },
    }


def get_all_rules_catalog() -> list:
    """Return all rules as a catalog for the manual override UI."""
    return [
        {
            "rule_id": r.rule_id,
            "process": r.process,
            "parameter": r.parameter,
            "fault_pattern": r.fault_pattern,
            "severity": r.severity,
            "description": r.description,
        }
        for r in CAPA_RULES
    ]


# ── R2: Load expanded database if available ───────────────────────────────────
def _get_rules():
    """Load expanded R2 database if available, fallback to original."""
    from capa_database import CAPA_RULES as R2_RULES
    return R2_RULES


def run_capa_engine_v2(
    normality_result=None, capability_result=None,
    spc_result=None, grr_result=None,
    process_context: str = "", parameter_name: str = "", process_type: str = "",
) -> dict:
    """V2 engine — uses expanded R2 database with process-boosted scoring."""
    from capa_database import CAPA_RULES

    stats = _extract_stats(normality_result, capability_result, spc_result, grr_result)
    stats["process"] = (process_type + " " + parameter_name + " " + process_context).lower()
    stats["parameter"] = parameter_name.lower()

    # Score with process boost
    scored = []
    for rule in CAPA_RULES:
        s = score_rule(rule, stats)
        if s == 0:
            continue
        # Boost rules whose process matches user-selected process_type
        if process_type and rule.process.lower() in process_type.lower():
            s *= 1.8
        # Boost general rules if no specific process selected
        elif not process_type and rule.process == "General":
            s *= 1.2
        # Penalise if process clearly doesn't match (e.g. Automotive for semiconductor data)
        if process_type and rule.process not in ("General", process_type):
            s *= 0.5
        scored.append((s, rule))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return {
            "matched_rules": [], "primary_capa": None,
            "stats_summary": stats, "auto_severity": "Minor",
            "message": "No rule violations detected.",
        }

    matched = []
    for score, rule in scored[:8]:
        matched.append({
            "rule_id": rule.rule_id, "process": rule.process,
            "fault_pattern": rule.fault_pattern, "severity": rule.severity,
            "score": round(score, 2), "description": rule.description,
        })

    top_score, top_rule = scored[0]
    primary = _build_capa_report(top_rule, stats, process_context, parameter_name)

    sev_order = {"Critical": 3, "Major": 2, "Minor": 1}
    max_sev = max((sev_order.get(r.severity, 0) for _, r in scored), default=0)
    auto_sev = {3:"Critical",2:"Major",1:"Minor"}.get(max_sev,"Minor")

    return {
        "matched_rules": matched, "primary_capa": primary,
        "stats_summary": stats, "auto_severity": auto_sev,
        "top_rule_id": top_rule.rule_id,
        "message": f"Matched {len(scored)} rule(s). Primary: {top_rule.fault_pattern}",
    }


def get_all_rules_catalog_v2() -> list:
    """Return expanded R2 catalog."""
    try:
        from capa_database import CAPA_RULES
        return [{"rule_id": r.rule_id, "process": r.process, "parameter": r.parameter,
                 "fault_pattern": r.fault_pattern, "severity": r.severity,
                 "description": r.description, "standard_reference": r.standard_reference}
                for r in CAPA_RULES]
    except ImportError:
        return get_all_rules_catalog()


# ── N5: Subrange-aware CAPA ────────────────────────────────────────────────────

def run_capa_engine_subrange(
    normality_result=None, capability_result=None,
    spc_result=None, grr_result=None,
    process_context: str = "", parameter_name: str = "", process_type: str = "",
    subrange_start: int = None, subrange_end: int = None,
    total_points: int = None,
) -> dict:
    """
    V2 CAPA engine with subrange awareness.
    When a SPC subrange is selected, notes that analysis is localized
    and adjusts fault pattern description accordingly.
    """
    result = run_capa_engine_v2(
        normality_result, capability_result, spc_result, grr_result,
        process_context, parameter_name, process_type,
    )

    is_subrange = subrange_start is not None and subrange_end is not None

    if is_subrange and result.get("primary_capa"):
        capa = result["primary_capa"]
        total = total_points or (subrange_end if subrange_end else 100)
        window = subrange_end - subrange_start if subrange_end and subrange_start is not None else 0
        pct = round(window / total * 100, 1) if total > 0 else 0

        # Add subrange context to fault pattern and conclusion
        sr_note = (
            f"SUBRANGE ANALYSIS: Points {subrange_start+1}–{subrange_end} "
            f"({window} of {total} total, {pct}% of dataset). "
            f"This is a LOCALIZED capability failure, not a global one. "
        )

        # Compare subrange Cpk vs full-dataset Cpk
        sub_cpk = capability_result.get("cpk") if capability_result else None
        if sub_cpk is not None:
            sr_note += f"Subrange Cpk={sub_cpk:.3f}. "
            if sub_cpk < 1.0:
                sr_note += "Subrange is significantly more capable-challenged than shown in full-dataset view. "

        # Add subrange context to executive summary
        if capa.get("executive_summary"):
            capa["executive_summary"] = sr_note + capa["executive_summary"]
        if capa.get("fault_pattern"):
            capa["fault_pattern"] = f"[Subrange pts {subrange_start+1}–{subrange_end}] " + capa["fault_pattern"]

        # Add specific subrange corrective action
        sr_action = {
            "action": f"Investigate specific event at points {subrange_start+1}–{subrange_end}. "
                      f"Pull tool event log, maintenance records, and material lot data for this time window (±4 hours).",
            "owner": "Process Engineer",
            "timeline": "Immediate",
            "priority": "P1",
            "expected_impact": f"Identifies assignable cause for localized failure in {pct}% of production window."
        }
        if capa.get("corrective_actions"):
            capa["corrective_actions"].insert(0, sr_action)
        else:
            capa["corrective_actions"] = [sr_action]

        result["subrange_context"] = {
            "is_subrange": True,
            "start": subrange_start,
            "end": subrange_end,
            "window_size": window,
            "total_points": total,
            "pct_of_dataset": pct,
            "note": sr_note,
        }
    else:
        result["subrange_context"] = {"is_subrange": False}

    return result
