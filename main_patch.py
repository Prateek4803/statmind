
# ── Phase 2 Extensions ─────────────────────────────────────────────────────────

@app.post("/api/v1/capability/ci")
async def capability_ci(request: Request):
    """Cpk confidence interval calculation for a given Cpk and sample size."""
    b = await request.json()
    try:
        from capability import cpk_confidence_interval
        cpk = float(b["cpk"])
        n   = int(b["n"])
        confidence = float(b.get("confidence", 0.95))
        ci = cpk_confidence_interval(cpk, n, confidence)
        return jd({
            "cpk":        cpk,
            "n":          n,
            "confidence": confidence,
            "ci_lower":   ci.lower,
            "ci_upper":   ci.upper,
        })
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/outliers/analyze")
async def outliers_analyze(
    file: UploadFile = File(...),
    column: str      = Query(...),
    method: str      = Query("grubbs"),
    alpha: float     = Query(0.05),
):
    """Outlier detection using Grubbs, Rosner ESD, or Dixon Q test."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data = result.df[column].dropna().values.astype(float)
    try:
        from outliers import detect_outliers
        r = await asyncio.to_thread(detect_outliers, data, column, method, alpha)
        return jd(dataclasses.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/equivalence/analyze")
async def equivalence_analyze(request: Request):
    """TOST equivalence testing between two groups."""
    b = await request.json()
    try:
        from equivalence_test import tost_equivalence
        a     = np.array(b["group_a"], dtype=float)
        grp_b = np.array(b["group_b"], dtype=float)
        delta = float(b.get("delta", 0.074))
        alpha = float(b.get("alpha", 0.05))
        r = await asyncio.to_thread(
            tost_equivalence, a, grp_b, delta, alpha,
            b.get("name_a", "Group A"), b.get("name_b", "Group B"),
        )
        return jd(dataclasses.asdict(r))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/runchart/analyze")
async def runchart_analyze(
    file: UploadFile = File(...),
    column: str      = Query(...),
):
    """Run chart with runs-above/below-median and trend tests."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data   = result.df[column].dropna().values.astype(float)
    median = float(np.median(data))
    above  = [int(v > median) for v in data]
    runs, current = 1, above[0]
    for v in above[1:]:
        if v != current:
            runs += 1
            current = v
    return jd({
        "column":       column,
        "n":            int(len(data)),
        "median":       median,
        "values":       data.tolist(),
        "above_median": above,
        "n_runs":       runs,
        "verdict":      "Too few runs — possible trend or shift" if runs < max(1, int(len(data) * 0.3)) else "Run pattern appears random",
    })


@app.post("/api/v1/cusum/analyze")
async def cusum_analyze(
    file: UploadFile = File(...),
    column: str      = Query(...),
    k: float         = Query(0.5),
    h: float         = Query(4.0),
    target: float    = Query(None),
):
    """CUSUM chart for detecting small sustained process shifts."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    if column not in result.df.columns:
        raise HTTPException(404, f"Column '{column}' not found")
    data    = result.df[column].dropna().values.astype(float)
    mu      = float(target) if target is not None else float(np.mean(data))
    sigma   = float(np.std(data, ddof=1))
    if sigma == 0:
        raise HTTPException(400, "Standard deviation is zero — CUSUM undefined.")
    cusum_pos, cusum_neg = [0.0], [0.0]
    alarms = []
    for i, x in enumerate(data):
        zi = (x - mu) / sigma
        cp = max(0.0, cusum_pos[-1] + zi - k)
        cn = max(0.0, cusum_neg[-1] - zi - k)
        cusum_pos.append(cp)
        cusum_neg.append(cn)
        if cp > h or cn > h:
            alarms.append({"index": i, "value": float(x),
                           "cusum_pos": round(cp, 4), "cusum_neg": round(cn, 4)})
    return jd({
        "column":     column,
        "n":          int(len(data)),
        "target":     mu,
        "sigma":      round(sigma, 6),
        "k":          k,
        "h":          h,
        "cusum_pos":  cusum_pos[1:],
        "cusum_neg":  cusum_neg[1:],
        "alarms":     alarms,
        "n_alarms":   len(alarms),
        "in_control": len(alarms) == 0,
        "verdict":    "In control" if len(alarms) == 0 else f"{len(alarms)} CUSUM alarm(s) detected",
    })


@app.post("/api/v1/correlation/matrix")
async def correlation_matrix(
    file: UploadFile  = File(...),
    columns: str      = Query(...),
    method: str       = Query("pearson"),
):
    """Correlation matrix with significance p-values."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    cols = [col.strip() for col in columns.split(",") if col.strip()]
    for col in cols:
        if col not in result.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    df  = result.df[cols].dropna()
    mat, pmat = [], []
    for c1 in cols:
        row_r, row_p = [], []
        for c2 in cols:
            if c1 == c2:
                row_r.append(1.0); row_p.append(0.0)
            else:
                from scipy import stats as _stats
                if method == "spearman":
                    r, p = _stats.spearmanr(df[c1], df[c2])
                else:
                    r, p = _stats.pearsonr(df[c1], df[c2])
                row_r.append(round(float(r), 4))
                row_p.append(round(float(p), 4))
        mat.append(row_r); pmat.append(row_p)
    return jd({"columns": cols, "r_matrix": mat, "p_matrix": pmat, "method": method, "n": int(len(df))})


@app.post("/api/v1/sample-size/calculate")
async def sample_size_calculate(request: Request):
    """Sample size calculation for capability studies, hypothesis tests, and control charts."""
    b = await request.json()
    try:
        from scipy import stats as _stats
        study_type = b.get("study_type", "capability")
        if study_type == "capability":
            cpk_target = float(b.get("cpk_target", 1.33))
            confidence = float(b.get("confidence", 0.95))
            precision  = float(b.get("precision",  0.10))
            z = float(_stats.norm.ppf((1 + confidence) / 2))
            n = int(np.ceil((z / precision) ** 2 * (1 / (9 * cpk_target ** 2) + 0.5)))
            return jd({"study_type": study_type, "n": max(n, 30),
                        "cpk_target": cpk_target, "confidence": confidence, "precision": precision})
        elif study_type == "two_sample_t":
            delta  = float(b.get("delta", 1.0))
            sigma  = float(b.get("sigma", 1.0))
            alpha  = float(b.get("alpha", 0.05))
            power  = float(b.get("power", 0.80))
            z_a    = float(_stats.norm.ppf(1 - alpha / 2))
            z_b    = float(_stats.norm.ppf(power))
            n      = int(np.ceil(2 * ((z_a + z_b) * sigma / delta) ** 2))
            return jd({"study_type": study_type, "n_per_group": max(n, 2),
                        "delta": delta, "sigma": sigma, "alpha": alpha, "power": power})
        else:
            raise HTTPException(400, f"Unknown study_type: {study_type}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/hypothesis/two-way-anova")
async def two_way_anova(
    file: UploadFile   = File(...),
    response: str      = Query(...),
    factor_a: str      = Query(...),
    factor_b: str      = Query(...),
    alpha: float       = Query(0.05),
):
    """Two-way ANOVA with interaction term."""
    c = await file.read()
    _validate_upload(file, c)
    try:
        result = parse_any_file(c, file.filename)
    except Exception as e:
        raise HTTPException(400, str(e))
    for col in [response, factor_a, factor_b]:
        if col not in result.df.columns:
            raise HTTPException(404, f"Column '{col}' not found")
    try:
        import statsmodels.formula.api as smf
        df = result.df[[response, factor_a, factor_b]].dropna().copy()
        df[factor_a] = df[factor_a].astype(str)
        df[factor_b] = df[factor_b].astype(str)
        formula = f"Q('{response}') ~ C(Q('{factor_a}')) + C(Q('{factor_b}')) + C(Q('{factor_a}')):C(Q('{factor_b}'))"
        model   = smf.ols(formula, data=df).fit()
        import statsmodels.stats.anova as anova_lm
        table   = anova_lm.anova_lm(model, typ=2)
        rows = []
        for idx, row in table.iterrows():
            rows.append({
                "source":   str(idx),
                "ss":       round(float(row.get("sum_sq", 0)), 4),
                "df":       round(float(row.get("df", 0)), 1),
                "ms":       round(float(row.get("sum_sq", 0) / max(row.get("df", 1), 1)), 4),
                "F":        round(float(row.get("F", 0)), 4) if not np.isnan(row.get("F", float("nan"))) else None,
                "p_value":  round(float(row.get("PR(>F)", 1)), 4) if not np.isnan(row.get("PR(>F)", float("nan"))) else None,
                "significant": float(row.get("PR(>F)", 1)) < alpha if not np.isnan(row.get("PR(>F)", float("nan"))) else False,
            })
        return jd({"response": response, "factor_a": factor_a, "factor_b": factor_b,
                   "alpha": alpha, "anova_table": rows, "r_squared": round(float(model.rsquared), 4)})
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/rsm/design")
async def rsm_design(request: Request):
    """Generate a Central Composite Design (CCD) or Box-Behnken design matrix."""
    b = await request.json()
    try:
        factors     = b.get("factors", [])
        design_type = b.get("design_type", "ccd")
        n_factors   = len(factors)
        if n_factors < 2:
            raise HTTPException(400, "RSM requires at least 2 factors.")
        if design_type == "ccd":
            from itertools import product as _prod
            factorial_runs = list(_prod([-1, 1], repeat=n_factors))
            alpha_val      = float(n_factors ** 0.5)
            axial_runs     = []
            for i in range(n_factors):
                row_p = [0.0] * n_factors; row_p[i] =  alpha_val; axial_runs.append(row_p)
                row_n = [0.0] * n_factors; row_n[i] = -alpha_val; axial_runs.append(row_n)
            center_runs = [[0.0] * n_factors] * 4
            all_runs    = [list(r) for r in factorial_runs] + axial_runs + center_runs
        else:
            all_runs = [[0.0] * n_factors] * (n_factors * (n_factors - 1) * 2 + 1)

        design_matrix = []
        for i, run in enumerate(all_runs):
            row = {"run": i + 1}
            for j, f in enumerate(factors):
                lo   = float(f.get("low",  -1))
                hi   = float(f.get("high",  1))
                mid  = (lo + hi) / 2
                half = (hi - lo) / 2
                row[f["name"]] = round(mid + run[j] * half / max(alpha_val if design_type == "ccd" else 1, 1), 4)
            design_matrix.append(row)

        return jd({"design_type": design_type, "n_factors": n_factors,
                   "n_runs": len(design_matrix), "factors": factors,
                   "design_matrix": design_matrix})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/rsm/analyze")
async def rsm_analyze(request: Request):
    """Fit a second-order response surface model and return coefficients + contour data."""
    b = await request.json()
    try:
        runs       = b.get("runs", [])
        response   = b.get("response", "y")
        factor_names = b.get("factors", [])
        if not runs or not factor_names:
            raise HTTPException(400, "Provide 'runs' (list of dicts) and 'factors' (list of names).")
        import pandas as _pd
        df  = _pd.DataFrame(runs)
        y   = df[response].values.astype(float)
        X_df = df[factor_names]
        import statsmodels.formula.api as smf
        terms   = " + ".join([f"Q('{f}')" for f in factor_names])
        sq_terms= " + ".join([f"I(Q('{f}')**2)" for f in factor_names])
        inter   = " + ".join([f"Q('{factor_names[i]}')*Q('{factor_names[j]}')"
                              for i in range(len(factor_names))
                              for j in range(i+1, len(factor_names))])
        formula = f"Q('{response}') ~ {terms} + {sq_terms}" + (f" + {inter}" if inter else "")
        model   = smf.ols(formula, data=df).fit()
        coeffs  = {str(k): round(float(v), 6) for k, v in model.params.items()}
        return jd({
            "response":   response,
            "factors":    factor_names,
            "n_runs":     len(runs),
            "r_squared":  round(float(model.rsquared), 4),
            "r_squared_adj": round(float(model.rsquared_adj), 4),
            "coefficients": coeffs,
            "p_values":   {str(k): round(float(v), 4) for k, v in model.pvalues.items()},
            "verdict":    "Good fit (R² ≥ 0.80)" if model.rsquared >= 0.80 else "Poor fit — consider more runs or different factor ranges",
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))
