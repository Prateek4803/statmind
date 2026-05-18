"""
    })


import dataclasses
import itertools
import math
from typing import Optional

# ── Structured JSON error handling ───────────────────────────────────────────
# Add this near the top of main.py (after app = FastAPI()):
#
# from fastapi import Request
# from fastapi.responses import JSONResponse
#
# @app.exception_handler(Exception)
# async def global_exception_handler(request: Request, exc: Exception):
#     import logging
#     logging.error(f"Unhandled exception: {exc}", exc_info=True)
#     return JSONResponse(
#         status_code=500,
#         content={"detail": str(exc), "type": type(exc).__name__},
#     )


# ══ PASTE FROM HERE INTO BOTTOM OF main.py ═══════════════════════════════════

# ── Cpk Confidence Intervals (chi-squared/Bissell 1990) ─────────────────────
@app.post("/api/v1/capability/ci")
async def capability_ci(request: Request):
    """
    Compute 95% confidence intervals for Cp, Cpk, Pp, Ppk.

    Uses chi-squared method for Cp/Pp and Bissell (1990) approximation
    for Cpk/Ppk.  The lower Cpk CI is the key number for supplier
    qualification — Apple/AIAG require lower CI ≥ 1.33.
    """
    body = await request.json()
    from scipy import stats as _stats

    n   = max(int(body.get("n",   30)), 3)
    cp  = float(body.get("cp",  1.0))
    cpk = float(body.get("cpk", 1.0))
    pp  = float(body.get("pp",  1.0))
    ppk = float(body.get("ppk", 1.0))
    alpha = 0.05

    chi2_lo = _stats.chi2.ppf(alpha / 2,       n - 1)
    chi2_hi = _stats.chi2.ppf(1 - alpha / 2,   n - 1)

    # Cp / Pp: chi-squared CI
    cp_ci_lo  = round(cp  * math.sqrt((n - 1) / chi2_hi), 4)
    cp_ci_hi  = round(cp  * math.sqrt((n - 1) / chi2_lo), 4)
    pp_ci_lo  = round(pp  * math.sqrt((n - 1) / chi2_hi), 4)
    pp_ci_hi  = round(pp  * math.sqrt((n - 1) / chi2_lo), 4)

    # Cpk / Ppk: Bissell (1990) approximation
    cpk_se    = math.sqrt(max(cpk ** 2 / (9 * n) + 1 / (2 * (n - 1)), 1e-9))
    cpk_ci_lo = round(cpk - 1.96 * cpk_se, 4)
    cpk_ci_hi = round(cpk + 1.96 * cpk_se, 4)
    ppk_se    = math.sqrt(max(ppk ** 2 / (9 * n) + 1 / (2 * (n - 1)), 1e-9))
    ppk_ci_lo = round(ppk - 1.96 * ppk_se, 4)
    ppk_ci_hi = round(ppk + 1.96 * ppk_se, 4)

    supplier_qualified = cpk_ci_lo >= 1.33
    meets_threshold    = cpk >= 1.33

    if supplier_qualified:
        interpretation = (
            "✅ Lower Cpk CI ≥ 1.33 — SUPPLIER QUALIFIED (Apple/AIAG standard)"
        )
    elif meets_threshold:
        interpretation = (
            f"⚠️ Cpk={cpk:.3f} ≥ 1.33 but lower 95% CI = {cpk_ci_lo:.3f} < 1.33 "
            "— insufficient statistical evidence of capability. Increase sample size."
        )
    else:
        interpretation = (
            f"❌ Cpk={cpk:.3f} < 1.33 — process is not capable at the 1.33 threshold."
        )

    return jd({
        "n":             n,
        "confidence":    "95%",
        "cp":  {"estimate": cp,  "ci_lo": cp_ci_lo,  "ci_hi": cp_ci_hi},
        "cpk": {
            "estimate":          cpk,
            "ci_lo":             cpk_ci_lo,
            "ci_hi":             cpk_ci_hi,
            "supplier_qualified": supplier_qualified,
        },
        "pp":  {"estimate": pp,  "ci_lo": pp_ci_lo,  "ci_hi": pp_ci_hi},
        "ppk": {"estimate": ppk, "ci_lo": ppk_ci_lo, "ci_hi": ppk_ci_hi},
        "interpretation": interpretation,
    })


# ── Outlier Detection ─────────────────────────────────────────────────────────
@app.post("/api/v1/outliers/analyze")
async def outliers_analyze(
    file:   UploadFile = File(...),
    column: str        = Query(...),
    method: str        = Query("all"),
    alpha:  float      = Query(0.05),
):
    content = await file.read()
    try:
        result = parse_any_file(content, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found. "
                                 f"Available: {result.numeric_columns}")
    try:
        from outliers import detect_outliers
        data = result.df[column].dropna().values.astype(float)
        r    = detect_outliers(data, column, method=method, alpha=alpha)
        return jd(dataclasses.asdict(r))
    except ImportError:
        raise HTTPException(500, "outliers.py not found on server")
    except Exception as e:
        raise HTTPException(400, str(e))


# ── TOST Equivalence Test ─────────────────────────────────────────────────────
@app.post("/api/v1/equivalence/analyze")
async def equivalence_analyze(
    file:  UploadFile = File(...),
    col_a: str        = Query(...),
    col_b: str        = Query(...),
    delta: float      = Query(None),
    alpha: float      = Query(0.05),
):
    content = await file.read()
    try:
        result = parse_any_file(content, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    for col in (col_a, col_b):
        if col not in result.df.columns:
            raise HTTPException(404, f"Column '{col}' not found.")
    try:
        from equivalence_test import tost_equivalence
        a = result.df[col_a].dropna().values.astype(float)
        b = result.df[col_b].dropna().values.astype(float)
        r = tost_equivalence(a, b, delta=delta, alpha=alpha,
                             name_a=col_a, name_b=col_b)
        return jd(dataclasses.asdict(r))
    except ImportError:
        raise HTTPException(500, "equivalence_test.py not found on server")
    except Exception as e:
        raise HTTPException(400, str(e))


# ── Run Chart ─────────────────────────────────────────────────────────────────
@app.post("/api/v1/runchart/analyze")
async def runchart_analyze(
    file:   UploadFile = File(...),
    column: str        = Query(...),
):
    content = await file.read()
    try:
        result = parse_any_file(content, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found.")
    from scipy import stats as _stats

    data   = result.df[column].dropna().values.astype(float)
    n      = len(data)
    median = float(np.median(data))
    mean   = float(data.mean())

    # Swed-Eisenhart runs test (above/below median)
    above    = [1 if x > median else 0 for x in data if x != median]
    n_above  = sum(above)
    n_below  = len(above) - n_above
    n_tot    = n_above + n_below
    runs     = 1 + sum(1 for i in range(1, len(above)) if above[i] != above[i - 1]) if above else 0

    if n_tot > 1:
        runs_exp = 2 * n_above * n_below / n_tot + 1
        runs_var = (2 * n_above * n_below * (2 * n_above * n_below - n_tot)
                    / (n_tot ** 2 * (n_tot - 1))) if n_tot > 2 else 1.0
        z_runs   = (runs - runs_exp) / max(math.sqrt(runs_var), 1e-9)
        p_runs   = float(2 * (1 - _stats.norm.cdf(abs(z_runs))))
    else:
        runs_exp = runs_var = z_runs = 0.0
        p_runs   = 1.0

    runs_verdict = "Non-random pattern detected" if p_runs < 0.05 else "Random — no pattern detected"

    # Cox-Stuart trend test
    m       = n // 2
    pairs   = [(data[i], data[i + m]) for i in range(m)]
    n_plus  = sum(1 for a, b in pairs if b > a)
    n_minus = sum(1 for a, b in pairs if b < a)
    n_eff   = n_plus + n_minus
    p_trend = float(2 * _stats.binom.cdf(min(n_plus, n_minus), n_eff, 0.5)) if n_eff > 0 else 1.0
    trend_verdict = "Significant trend detected" if p_trend < 0.05 else "No significant trend"

    return jd({
        "column": column, "n": n, "median": round(median, 4), "mean": round(mean, 4),
        "data":   [round(float(x), 4) for x in data],
        "runs_test": {
            "runs": runs, "expected": round(runs_exp, 2),
            "z": round(z_runs, 3), "p": round(p_runs, 4), "verdict": runs_verdict,
        },
        "trend_test": {
            "n_plus": n_plus, "n_minus": n_minus,
            "p": round(p_trend, 4), "verdict": trend_verdict,
        },
        "overall_verdict": (
            "Non-random" if p_runs < 0.05 or p_trend < 0.05
            else "Random — process appears stable"
        ),
    })


# ── CUSUM / EWMA ──────────────────────────────────────────────────────────────
@app.post("/api/v1/cusum/analyze")
async def cusum_analyze(
    file:   UploadFile = File(...),
    column: str        = Query(...),
    k:      float      = Query(0.5),
    h:      float      = Query(5.0),
    lam:    float      = Query(0.2),
    L:      float      = Query(3.0),
):
    content = await file.read()
    try:
        result = parse_any_file(content, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found.")

    data   = result.df[column].dropna().values.astype(float)
    n      = len(data)
    mean   = float(data.mean())
    std    = float(data.std(ddof=1)) if n > 1 else 1.0

    # CUSUM
    cusum_pos = [0.0]
    cusum_neg = [0.0]
    for x in data:
        z = (x - mean) / std
        cusum_pos.append(max(0.0, cusum_pos[-1] + z - k))
        cusum_neg.append(min(0.0, cusum_neg[-1] + z + k))
    cusum_pos = cusum_pos[1:]
    cusum_neg = cusum_neg[1:]
    cusum_signals = [i for i, (p, q) in enumerate(zip(cusum_pos, cusum_neg))
                     if p > h or abs(q) > h]

    # EWMA
    cl  = mean
    ucl = mean + L * std * math.sqrt(lam / (2 - lam))
    lcl = mean - L * std * math.sqrt(lam / (2 - lam))
    ewma_vals = [mean]
    for x in data:
        ewma_vals.append(lam * x + (1 - lam) * ewma_vals[-1])
    ewma_vals = ewma_vals[1:]
    ewma_signals = [i for i, e in enumerate(ewma_vals) if e > ucl or e < lcl]

    return jd({
        "column": column, "n": n, "mean": round(mean, 4), "std": round(std, 4),
        "cusum": {
            "k": k, "h": h,
            "cusum_pos": [round(float(v), 4) for v in cusum_pos],
            "cusum_neg": [round(float(v), 4) for v in cusum_neg],
            "signals":   cusum_signals,
        },
        "ewma": {
            "lambda": lam, "L": L,
            "center_line": round(cl, 4),
            "ucl": round(ucl, 4), "lcl": round(lcl, 4),
            "ewma_values": [round(float(v), 4) for v in ewma_vals],
            "signals":     ewma_signals,
        },
    })


# ── Correlation Matrix ────────────────────────────────────────────────────────
@app.post("/api/v1/correlation/matrix")
async def correlation_matrix(
    file:   UploadFile = File(...),
    method: str        = Query("pearson"),
    alpha:  float      = Query(0.05),
):
    content = await file.read()
    try:
        result = parse_any_file(content, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    from scipy import stats as _stats

    cols = result.numeric_columns
    df   = result.df[cols].dropna()
    n    = len(df)

    corr_matrix: dict = {}
    pval_matrix: dict = {}
    for c1 in cols:
        corr_matrix[c1] = {}
        pval_matrix[c1] = {}
        for c2 in cols:
            if c1 == c2:
                corr_matrix[c1][c2] = 1.0
                pval_matrix[c1][c2] = 0.0
            else:
                if method == "spearman":
                    r, p = _stats.spearmanr(df[c1], df[c2])
                else:
                    r, p = _stats.pearsonr(df[c1], df[c2])
                corr_matrix[c1][c2] = round(float(r), 4)
                pval_matrix[c1][c2] = round(float(p), 5)

    return jd({
        "columns":           cols,
        "method":            method.capitalize(),
        "n":                 n,
        "correlation_matrix": corr_matrix,
        "p_values":          pval_matrix,
    })


# ── Sample Size Calculator ────────────────────────────────────────────────────
@app.post("/api/v1/sample-size/calculate")
async def sample_size_calculate(request: Request):
    body = await request.json()
    from scipy import stats as _stats

    study_type  = body.get("study_type",    "capability")
    cpk_base    = float(body.get("cpk_baseline", 1.33))
    cpk_shift   = float(body.get("cpk_shift",    0.20))
    power_val   = float(body.get("power",        0.90))
    alpha_val   = float(body.get("alpha",        0.05))

    # Cpk detection: Bissell variance of Cpk → approximate sample size
    z_a = float(_stats.norm.ppf(1 - alpha_val / 2))
    z_b = float(_stats.norm.ppf(power_val))
    n_approx = math.ceil(
        (z_a + z_b) ** 2 * (1 + 9 * cpk_base ** 2) / (9 * cpk_shift ** 2)
    )
    n_approx = max(n_approx, 5)

    # Power curve
    ns     = list(range(5, min(n_approx * 3, 501), 5))
    powers = []
    for ni in ns:
        se  = math.sqrt(max(cpk_base ** 2 / (9 * ni) + 1 / (2 * (ni - 1)), 1e-9))
        z_e = abs(cpk_shift) / se
        pow_val = float(_stats.norm.cdf(z_e - z_a) + _stats.norm.cdf(-z_e - z_a))
        powers.append(round(min(max(pow_val, 0.0), 1.0), 4))

    return jd({
        "study_type":      study_type,
        "required_n":      n_approx,
        "cpk_baseline":    cpk_base,
        "cpk_shift":       cpk_shift,
        "power":           power_val,
        "alpha":           alpha_val,
        "power_curve":     {"n": ns, "power": powers},
        "interpretation": (
            f"Need n={n_approx} measurements to detect a Cpk shift from "
            f"{cpk_base} to {cpk_base - cpk_shift:.2f} with "
            f"{round(power_val * 100)}% power at α={alpha_val}."
        ),
    })


# ── Two-Way ANOVA ─────────────────────────────────────────────────────────────
@app.post("/api/v1/hypothesis/two-way-anova")
async def two_way_anova(request: Request):
    body = await request.json()
    import pandas as _pd
    from scipy import stats as _stats

    try:
        response_vals = [float(v) for v in body["data"]]
        factor_a      = [str(v) for v in body["factor_a"]]
        factor_b      = [str(v) for v in body["factor_b"]]
        name_a        = str(body.get("name_a",    "Factor A"))
        name_b        = str(body.get("name_b",    "Factor B"))
        resp_name     = str(body.get("response",  "Response"))
        alpha_val     = float(body.get("alpha",   0.05))
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(422, f"Invalid request body: {e}")

    df       = _pd.DataFrame({"y": response_vals, "A": factor_a, "B": factor_b})
    levels_a = sorted(df["A"].unique())
    levels_b = sorted(df["B"].unique())
    n_a, n_b = len(levels_a), len(levels_b)
    N        = len(df)
    grand    = float(df["y"].mean())

    means_a    = df.groupby("A")["y"].mean()
    means_b    = df.groupby("B")["y"].mean()
    cell_means = df.groupby(["A", "B"])["y"].mean()
    n_rep      = N // max(n_a * n_b, 1)

    ss_a   = n_b * n_rep * sum((means_a[la] - grand) ** 2 for la in levels_a)
    ss_b   = n_a * n_rep * sum((means_b[lb] - grand) ** 2 for lb in levels_b)
    ss_ab  = n_rep * sum(
        (cell_means.get((la, lb), grand) - means_a[la] - means_b[lb] + grand) ** 2
        for la in levels_a for lb in levels_b
    )
    ss_err = sum(
        (row["y"] - cell_means.get((row["A"], row["B"]), grand)) ** 2
        for _, row in df.iterrows()
    )
    ss_tot = sum((v - grand) ** 2 for v in df["y"])

    df_a, df_b, df_ab = n_a - 1, n_b - 1, (n_a - 1) * (n_b - 1)
    df_err = N - n_a * n_b

    ms_a   = ss_a   / df_a   if df_a   > 0 else 0.0
    ms_b   = ss_b   / df_b   if df_b   > 0 else 0.0
    ms_ab  = ss_ab  / df_ab  if df_ab  > 0 else 0.0
    ms_err = ss_err / max(df_err, 1)

    f_a  = ms_a  / ms_err
    f_b  = ms_b  / ms_err
    f_ab = ms_ab / ms_err

    p_a  = float(1 - _stats.f.cdf(f_a,  df_a,  df_err))
    p_b  = float(1 - _stats.f.cdf(f_b,  df_b,  df_err))
    p_ab = float(1 - _stats.f.cdf(f_ab, df_ab, df_err))

    def fmt(v): return round(float(v), 4)

    return jd({
        "success":     True,
        "response":    resp_name,
        "factor_a":    name_a,
        "factor_b":    name_b,
        "n_total":     N,
        "grand_mean":  fmt(grand),
        "anova_table": [
            {"source": name_a,              "ss": fmt(ss_a),  "df": df_a,  "ms": fmt(ms_a),  "f": fmt(f_a),  "p": fmt(p_a),  "significant": p_a  < alpha_val},
            {"source": name_b,              "ss": fmt(ss_b),  "df": df_b,  "ms": fmt(ms_b),  "f": fmt(f_b),  "p": fmt(p_b),  "significant": p_b  < alpha_val},
            {"source": f"{name_a}×{name_b}","ss": fmt(ss_ab), "df": df_ab, "ms": fmt(ms_ab), "f": fmt(f_ab), "p": fmt(p_ab), "significant": p_ab < alpha_val},
            {"source": "Error",             "ss": fmt(ss_err),"df": df_err,"ms": fmt(ms_err),"f": None,       "p": None,      "significant": False},
            {"source": "Total",             "ss": fmt(ss_tot),"df": N - 1, "ms": None,        "f": None,       "p": None,      "significant": False},
        ],
        "interaction_significant": p_ab < alpha_val,
        "conclusion": (
            f"Significant interaction between {name_a} and {name_b} "
            f"(p={p_ab:.4f}) — interpret main effects with caution."
            if p_ab < alpha_val else
            f"No significant interaction. "
            f"{name_a}: {'significant' if p_a < alpha_val else 'not significant'} "
            f"(p={p_a:.4f}). "
            f"{name_b}: {'significant' if p_b < alpha_val else 'not significant'} "
            f"(p={p_b:.4f})."
        ),
    })


# ── RSM — Response Surface Methodology ───────────────────────────────────────
@app.post("/api/v1/rsm/design")
async def rsm_design(request: Request):
    """Generate a Central Composite Design (CCD) or Box-Behnken matrix."""
    body         = await request.json()
    factor_names = body.get("factor_names",  ["X1", "X2"])
    factor_levels= body.get("factor_levels", {})
    design_type  = body.get("design_type",   "ccd")
    center_pts   = int(body.get("center_points", 3))
    alpha_axial  = float(body.get("alpha", 1.414))
    k            = len(factor_names)

    runs: list = []
    if design_type == "ccd":
        for combo in itertools.product([-1, 1], repeat=k):
            run = {"run_type": "factorial"}
            for i, nm in enumerate(factor_names): run[nm] = float(combo[i])
            runs.append(run)
        for i, nm in enumerate(factor_names):
            for sign in (-1, 1):
                run = {"run_type": "axial"}
                for j, nm2 in enumerate(factor_names):
                    run[nm2] = round(sign * alpha_axial, 4) if j == i else 0.0
                runs.append(run)
    elif design_type == "bbd" and k == 3:
        bbd = [(1,1,0),(-1,1,0),(1,-1,0),(-1,-1,0),(1,0,1),(-1,0,1),
               (1,0,-1),(-1,0,-1),(0,1,1),(0,-1,1),(0,1,-1),(0,-1,-1)]
        for combo in bbd:
            run = {"run_type": "bbd"}
            for i, nm in enumerate(factor_names): run[nm] = float(combo[i])
            runs.append(run)
    else:
        raise HTTPException(422, f"Unsupported design type '{design_type}' for k={k}")

    for _ in range(center_pts):
        run = {"run_type": "center"}
        for nm in factor_names: run[nm] = 0.0
        runs.append(run)

    # Decode coded to actual
    c2a = {}
    for nm in factor_names:
        levels = factor_levels.get(nm, [-1.0, 1.0])
        lo, hi = float(levels[0]), float(levels[1])
        c2a[nm] = {"center": (lo + hi) / 2, "half_range": (hi - lo) / 2}

    for i, run in enumerate(runs):
        run["run"] = i + 1
        run["response"] = None
        for nm in factor_names:
            run[f"{nm}_actual"] = round(
                c2a[nm]["center"] + run[nm] * c2a[nm]["half_range"], 4
            )

    terms = (["intercept"] + factor_names +
             [f"{nm}²" for nm in factor_names] +
             [f"{factor_names[i]}×{factor_names[j]}"
              for i in range(k) for j in range(i + 1, k)])

    return jd({
        "design_type":   design_type.upper(),
        "k":             k,
        "n_runs":        len(runs),
        "center_points": center_pts,
        "alpha":         alpha_axial,
        "factor_names":  factor_names,
        "factor_levels": factor_levels,
        "run_matrix":    runs,
        "model_terms":   terms,
    })


@app.post("/api/v1/rsm/analyze")
async def rsm_analyze(request: Request):
    """Fit a quadratic RSM model and find the optimal settings."""
    body = await request.json()
    from scipy.optimize import minimize

    try:
        factor_names = body["factor_names"]
        run_matrix   = body["run_matrix"]
        responses    = [float(v) for v in body["responses"]]
        goal         = body.get("goal", "maximize")
        target_val   = body.get("target_value")
        factor_levels= body.get("factor_levels", {})
        alpha_axial  = float(body.get("alpha", 1.414))
    except (KeyError, TypeError) as e:
        raise HTTPException(422, f"Invalid request body: {e}")

    k     = len(factor_names)
    n_run = len(responses)

    # Build model matrix [1, x1,..,xk, x1²,..,xk², x1x2,..]
    X_coded = np.array([[row.get(nm, 0) for nm in factor_names]
                         for row in run_matrix], dtype=float)
    y = np.array(responses, dtype=float)

    cols = ([np.ones(n_run)] +
            [X_coded[:, i] for i in range(k)] +
            [X_coded[:, i] ** 2 for i in range(k)] +
            [X_coded[:, i] * X_coded[:, j]
             for i in range(k) for j in range(i + 1, k)])
    X_model = np.column_stack(cols)

    beta, *_ = np.linalg.lstsq(X_model, y, rcond=None)
    y_pred   = X_model @ beta
    ss_res   = float(np.sum((y - y_pred) ** 2))
    ss_tot   = float(np.sum((y - y.mean()) ** 2))
    r2       = 1 - ss_res / max(ss_tot, 1e-9)
    n_params = X_model.shape[1]
    r2_adj   = 1 - (1 - r2) * (n_run - 1) / max(n_run - n_params, 1)
    rmse     = math.sqrt(ss_res / max(n_run - n_params, 1))

    def _predict(x_coded: np.ndarray) -> float:
        row = np.concatenate([[1.0], x_coded,
                              x_coded ** 2,
                              [x_coded[i] * x_coded[j]
                               for i in range(k) for j in range(i + 1, k)]])
        return float(row @ beta)

    def objective(x):
        v = _predict(x)
        if goal == "minimize":    return  v
        if goal == "maximize":    return -v
        return (v - float(target_val)) ** 2

    best_result = None
    best_obj    = float("inf")
    bounds      = [(-alpha_axial, alpha_axial)] * k
    rng         = np.random.default_rng(42)
    for _ in range(30):
        x0  = rng.uniform(-1, 1, k)
        res = minimize(objective, x0, method="L-BFGS-B", bounds=bounds)
        if res.fun < best_obj:
            best_obj    = res.fun
            best_result = res

    optimal_coded = best_result.x.tolist() if best_result else [0.0] * k
    optimal_actual: dict = {}
    for i, nm in enumerate(factor_names):
        levels = factor_levels.get(nm, [-1.0, 1.0])
        lo, hi = float(levels[0]), float(levels[1])
        optimal_actual[nm] = round((lo + hi) / 2 + optimal_coded[i] * (hi - lo) / 2, 4)
    optimal_response = round(_predict(np.array(optimal_coded)), 4)

    term_names = (["Intercept"] + factor_names +
                  [f"{nm}²" for nm in factor_names] +
                  [f"{factor_names[i]}×{factor_names[j]}"
                   for i in range(k) for j in range(i + 1, k)])

    return jd({
        "success": True,
        "model": {
            "r_squared":     round(r2,    4),
            "r_squared_adj": round(r2_adj,4),
            "rmse":          round(rmse,  4),
            "n_runs":        n_run,
            "n_params":      n_params,
            "terms": [{"name": nm, "coeff": round(float(b), 4)}
                      for nm, b in zip(term_names, beta)],
        },
        "goal":             goal,
        "optimal_coded":    [round(float(c), 4) for c in optimal_coded],
        "optimal_settings": optimal_actual,
        "predicted_optimum": optimal_response,
        "y_actual":         [round(float(v), 4) for v in y],
        "y_predicted":      [round(float(v), 4) for v in y_pred],
    })
