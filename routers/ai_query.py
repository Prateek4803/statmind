"""
StatMind N16 — AI Natural Language Query Engine
"Is Chamber A different from Chamber B?" → auto-selects and runs the right test
"Which parameters are out of control?" → scans all SPC results
"What is causing my Cpk to be low?" → triggers CAPA engine
"Show me the distribution of Etch_Rate" → runs normality + histogram

Intent classification → route to correct engine → return result + explanation
"""

import numpy as np
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QueryIntent:
    category: str          # "compare","capability","spc","normality","correlation","capa","outliers","regression","general"
    confidence: float      # 0-1
    parameters_mentioned: list   # column names detected in query
    test_recommended: str        # "two_sample_t", "anova", "capability", etc
    reasoning: str               # why this test was selected


@dataclass
class NLQueryResult:
    query: str
    intent: QueryIntent
    analysis_type: str
    # The actual result (dict from underlying engine)
    result: dict
    # Plain English interpretation
    answer: str            # direct answer to the question
    key_finding: str       # one-sentence takeaway
    recommendation: str    # what to do next
    # Suggested follow-up queries
    follow_ups: list
    # Chart hint for frontend
    chart_hint: str        # "boxplot","histogram","control_chart","scatter" etc


# ── Intent Classifier ─────────────────────────────────────────────────────────

INTENT_PATTERNS = {
    "compare": [
        r"\b(different|differ|compare|vs\.?|versus|same|equal|better|worse|higher|lower)\b",
        r"\b(chamber|tool|operator|shift|lot|batch|line|machine)\s+[a-z0-9]+\s+(vs\.?|versus|and|or)\b",
        r"\bis\s+\w+\s+(higher|lower|better|worse|different)\s+(than|from)\b",
        r"\b(anova|t.?test|mann.?whitney|hypothesis)\b",
    ],
    "capability": [
        r"\b(cpk|cp|ppk|capability|capable|ppm|sigma.?level|yield|defect)\b",
        r"\b(spec|usl|lsl|tolerance|within.?spec|out.?of.?spec|oos)\b",
        r"\b(ppap|customer.?require|qualify|qualification)\b",
    ],
    "spc": [
        r"\b(control|alarm|alert|out.?of.?control|signal|rule|violation)\b",
        r"\b(stable|unstable|trend|shift|drift|pattern)\b",
        r"\b(cusum|ewma|shewhart|xbar|i.?mr|control.?chart)\b",
    ],
    "normality": [
        r"\b(normal|distribution|skew|histogram|bell.?curve|shapiro|anderson)\b",
        r"\b(transform|box.?cox|log.?normal|non.?normal)\b",
        r"\b(how.?is.+distributed|what.+distribution|look.+like)\b",
    ],
    "correlation": [
        r"\b(correlat|related|relationship|depends|affect|influence|drives?|impact)\b",
        r"\b(pearson|spearman|r.?squared|r2)\b",
        r"\bdoes\s+\w+\s+(affect|influence|correlate|relate|drive)\b",
    ],
    "outlier": [
        r"\b(outlier|anomal|unusual|extreme|suspect|bad.?data|spurious|grubbs|dixon)\b",
        r"\b(remove|exclude|flag|identify|detect)\s+(outlier|bad|extreme)\b",
    ],
    "regression": [
        r"\b(predict|model|regression|fit|equation|linear|formula)\b",
        r"\b(y\s*=|response|input.+output|cause.+effect)\b",
        r"\bwhat.+(predict|model|cause|drive)\b",
    ],
    "capa": [
        r"\b(cause|root.?cause|why|reason|capa|corrective|action|fix|solve)\b",
        r"\b(investigate|diagnose|failure.?mode|fault|defect.+cause)\b",
    ],
    "timeseries": [
        r"\b(trend|over.?time|forecast|predict.+future|time.?series|seasonal)\b",
        r"\b(increasing|decreasing|growing|declining|drifting)\b",
    ],
    "grr": [
        r"\b(gauge|gage|measurement.?system|msa|grr|repeatability|reproducibility)\b",
        r"\b(measurement.+error|measurement.+variab|gauge.+r.+r)\b",
    ],
}

def classify_intent(query: str, available_columns: list = None) -> QueryIntent:
    q = query.lower().strip()
    scores = {cat: 0.0 for cat in INTENT_PATTERNS}

    for cat, patterns in INTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q):
                scores[cat] += 1.0

    # Normalize
    max_score = max(scores.values()) if scores else 1
    if max_score == 0:
        best_cat = "general"
        confidence = 0.3
    else:
        best_cat = max(scores, key=scores.get)
        confidence = min(0.98, scores[best_cat] / (max_score + 1) * 1.5 + 0.3)

    # Detect column names in query
    params_mentioned = []
    if available_columns:
        for col in available_columns:
            if col.lower() in q or col.replace('_',' ').lower() in q:
                params_mentioned.append(col)

    # Map intent to recommended test
    test_map = {
        "compare": _pick_compare_test(q, params_mentioned),
        "capability": "capability",
        "spc": "cusum_ewma" if any(w in q for w in ["small","subtle","drift","1 sigma","shift"]) else "spc",
        "normality": "normality",
        "correlation": "correlation",
        "outlier": "outliers",
        "regression": "regression",
        "capa": "capa",
        "timeseries": "timeseries",
        "grr": "grr",
        "general": "normality",
    }

    reasoning_map = {
        "compare": f"Query asks to compare groups → {'ANOVA' if len(params_mentioned)>2 else '2-sample t-test or Mann-Whitney'}",
        "capability": "Query asks about process capability → Cp/Cpk analysis with confidence intervals",
        "spc": "Query asks about process control → SPC control charts with alarm detection",
        "normality": "Query asks about data distribution → Shapiro-Wilk + Anderson-Darling normality tests",
        "correlation": "Query asks about relationships → Pearson + Spearman correlation matrix",
        "outlier": "Query asks about unusual values → Grubbs + Rosner ESD outlier detection",
        "regression": "Query asks about prediction/modeling → Linear regression with R² and coefficients",
        "capa": "Query asks about root cause → CAPA engine with 45-rule fault pattern matching",
        "timeseries": "Query asks about time trends → Trend analysis + decomposition + forecast",
        "grr": "Query asks about measurement system → Gauge R&R ANOVA method",
        "general": "General query → Running normality test as starting point",
    }

    return QueryIntent(
        category=best_cat,
        confidence=round(confidence, 3),
        parameters_mentioned=params_mentioned,
        test_recommended=test_map.get(best_cat, "normality"),
        reasoning=reasoning_map.get(best_cat, ""),
    )


def _pick_compare_test(q: str, params: list) -> str:
    n_groups = len(params) if params else 2
    is_nonparametric = any(w in q for w in ["non-normal","skewed","nonnormal","not normal","count","defect"])
    if n_groups > 2:
        return "kruskal_wallis" if is_nonparametric else "one_way_anova"
    return "mann_whitney" if is_nonparametric else "two_sample_t"


# ── Query Router ──────────────────────────────────────────────────────────────

def route_query(
    query: str,
    df,                    # pandas DataFrame
    column: str = None,    # primary column if known
    usl: float = None,
    lsl: float = None,
    process_type: str = "",
) -> NLQueryResult:
    """
    Route a natural language query to the correct analysis engine.
    Returns a unified NLQueryResult with plain-English answer.
    """
    import pandas as pd

    available_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    intent = classify_intent(query, available_cols)

    # Pick primary column
    primary_col = None
    if intent.parameters_mentioned:
        primary_col = intent.parameters_mentioned[0]
    elif column and column in df.columns:
        primary_col = column
    elif available_cols:
        primary_col = available_cols[0]

    if primary_col is None:
        return NLQueryResult(
            query=query, intent=intent,
            analysis_type="error", result={},
            answer="Could not identify a numeric column to analyze. Please specify a column name.",
            key_finding="No numeric column found.",
            recommendation="Upload a file with numeric columns and mention the column name in your query.",
            follow_ups=[], chart_hint="none",
        )

    result = {}
    answer = ""
    key_finding = ""
    recommendation = ""
    chart_hint = "histogram"
    follow_ups = []

    try:
        cat = intent.category

        # ── Compare ──────────────────────────────────────────────────────────
        if cat == "compare" and len(intent.parameters_mentioned) >= 2:
            from hypothesis import two_sample_t, one_way_anova, mann_whitney, kruskal_wallis
            import dataclasses as dc
            cols = intent.parameters_mentioned[:6]
            groups = [df[c].dropna().values.astype(float) for c in cols]
            names = cols

            if len(groups) == 2:
                if intent.test_recommended == "mann_whitney":
                    r = mann_whitney(groups[0], groups[1], names[0], names[1])
                else:
                    r = two_sample_t(groups[0], groups[1], names[0], names[1])
            else:
                if intent.test_recommended == "kruskal_wallis":
                    r = kruskal_wallis(groups, names)
                else:
                    r = one_way_anova(groups, names)

            result = dc.asdict(r)
            sig = r.reject_null
            answer = (
                f"Yes, {names[0]} and {names[1]} ARE significantly different (p={r.p_value:.4f} < 0.05). "
                f"Mean difference = {abs(groups[0].mean()-groups[1].mean()):.4f}. Effect: {r.effect_interpretation}."
                if sig else
                f"No, {names[0]} and {names[1]} are NOT significantly different (p={r.p_value:.4f} ≥ 0.05). "
                f"Insufficient evidence to conclude they differ."
            )
            key_finding = r.conclusion[:120]
            recommendation = "Run CAPA engine if significant. Check GRR to confirm measurement system isn't masking differences." if sig else "Continue monitoring. Consider increasing sample size if practical difference exists."
            chart_hint = "boxplot"
            follow_ups = [
                f"Are {names[0]} variances equal to {names[1]}?",
                f"What is the Cpk of {names[0]}?",
                "What is causing this difference?",
            ]

        # ── Capability ───────────────────────────────────────────────────────
        elif cat == "capability":
            from capability import analyze_capability
            import dataclasses as dc
            data = df[primary_col].dropna().values.astype(float)
            mean, std = float(np.mean(data)), float(np.std(data, ddof=1))
            u = usl or (mean + 4*std)
            l = lsl or (mean - 4*std)
            r = analyze_capability(data, primary_col, u, l)
            result = dc.asdict(r)
            cpk = r.cpk
            verdict = "CAPABLE (Cpk ≥ 1.33)" if cpk >= 1.33 else "MARGINAL (1.00 ≤ Cpk < 1.33)" if cpk >= 1.0 else "NOT CAPABLE (Cpk < 1.00)"
            answer = (
                f"{primary_col} is {verdict}. Cpk = {cpk:.3f}, Cp = {r.cp:.3f}. "
                f"Estimated PPM = {r.ppm_within:,.0f}. Sigma level = {r.sigma_level:.2f}σ."
            )
            key_finding = r.verdict
            recommendation = ("Process is capable. Maintain current settings and monitor with SPC." if cpk >= 1.33 else
                             "Cpk marginal. Investigate centering (if Cp>>Cpk) or reduce variation (if Cp≈Cpk)." if cpk >= 1.0 else
                             "Process not capable. Immediate improvement needed. Run CAPA engine.")
            chart_hint = "capability"
            follow_ups = [f"Is {primary_col} normally distributed?", f"What is causing {primary_col} to have low Cpk?", f"Show me the {primary_col} control chart"]

        # ── SPC / Control ─────────────────────────────────────────────────────
        elif cat == "spc":
            from control_charts import analyze_control_chart
            import dataclasses as dc
            data = df[primary_col].dropna().values.astype(float)
            r = analyze_control_chart(data, primary_col, subgroup_size=1)
            result = dc.asdict(r)
            n_alarms = r.total_alarms
            answer = (
                f"{primary_col} is IN statistical control. No SPC alarms detected ({len(data)} observations)."
                if r.in_control else
                f"{primary_col} is OUT of control. {n_alarms} alarm(s) detected. "
                f"Latest violation: {r.western_electric_alarms[0]['rule'] if r.western_electric_alarms else 'Nelson rule'}."
            )
            key_finding = f"UCL={r.primary_ucl:.4f}, Mean={r.primary_cl:.4f}, LCL={r.primary_lcl:.4f}. {n_alarms} alarms."
            recommendation = ("Continue monitoring. No assignable causes detected." if r.in_control else
                             "Investigate assignable cause immediately. Check tool logs for events at alarm timestamps.")
            chart_hint = "control_chart"
            follow_ups = [f"What is the Cpk of {primary_col}?", "What is causing the out-of-control signal?", f"Run CUSUM chart on {primary_col} to detect small shifts"]

        # ── Normality ─────────────────────────────────────────────────────────
        elif cat == "normality":
            from normality import analyze_column
            import dataclasses as dc
            data = df[primary_col].dropna().values.astype(float)
            r = analyze_column(data, primary_col)
            result = dc.asdict(r)
            norm = r.overall_verdict
            sw = r.shapiro_wilk
            sw_p = sw.get("p_value", 0) if isinstance(sw, dict) else getattr(sw, "p_value", 0)
            answer = (
                f"{primary_col} appears {'normally' if norm != 'Non-Normal' else 'non-normally'} distributed "
                f"(Shapiro-Wilk p={sw_p:.4f}). "
                f"Mean = {r.mean:.4f}, Std = {r.std:.4f}, n = {r.n}."
            )
            key_finding = f"{norm}. Skewness = {r.skewness:.3f}, Kurtosis = {r.kurtosis:.3f}."
            chart_hint = "histogram"
            follow_ups = [f"What is the Cpk of {primary_col}?", f"Transform {primary_col} with Box-Cox", f"Are there outliers in {primary_col}?"]

        # ── Correlation ───────────────────────────────────────────────────────
        elif cat == "correlation":
            from correlation import correlation_matrix
            import dataclasses as dc
            r = correlation_matrix(df[available_cols], alpha=0.05, min_r=0.3)
            result = dc.asdict(r)
            top = r.strong_pairs[:3] if r.strong_pairs else []
            if top:
                top_str = "; ".join(f"{p['col_a']}↔{p['col_b']} (r={p['pearson_r']:.3f})" for p in top)
                answer = f"Found {len(r.strong_pairs)} notable correlations. Strongest: {top_str}."
            else:
                answer = f"No strong correlations (|r| ≥ 0.3) found among {len(available_cols)} variables."
            key_finding = r.conclusion[:120]
            recommendation = ("Investigate the strong correlations — they may indicate process levers or confounded variables." if top else
                             "No obvious input-output relationships. Consider DOE to identify drivers.")
            chart_hint = "heatmap"
            follow_ups = [f"Does {top[0]['col_a'] if top else available_cols[0]} predict {top[0]['col_b'] if top else (available_cols[1] if len(available_cols)>1 else 'output')}?", "Run regression analysis", "Show scatter plot"]

        # ── Outliers ──────────────────────────────────────────────────────────
        elif cat == "outlier":
            from outliers import detect_outliers
            import dataclasses as dc
            data = df[primary_col].dropna().values.astype(float)
            r = detect_outliers(data, primary_col, usl=usl, lsl=lsl)
            result = dc.asdict(r)
            n_out = r.n_outliers
            answer = (
                f"Found {n_out} statistical outlier(s) in {primary_col} out of {r.n} measurements. "
                f"Values: {r.outlier_values}. "
                + (f"Excluding outliers: Cpk improves from {r.cpk_with} to {r.cpk_without}." if r.cpk_with and r.cpk_without else "")
                if n_out > 0 else
                f"No statistical outliers detected in {primary_col} (n={r.n}). Grubbs test p>0.05."
            )
            key_finding = r.conclusion[:120]
            recommendation = ("Investigate outlier values before excluding them. Check measurement error, process events, or data entry errors first." if n_out > 0 else
                             "Data quality confirmed. Proceed with standard analysis.")
            chart_hint = "scatter"
            follow_ups = [f"What is the Cpk of {primary_col} without outliers?", f"Is {primary_col} normally distributed?"]

        # ── Regression ────────────────────────────────────────────────────────
        elif cat == "regression" and len(intent.parameters_mentioned) >= 2:
            from regression import simple_linear_regression
            import dataclasses as dc
            y_col = intent.parameters_mentioned[0]
            x_col = intent.parameters_mentioned[1]
            if y_col in df.columns and x_col in df.columns:
                r = simple_linear_regression(df[x_col].values.astype(float), df[y_col].values.astype(float), x_col, y_col)
                result = dc.asdict(r)
                answer = (
                    f"{'Yes' if r.model_significant else 'No'}, {x_col} {'IS' if r.model_significant else 'is NOT'} a significant predictor of {y_col} "
                    f"(R²={r.r_squared:.4f}, p={r.f_p_value:.4f}). "
                    f"Equation: {r.equation}."
                )
                key_finding = r.conclusion[:120]
                recommendation = ("Use this equation for process control and setpoint adjustment." if r.model_significant else
                                 "No significant linear relationship. Try multiple regression or DOE to find true drivers.")
                chart_hint = "scatter"
                follow_ups = [f"What else predicts {y_col}?", "Run DOE to identify optimal settings", f"What is the correlation matrix?"]

        # ── CAPA / Root Cause ─────────────────────────────────────────────────
        elif cat == "capa":
            from capa_rules_engine import run_capa_engine_v2
            data = df[primary_col].dropna().values.astype(float)
            mean, std = float(np.mean(data)), float(np.std(data, ddof=1))
            cap_stub = {"cpk": round(float(min((usl-mean)/(3*std),(mean-lsl)/(3*std))),4) if usl and lsl and std>0 else None}
            r = run_capa_engine_v2(capability_result=cap_stub, process_type=process_type, parameter_name=primary_col)
            result = r
            primary = r.get("primary_capa", {})
            answer = (
                f"Most likely root cause: {primary.get('fault_pattern','Unknown')}. "
                f"Root cause: {primary.get('root_cause','')[:100]}."
                if primary else
                "Could not identify a specific root cause. More session data (Normality, Capability, SPC, GRR) improves CAPA accuracy."
            )
            key_finding = primary.get("root_cause","")[:120] if primary else "Insufficient data for root cause analysis."
            recommendation = primary.get("corrective_actions",[{}])[0].get("action","Run complete StatMind analysis first, then return to CAPA.") if primary and primary.get("corrective_actions") else "Run Normality, Capability, SPC analyses first."
            chart_hint = "none"
            follow_ups = ["Run normality test first", "Run capability analysis", "Run SPC chart"]

        # ── Time Series ───────────────────────────────────────────────────────
        elif cat == "timeseries":
            from timeseries import analyze_timeseries
            import dataclasses as dc
            data = df[primary_col].dropna().values.astype(float)
            r = analyze_timeseries(data, primary_col)
            result = dc.asdict(r)
            answer = (
                f"{primary_col} shows a {r.trend_magnitude.lower()} {r.trend_direction.lower()} trend "
                f"(slope={r.trend_slope:+.4f}/obs, p={r.trend_p_value:.4f}). "
                f"{'Trend is statistically significant.' if r.trend_significant else 'Trend is not statistically significant.'} "
                f"10-step forecast: {r.ses_forecast[0]:.4f}."
            )
            key_finding = r.conclusion[:120]
            recommendation = ("Investigate source of trend — likely tool wear, consumable degradation, or environmental drift." if r.trend_significant else
                             "No significant trend. Process appears temporally stable.")
            chart_hint = "line"
            follow_ups = [f"Is the {primary_col} trend causing capability issues?", f"Run SPC chart on {primary_col}", "What is causing this trend?"]

        # ── GRR ───────────────────────────────────────────────────────────────
        elif cat == "grr":
            answer = f"For GRR analysis, upload a file with Part, Operator, and Measurement columns, then use the GRR session."
            key_finding = "GRR requires structured multi-operator, multi-part, multi-replicate data."
            recommendation = "Use the Session 4 — Gauge R&R tab. Minimum: 10 parts × 3 operators × 2 replicates."
            chart_hint = "none"
            follow_ups = ["How many samples do I need for a GRR study?"]

        # ── General fallback ─────────────────────────────────────────────────
        else:
            from normality import analyze_column
            import dataclasses as dc
            data = df[primary_col].dropna().values.astype(float)
            r = analyze_column(data, primary_col)
            result = dc.asdict(r)
            answer = (
                f"Here's a summary of {primary_col}: n={r.n}, "
                f"Mean={r.mean:.4f}, Std={r.std:.4f}, "
                f"Distribution: {r.overall_verdict}."
            )
            key_finding = f"{primary_col}: {r.overall_verdict}, Skew={r.skewness:.3f}"
            recommendation = "Start with capability analysis (enter USL/LSL) or SPC chart."
            chart_hint = "histogram"
            follow_ups = [f"What is the Cpk of {primary_col}?", f"Is {primary_col} in control?", f"Are there outliers in {primary_col}?"]

    except Exception as e:
        answer = f"Analysis failed: {str(e)}. Try specifying the column name explicitly."
        key_finding = str(e)
        recommendation = "Check that column names in your query match the uploaded file."
        result = {"error": str(e)}

    return NLQueryResult(
        query=query,
        intent=intent,
        analysis_type=intent.category,
        result=result,
        answer=answer,
        key_finding=key_finding,
        recommendation=recommendation,
        follow_ups=follow_ups[:3],
        chart_hint=chart_hint,
    )
