"""
StatMind — Session 4: Gauge R&R Engine
ANOVA method (preferred) + Xbar/R method
% Contribution breakdown: Part, Operator, Interaction, Equipment (Repeatability), Reproducibility
ndc (number of distinct categories)
Crossed and nested study support
"""

import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


@dataclass
class ANOVATable:
    source: str
    ss: float       # Sum of squares
    df: int         # Degrees of freedom
    ms: float       # Mean square
    f_stat: float
    p_value: float


@dataclass
class VarianceComponent:
    source: str
    variance: float
    std_dev: float
    pct_contribution: float     # % of total variance
    pct_study_var: float        # % of study variation (6σ basis)
    study_var: float            # 6 * std_dev


@dataclass
class GaugeRRReport:
    # Study design
    study_type: str             # "Crossed" or "Nested"
    method: str                 # "ANOVA" or "XbarR"
    n_parts: int
    n_operators: int
    n_replicates: int
    n_total: int
    column: str

    # ANOVA table
    anova_table: list           # list of ANOVATable dicts

    # Variance components
    repeatability: VarianceComponent        # Equipment variation (EV)
    reproducibility: VarianceComponent      # Appraiser variation (AV)
    operator_by_part: VarianceComponent     # Interaction
    gauge_rr: VarianceComponent             # GRR = repeatability + reproducibility
    part_to_part: VarianceComponent         # PV
    total_variation: VarianceComponent      # TV

    # Key metrics
    ndc: int                    # number of distinct categories
    tolerance: Optional[float]  # USL - LSL if provided
    pct_tolerance: Optional[float]  # GRR as % of tolerance

    # Verdict
    verdict: str                # "Acceptable", "Marginal", "Unacceptable"
    verdict_detail: str
    capa_required: bool
    capa_notes: list

    # Chart data
    by_operator_data: dict      # for operator comparison chart
    part_variation_data: dict   # for part-to-part chart
    interaction_data: dict      # operator * part interaction


def analyze_gauge_rr(
    measurements: np.ndarray,       # shape: (n_parts * n_operators * n_replicates,)
    parts: np.ndarray,              # part labels for each measurement
    operators: np.ndarray,          # operator labels for each measurement
    column: str = "Measurement",
    tolerance: Optional[float] = None,
    method: str = "ANOVA",
) -> GaugeRRReport:
    """
    Main entry point for Gauge R&R analysis.
    measurements, parts, operators must be aligned arrays of equal length.
    """
    measurements = np.array(measurements, dtype=float)
    parts        = np.array(parts)
    operators    = np.array(operators)

    # ── Input validation ────────────────────────────────────────────────────
    if len(measurements) < 6:
        raise ValueError(
            f"GRR study requires at least 6 measurements "
            f"(2 parts × 2 operators × 1 replicate minimum). Got {len(measurements)}."
        )
    if len(measurements) != len(parts) or len(measurements) != len(operators):
        raise ValueError(
            f"measurements, parts, and operators must have equal length. "
            f"Got: measurements={len(measurements)}, "
            f"parts={len(parts)}, operators={len(operators)}."
        )
    valid_mask = ~np.isnan(measurements)
    if not np.all(valid_mask):
        measurements = measurements[valid_mask]
        parts        = parts[valid_mask]
        operators    = operators[valid_mask]

    unique_parts = np.unique(parts)
    unique_operators = np.unique(operators)
    n_parts = len(unique_parts)
    n_operators = len(unique_operators)
    n_total = len(measurements)
    n_replicates = n_total // (n_parts * n_operators)

    if method == "ANOVA":
        return _anova_method(measurements, parts, operators, unique_parts, unique_operators,
                             n_parts, n_operators, n_replicates, n_total, column, tolerance)
    else:
        return _xbar_r_method(measurements, parts, operators, unique_parts, unique_operators,
                               n_parts, n_operators, n_replicates, n_total, column, tolerance)


def _anova_method(measurements, parts, operators, unique_parts, unique_operators,
                  n_parts, n_operators, n_replicates, n_total, column, tolerance):
    """Two-way ANOVA with interaction for crossed Gauge R&R."""

    grand_mean = np.mean(measurements)

    # Build cell means matrix: shape (n_parts, n_operators)
    cell_means = np.zeros((n_parts, n_operators))
    cell_counts = np.zeros((n_parts, n_operators), dtype=int)
    for i, p in enumerate(unique_parts):
        for j, o in enumerate(unique_operators):
            mask = (parts == p) & (operators == o)
            if mask.sum() > 0:
                cell_means[i, j] = measurements[mask].mean()
                cell_counts[i, j] = mask.sum()

    part_means = cell_means.mean(axis=1)   # mean per part
    op_means   = cell_means.mean(axis=0)   # mean per operator

    # SS calculations
    # SS_Parts
    n_per_part = n_operators * n_replicates
    SS_parts = n_per_part * np.sum((part_means - grand_mean)**2)
    df_parts = n_parts - 1

    # SS_Operators
    n_per_op = n_parts * n_replicates
    SS_ops = n_per_op * np.sum((op_means - grand_mean)**2)
    df_ops = n_operators - 1

    # SS_Interaction (Parts x Operators)
    SS_interaction_cells = n_replicates * np.sum((cell_means - part_means[:,None] - op_means[None,:] + grand_mean)**2)
    df_interaction = df_parts * df_ops

    # SS_Error (repeatability / within-cell)
    SS_error = 0.0
    for i, p in enumerate(unique_parts):
        for j, o in enumerate(unique_operators):
            mask = (parts == p) & (operators == o)
            vals = measurements[mask]
            if len(vals) > 1:
                SS_error += np.sum((vals - vals.mean())**2)
    df_error = n_total - n_parts * n_operators

    SS_total = np.sum((measurements - grand_mean)**2)

    # Mean squares
    MS_parts       = SS_parts / df_parts if df_parts > 0 else 0
    MS_ops         = SS_ops / df_ops if df_ops > 0 else 0
    MS_interaction = SS_interaction_cells / df_interaction if df_interaction > 0 else 0
    MS_error       = SS_error / df_error if df_error > 0 else 0

    # F statistics
    # Test interaction against error
    F_interaction = MS_interaction / MS_error if MS_error > 0 else 0
    p_interaction = 1 - stats.f.cdf(F_interaction, df_interaction, df_error)

    # Test parts and operators against interaction (if interaction significant) or error
    denominator_ms = MS_interaction if p_interaction < 0.25 else MS_error
    denominator_df = df_interaction if p_interaction < 0.25 else df_error

    F_parts = MS_parts / denominator_ms if denominator_ms > 0 else 0
    p_parts = 1 - stats.f.cdf(F_parts, df_parts, denominator_df)

    F_ops = MS_ops / denominator_ms if denominator_ms > 0 else 0
    p_ops = 1 - stats.f.cdf(F_ops, df_ops, denominator_df)

    F_error = 0.0
    p_error = 1.0

    # ANOVA table
    anova_table = [
        {"source": "Parts",            "ss": round(SS_parts,6),             "df": df_parts,      "ms": round(MS_parts,6),       "f_stat": round(F_parts,4),       "p_value": round(p_parts,5)},
        {"source": "Operators",        "ss": round(SS_ops,6),               "df": df_ops,        "ms": round(MS_ops,6),         "f_stat": round(F_ops,4),         "p_value": round(p_ops,5)},
        {"source": "Parts × Operators","ss": round(SS_interaction_cells,6), "df": df_interaction,"ms": round(MS_interaction,6), "f_stat": round(F_interaction,4), "p_value": round(p_interaction,5)},
        {"source": "Repeatability",    "ss": round(SS_error,6),             "df": df_error,      "ms": round(MS_error,6),       "f_stat": 0.0,                    "p_value": 1.0},
        {"source": "Total",            "ss": round(SS_total,6),             "df": n_total-1,     "ms": 0.0,                     "f_stat": 0.0,                    "p_value": 1.0},
    ]

    # Variance components
    # sigma^2_repeatability = MS_error
    var_repeat = max(0.0, MS_error)

    # sigma^2_interaction = (MS_interaction - MS_error) / n_replicates
    var_interaction = max(0.0, (MS_interaction - MS_error) / n_replicates)

    # sigma^2_operator = (MS_ops - MS_interaction) / (n_parts * n_replicates)
    var_operator = max(0.0, (MS_ops - MS_interaction) / (n_parts * n_replicates))

    # sigma^2_part = (MS_parts - MS_interaction) / (n_operators * n_replicates)
    var_part = max(0.0, (MS_parts - MS_interaction) / (n_operators * n_replicates))

    # Combined
    var_reproducibility = var_operator + var_interaction
    var_grr = var_repeat + var_reproducibility
    var_total = var_grr + var_part

    if var_total == 0:
        var_total = 1e-10  # avoid division by zero

    def make_vc(source, variance):
        sd = float(np.sqrt(max(0, variance)))
        pct_c = float(variance / var_total * 100)
        sv = 6 * sd
        pct_sv = float(sv / (6 * np.sqrt(var_total)) * 100)
        return VarianceComponent(source=source, variance=round(variance,8),
                                 std_dev=round(sd,6), pct_contribution=round(pct_c,2),
                                 study_var=round(sv,6), pct_study_var=round(pct_sv,2))

    vc_repeat  = make_vc("Repeatability (EV)", var_repeat)
    vc_reprod  = make_vc("Reproducibility (AV)", var_reproducibility)
    vc_inter   = make_vc("Operator × Part", var_interaction)
    vc_grr     = make_vc("Gauge R&R (GRR)", var_grr)
    vc_part    = make_vc("Part-to-Part (PV)", var_part)
    vc_total   = make_vc("Total Variation (TV)", var_total)

    # ndc
    ndc = max(1, int(np.floor(1.41 * np.sqrt(var_part / var_grr)))) if var_grr > 0 else 999

    # Tolerance-based metrics
    pct_tol = None
    if tolerance and tolerance > 0:
        pct_tol = round(vc_grr.study_var / tolerance * 100, 2)

    # Verdict based on %GRR study variation
    pct_grr = vc_grr.pct_study_var
    if pct_grr < 10:
        verdict = "Acceptable"
        verdict_detail = f"%GRR = {pct_grr:.1f}% < 10% — Measurement system is acceptable."
        capa_required = False
    elif pct_grr < 30:
        verdict = "Marginal"
        verdict_detail = f"%GRR = {pct_grr:.1f}% between 10–30% — Conditionally acceptable. Improve if possible."
        capa_required = True
    else:
        verdict = "Unacceptable"
        verdict_detail = f"%GRR = {pct_grr:.1f}% > 30% — Measurement system is inadequate. Must be improved."
        capa_required = True

    capa_notes = _build_grr_capa(vc_repeat, vc_reprod, vc_inter, vc_grr, vc_part,
                                  ndc, p_interaction, n_operators, n_parts, pct_tol)

    chart_data = _build_chart_data(measurements, parts, operators, unique_parts, unique_operators,
                                   cell_means, part_means, op_means)

    return GaugeRRReport(
        study_type="Crossed", method="ANOVA",
        n_parts=n_parts, n_operators=n_operators, n_replicates=n_replicates, n_total=n_total,
        column=column,
        anova_table=anova_table,
        repeatability=vc_repeat, reproducibility=vc_reprod,
        operator_by_part=vc_inter, gauge_rr=vc_grr,
        part_to_part=vc_part, total_variation=vc_total,
        ndc=ndc, tolerance=tolerance, pct_tolerance=pct_tol,
        verdict=verdict, verdict_detail=verdict_detail,
        capa_required=capa_required, capa_notes=capa_notes,
        by_operator_data=chart_data["by_operator"],
        part_variation_data=chart_data["part_variation"],
        interaction_data=chart_data["interaction"],
    )


def _xbar_r_method(measurements, parts, operators, unique_parts, unique_operators,
                    n_parts, n_operators, n_replicates, n_total, column, tolerance):
    """Classical Xbar/R method for Gauge R&R."""
    d2_map = {2:1.128,3:1.693,4:2.059,5:2.326,6:2.534,7:2.704,8:2.847,9:2.970,10:3.078}
    d2_r = d2_map.get(n_replicates, 1.128)
    d2_op = d2_map.get(n_operators, 1.128)

    # Operator averages and ranges
    op_ranges, op_means_list = [], []
    for o in unique_operators:
        vals = measurements[operators == o]
        # Reshape by part
        part_vals = [measurements[(operators==o)&(parts==p)] for p in unique_parts]
        ranges = [v.max()-v.min() for v in part_vals if len(v)>1]
        op_ranges.append(np.mean(ranges) if ranges else 0)
        op_means_list.append(np.mean(vals))

    r_bar = np.mean(op_ranges)
    EV = r_bar / d2_r * 5.15   # 5.15 = 99% spread (use 6 for 6-sigma basis)
    EV_sigma = r_bar / d2_r

    # AV from operator means
    op_means_arr = np.array(op_means_list)
    x_diff = op_means_arr.max() - op_means_arr.min()
    AV_raw = np.sqrt(max(0, (x_diff / d2_op)**2 - (EV_sigma**2) / (n_parts * n_replicates)))
    AV_sigma = AV_raw

    GRR_sigma = np.sqrt(EV_sigma**2 + AV_sigma**2)

    # Part variation
    part_means_arr = np.array([measurements[parts==p].mean() for p in unique_parts])
    part_range = part_means_arr.max() - part_means_arr.min()
    d2_parts = d2_map.get(n_parts, 3.078)
    PV_sigma = part_range / d2_parts

    TV_sigma = np.sqrt(GRR_sigma**2 + PV_sigma**2)
    if TV_sigma == 0: TV_sigma = 1e-10

    def make_vc2(source, sd):
        variance = sd**2
        pct_c = variance / TV_sigma**2 * 100
        sv = 6 * sd
        pct_sv = sv / (6 * TV_sigma) * 100
        return VarianceComponent(source=source, variance=round(variance,8), std_dev=round(sd,6),
                                 pct_contribution=round(pct_c,2), study_var=round(sv,6), pct_study_var=round(pct_sv,2))

    vc_repeat = make_vc2("Repeatability (EV)", EV_sigma)
    vc_reprod = make_vc2("Reproducibility (AV)", AV_sigma)
    vc_inter  = make_vc2("Operator × Part", 0.0)
    vc_grr    = make_vc2("Gauge R&R (GRR)", GRR_sigma)
    vc_part   = make_vc2("Part-to-Part (PV)", PV_sigma)
    vc_total  = make_vc2("Total Variation (TV)", TV_sigma)

    ndc = max(1, int(np.floor(1.41 * np.sqrt(PV_sigma**2 / GRR_sigma**2)))) if GRR_sigma > 0 else 999
    pct_tol = round(vc_grr.study_var / tolerance * 100, 2) if tolerance and tolerance > 0 else None
    pct_grr = vc_grr.pct_study_var

    if pct_grr < 10: verdict, capa_required = "Acceptable", False
    elif pct_grr < 30: verdict, capa_required = "Marginal", True
    else: verdict, capa_required = "Unacceptable", True
    verdict_detail = f"%GRR = {pct_grr:.1f}% — {'Acceptable' if pct_grr<10 else 'Conditionally acceptable' if pct_grr<30 else 'Inadequate — must improve'}."

    cell_means = np.array([[measurements[(parts==p)&(operators==o)].mean()
                            for o in unique_operators] for p in unique_parts])
    part_means_v = cell_means.mean(axis=1)
    op_means_v   = cell_means.mean(axis=0)

    chart_data = _build_chart_data(measurements, parts, operators, unique_parts, unique_operators,
                                   cell_means, part_means_v, op_means_v)
    anova_table = [{"source":"XbarR method — no ANOVA table","ss":0,"df":0,"ms":0,"f_stat":0,"p_value":1}]
    capa_notes = _build_grr_capa(vc_repeat, vc_reprod, vc_inter, vc_grr, vc_part, ndc, 1.0, n_operators, n_parts, pct_tol)

    return GaugeRRReport(
        study_type="Crossed", method="XbarR",
        n_parts=n_parts, n_operators=n_operators, n_replicates=n_replicates, n_total=n_total,
        column=column, anova_table=anova_table,
        repeatability=vc_repeat, reproducibility=vc_reprod,
        operator_by_part=vc_inter, gauge_rr=vc_grr,
        part_to_part=vc_part, total_variation=vc_total,
        ndc=ndc, tolerance=tolerance, pct_tolerance=pct_tol,
        verdict=verdict, verdict_detail=verdict_detail,
        capa_required=capa_required, capa_notes=capa_notes,
        by_operator_data=chart_data["by_operator"],
        part_variation_data=chart_data["part_variation"],
        interaction_data=chart_data["interaction"],
    )


def _build_grr_capa(vc_r, vc_a, vc_i, vc_grr, vc_part, ndc, p_interaction, n_ops, n_parts, pct_tol):
    notes = []
    pct = vc_grr.pct_study_var

    # EV vs AV breakdown
    if vc_r.pct_study_var > vc_a.pct_study_var:
        notes.append(f"Repeatability ({vc_r.pct_study_var:.1f}%) dominates — gauge precision issue. "
                     f"Check fixture stability, gauge calibration, and measurement technique.")
    else:
        notes.append(f"Reproducibility ({vc_a.pct_study_var:.1f}%) dominates — operator influence. "
                     f"Standardize measurement procedure and provide operator training.")

    # Interaction
    if p_interaction < 0.05:
        notes.append(f"Significant Parts × Operators interaction (p<0.05) — operators measure different parts inconsistently. "
                     f"Check for part fixturing issues or operator technique variation.")

    # ndc
    if ndc < 2:
        notes.append(f"ndc = {ndc} — gauge cannot distinguish between parts. Completely inadequate for process control.")
    elif ndc < 5:
        notes.append(f"ndc = {ndc} — gauge can make only {ndc} distinct categories. Industry standard requires ndc ≥ 5.")
    else:
        notes.append(f"ndc = {ndc} ≥ 5 — gauge can distinguish {ndc} distinct part categories. Acceptable for process control.")

    # Tolerance
    if pct_tol is not None:
        if pct_tol > 30:
            notes.append(f"GRR consumes {pct_tol:.1f}% of tolerance — measurement uncertainty is too high for this specification.")
        elif pct_tol > 10:
            notes.append(f"GRR consumes {pct_tol:.1f}% of tolerance — marginal. Consider tighter gauge or wider tolerance.")
        else:
            notes.append(f"GRR consumes {pct_tol:.1f}% of tolerance — acceptable measurement uncertainty.")

    # Part variation
    if vc_part.pct_study_var < 50:
        notes.append(f"Part-to-part variation ({vc_part.pct_study_var:.1f}%) is low relative to GRR — "
                     f"parts selected may not represent full process range. Repeat study with more diverse sample.")

    return notes


def _build_chart_data(measurements, parts, operators, unique_parts, unique_operators,
                      cell_means, part_means, op_means):
    """Build chart data for operator comparison and interaction plots."""

    # By operator: all measurements per operator
    by_op = {}
    for o in unique_operators:
        vals = measurements[operators == o].tolist()
        by_op[str(o)] = {"values": [round(v,6) for v in vals], "mean": round(float(np.mean(vals)),6)}

    # Part variation: part means + range
    part_var = {
        "parts": [str(p) for p in unique_parts],
        "means": [round(float(m),6) for m in part_means],
        "all_values": {str(p): [round(float(v),6) for v in measurements[parts==p]] for p in unique_parts},
    }

    # Interaction: operator means per part
    interaction = {
        "parts": [str(p) for p in unique_parts],
        "operators": [str(o) for o in unique_operators],
        "cell_means": cell_means.tolist(),
        "op_means": [round(float(m),6) for m in op_means],
    }

    return {"by_operator": by_op, "part_variation": part_var, "interaction": interaction}


def parse_grr_csv(file_bytes: bytes, filename: str, measurement_col: str = None):
    """
    Parse a GRR study CSV with columns: Part, Operator, Measurement
    (or similar — auto-detects column names).
    Returns (measurements, parts, operators, column_name)
    """
    import pandas as pd, io
    buf = io.BytesIO(file_bytes)
    if filename.lower().endswith(('.xlsx', '.xls')):
        df = pd.read_excel(buf)
    else:
        sample = file_bytes[:2048].decode('utf-8', errors='replace')
        sep = '\t' if '\t' in sample else ';' if ';' in sample else ','
        buf.seek(0)
        df = pd.read_csv(buf, sep=sep)

    df.columns = [c.strip() for c in df.columns]

    # Auto-detect columns
    part_col = next((c for c in df.columns if 'part' in c.lower()), None)
    op_col   = next((c for c in df.columns if any(x in c.lower() for x in ['oper', 'appraiser', 'inspector'])), None)
    import pandas as pd

    # P0-STAT-8 (2026-07-06 campaign): the standard AIAG study format includes a
    # numeric Trial/Replicate column. The old detector took the FIRST numeric
    # non-Part/Operator column — which was Trial — and silently reported
    # %GRR = 100% "Unacceptable" on a perfectly good gauge. Index-like columns
    # are now excluded, and if more than one measurement candidate remains the
    # caller must choose explicitly rather than us guessing.
    _INDEX_LIKE = ('trial', 'replicate', 'repeat', 'rep', 'run', 'cycle',
                   'sample', 'order', 'seq', 'index', 'id', 'no', 'num')

    def _is_index_like(name: str) -> bool:
        tokens = [t for t in ''.join(ch if ch.isalnum() else ' ' for ch in name.lower()).split() if t]
        return any(t in _INDEX_LIKE for t in tokens)

    numeric_cols = [
        c for c in df.columns
        if c not in [part_col, op_col]
        and (
            pd.api.types.is_numeric_dtype(df[c])
            or df[c].apply(lambda x: isinstance(x, (int, float)) and not pd.isna(x)).all()
        )
    ]
    meas_cols = [c for c in numeric_cols if not _is_index_like(c)]

    if not part_col or not op_col:
        raise ValueError(f"Could not find Part/Operator columns. Found: {list(df.columns)}. "
                         f"Please name columns 'Part', 'Operator', 'Measurement'.")

    if measurement_col:
        # Caller specified the measurement column explicitly — honour it.
        match = next((c for c in df.columns if c.lower() == measurement_col.strip().lower()), None)
        if match is None or match in (part_col, op_col):
            raise ValueError(
                f"Measurement column '{measurement_col}' not found in file. "
                f"Available: {', '.join(str(c) for c in df.columns)}."
            )
        if not pd.api.types.is_numeric_dtype(df[match]):
            raise ValueError(f"Measurement column '{measurement_col}' is not numeric.")
        meas_col = match
    elif len(meas_cols) == 1:
        meas_col = meas_cols[0]
    elif len(meas_cols) > 1:
        raise ValueError(
            f"Multiple possible measurement columns found: {', '.join(meas_cols)}. "
            f"Please specify which one to analyze (measurement column parameter), "
            f"or remove the extra numeric columns from the file."
        )
    elif numeric_cols:
        # Everything numeric looked index-like (e.g. only a Trial column) —
        # refuse rather than analyze an index and report a false verdict.
        raise ValueError(
            f"Only index-like numeric columns found ({', '.join(numeric_cols)}). "
            f"These look like trial/run counters, not measurements. "
            f"Please include a numeric measurement column, or specify one explicitly."
        )
    else:
        available = ", ".join(str(c) for c in df.columns)
        raise ValueError(
            f"Could not find a numeric measurement column. "
            f"Available columns: {available}. "
            "Please ensure measurements are numeric and not formatted as text."
        )

    df = df.dropna(subset=[part_col, op_col, meas_col])
    return (df[meas_col].values.astype(float),
            df[part_col].values,
            df[op_col].values,
            meas_col)
