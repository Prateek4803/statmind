"""
StatMind S3-A — Logistic Regression + Stepwise Regression (AIC/BIC)
Binary logistic regression for pass/fail prediction.
Stepwise: forward selection, backward elimination, bidirectional.
References: Hosmer & Lemeshow, Applied Logistic Regression; R stepAIC
"""
import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional
import warnings; warnings.filterwarnings("ignore")


@dataclass
class LogisticResult:
    response_column: str
    predictor_columns: list
    n: int
    n_positive: int
    n_negative: int
    # Coefficients
    intercept: float
    coefficients: dict       # {predictor: coef}
    std_errors: dict         # {predictor: se}
    z_scores: dict           # {predictor: z}
    p_values: dict           # {predictor: p}
    odds_ratios: dict        # {predictor: OR}
    ci_lower: dict           # {predictor: OR_lower}
    ci_upper: dict           # {predictor: OR_upper}
    # Model fit
    log_likelihood: float
    aic: float
    bic: float
    null_deviance: float
    residual_deviance: float
    mcfadden_r2: float       # pseudo R-squared
    accuracy: float
    auc: float               # area under ROC curve
    confusion_matrix: list   # [[TN,FP],[FN,TP]]
    # Predictions
    fitted_probabilities: list
    classification_threshold: float
    verdict: str


@dataclass
class StepwiseResult:
    response_column: str
    method: str              # 'forward'|'backward'|'both'
    criterion: str           # 'AIC'|'BIC'
    steps: list              # [{step, action, variable, criterion_value}]
    selected_predictors: list
    final_aic: float
    final_bic: float
    full_model_aic: float
    improvement: float
    final_model: Optional[LogisticResult]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))


def _fit_logistic(X: np.ndarray, y: np.ndarray, max_iter: int = 200):
    """IRLS (Iteratively Reweighted Least Squares) logistic regression fit."""
    n, p = X.shape
    beta = np.zeros(p)
    for _ in range(max_iter):
        mu = _sigmoid(X @ beta)
        W = mu * (1 - mu)
        W = np.maximum(W, 1e-10)
        z = X @ beta + (y - mu) / W
        XtW = X.T * W
        try:
            beta_new = np.linalg.solve(XtW @ X + np.eye(p)*1e-8, XtW @ z)
        except np.linalg.LinAlgError:
            break
        if np.max(np.abs(beta_new - beta)) < 1e-8:
            beta = beta_new
            break
        beta = beta_new

    mu = _sigmoid(X @ beta)
    W = np.maximum(mu * (1 - mu), 1e-10)
    XtW = X.T * W
    try:
        cov = np.linalg.inv(XtW @ X + np.eye(p)*1e-8)
        se = np.sqrt(np.diag(cov))
    except Exception:
        se = np.ones(p)

    log_lik = float(np.sum(y * np.log(np.maximum(mu, 1e-15)) +
                          (1-y) * np.log(np.maximum(1-mu, 1e-15))))
    return beta, se, log_lik, mu


def _auc_roc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    """Compute AUC using trapezoidal rule."""
    thresholds = np.sort(np.unique(y_prob))[::-1]
    tpr_list, fpr_list = [0.0], [0.0]
    pos = y_true.sum(); neg = len(y_true) - pos
    if pos == 0 or neg == 0:
        return 0.5
    for t in thresholds:
        pred = (y_prob >= t).astype(int)
        tp = ((pred == 1) & (y_true == 1)).sum()
        fp = ((pred == 1) & (y_true == 0)).sum()
        tpr_list.append(tp / pos)
        fpr_list.append(fp / neg)
    tpr_list.append(1.0); fpr_list.append(1.0)
    _trap = getattr(np, 'trapezoid', None) or getattr(np, 'trapz')
    return float(_trap(tpr_list, fpr_list))


def analyze_logistic(
    data: np.ndarray,     # shape (n, p) feature matrix
    y: np.ndarray,        # shape (n,) binary response (0/1)
    response_col: str,
    predictor_cols: list,
    threshold: float = 0.5,
) -> LogisticResult:
    """Full logistic regression with model fit statistics."""
    n = len(y)
    if n < 20:
        raise ValueError(f"Logistic regression requires at least 20 observations. Got {n}.")
    if len(np.unique(y)) < 2:
        raise ValueError("Response variable must have both 0 and 1 values.")

    # Add intercept
    X = np.column_stack([np.ones(n), data])
    col_names = ['intercept'] + list(predictor_cols)

    beta, se, log_lik, mu = _fit_logistic(X, y)

    # Null model log-likelihood
    p_null = y.mean()
    null_ll = float(n * (p_null * np.log(max(p_null,1e-15)) +
                        (1-p_null) * np.log(max(1-p_null,1e-15))))

    k = len(beta)
    aic = -2 * log_lik + 2 * k
    bic = -2 * log_lik + k * np.log(n)
    mcfadden = 1.0 - (log_lik / null_ll) if null_ll != 0 else 0.0

    z = beta / np.maximum(se, 1e-15)
    p_vals = 2 * (1 - stats.norm.cdf(np.abs(z)))
    OR = np.exp(beta)
    ci_lo = np.exp(beta - 1.96 * se)
    ci_hi = np.exp(beta + 1.96 * se)

    # Classification
    pred = (mu >= threshold).astype(int)
    acc = float((pred == y).mean())
    auc = _auc_roc(y, mu)
    tn = int(((pred == 0) & (y == 0)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tp = int(((pred == 1) & (y == 1)).sum())

    if mcfadden > 0.4:
        verdict = "Excellent fit (McFadden R² > 0.40)"
    elif mcfadden > 0.2:
        verdict = "Good fit (McFadden R² > 0.20)"
    elif mcfadden > 0.1:
        verdict = "Moderate fit"
    else:
        verdict = "Poor fit — consider adding predictors or transformation"

    return LogisticResult(
        response_column=response_col,
        predictor_columns=list(predictor_cols),
        n=n, n_positive=int(y.sum()), n_negative=int(n - y.sum()),
        intercept=round(float(beta[0]),6),
        coefficients={col_names[i+1]: round(float(beta[i+1]),6) for i in range(len(predictor_cols))},
        std_errors={col_names[i+1]: round(float(se[i+1]),6) for i in range(len(predictor_cols))},
        z_scores={col_names[i+1]: round(float(z[i+1]),4) for i in range(len(predictor_cols))},
        p_values={col_names[i+1]: round(float(p_vals[i+1]),5) for i in range(len(predictor_cols))},
        odds_ratios={col_names[i+1]: round(float(OR[i+1]),4) for i in range(len(predictor_cols))},
        ci_lower={col_names[i+1]: round(float(ci_lo[i+1]),4) for i in range(len(predictor_cols))},
        ci_upper={col_names[i+1]: round(float(ci_hi[i+1]),4) for i in range(len(predictor_cols))},
        log_likelihood=round(log_lik,4),
        aic=round(aic,4), bic=round(bic,4),
        null_deviance=round(-2*null_ll,4),
        residual_deviance=round(-2*log_lik,4),
        mcfadden_r2=round(float(mcfadden),4),
        accuracy=round(acc,4), auc=round(auc,4),
        confusion_matrix=[[tn,fp],[fn,tp]],
        fitted_probabilities=[round(float(p),6) for p in mu],
        classification_threshold=threshold,
        verdict=verdict,
    )


def _aic_logistic(X: np.ndarray, y: np.ndarray) -> float:
    beta, _, log_lik, _ = _fit_logistic(X, y)
    return -2 * log_lik + 2 * X.shape[1]


def _bic_logistic(X: np.ndarray, y: np.ndarray) -> float:
    beta, _, log_lik, _ = _fit_logistic(X, y)
    n = X.shape[0]
    return -2 * log_lik + X.shape[1] * np.log(n)


def stepwise_regression(
    data: np.ndarray,
    y: np.ndarray,
    response_col: str,
    predictor_cols: list,
    method: str = "both",      # 'forward'|'backward'|'both'
    criterion: str = "AIC",    # 'AIC'|'BIC'
) -> StepwiseResult:
    """
    Stepwise variable selection for logistic regression using AIC or BIC.
    Equivalent to R's stepAIC function.
    """
    n = len(y)
    crit_fn = _aic_logistic if criterion == "AIC" else _bic_logistic
    p_full = len(predictor_cols)

    def _crit(cols):
        if not cols:
            return float('inf')
        idx = [predictor_cols.index(c) for c in cols]
        X = np.column_stack([np.ones(n), data[:, idx]])
        return crit_fn(X, y)

    # Full model criterion
    full_crit = _crit(predictor_cols)
    steps = []

    if method == "forward":
        selected = []
        remaining = list(predictor_cols)
        current_crit = float('inf')

        while remaining:
            best_var, best_crit = None, current_crit
            for var in remaining:
                c = _crit(selected + [var])
                if c < best_crit:
                    best_crit, best_var = c, var
            if best_var is None:
                break
            selected.append(best_var)
            remaining.remove(best_var)
            current_crit = best_crit
            steps.append({'step': len(steps)+1, 'action': 'ADD', 'variable': best_var,
                         f'{criterion}': round(best_crit, 4)})

    elif method == "backward":
        selected = list(predictor_cols)
        current_crit = _crit(selected)

        while len(selected) > 1:
            best_var, best_crit = None, current_crit
            for var in selected:
                remaining = [v for v in selected if v != var]
                c = _crit(remaining)
                if c < best_crit:
                    best_crit, best_var = c, var
            if best_var is None:
                break
            selected.remove(best_var)
            current_crit = best_crit
            steps.append({'step': len(steps)+1, 'action': 'REMOVE', 'variable': best_var,
                         f'{criterion}': round(best_crit, 4)})

    else:  # both
        selected = []
        remaining = list(predictor_cols)
        current_crit = float('inf')

        for _ in range(2 * p_full):
            # Try adding
            best_add, best_add_crit = None, current_crit
            for var in remaining:
                c = _crit(selected + [var])
                if c < best_add_crit:
                    best_add_crit, best_add = c, var

            # Try removing
            best_rem, best_rem_crit = None, current_crit
            for var in selected:
                c = _crit([v for v in selected if v != var])
                if c < best_rem_crit:
                    best_rem_crit, best_rem = c, var

            if best_add is None and best_rem is None:
                break
            if best_add_crit <= best_rem_crit and best_add is not None:
                selected.append(best_add)
                remaining.remove(best_add)
                current_crit = best_add_crit
                steps.append({'step': len(steps)+1, 'action': 'ADD', 'variable': best_add,
                             f'{criterion}': round(best_add_crit,4)})
            elif best_rem is not None:
                selected.remove(best_rem)
                remaining.append(best_rem)
                current_crit = best_rem_crit
                steps.append({'step': len(steps)+1, 'action': 'REMOVE', 'variable': best_rem,
                             f'{criterion}': round(best_rem_crit,4)})

    final_crit = _crit(selected)
    final_bic = _bic_logistic(
        np.column_stack([np.ones(n), data[:, [predictor_cols.index(c) for c in selected]]]), y
    ) if selected else float('inf')

    final_model = None
    if selected:
        idx = [predictor_cols.index(c) for c in selected]
        final_model = analyze_logistic(data[:, idx], y, response_col, selected)

    return StepwiseResult(
        response_column=response_col, method=method, criterion=criterion,
        steps=steps, selected_predictors=selected,
        final_aic=round(final_crit if criterion=="AIC" else _aic_logistic(
            np.column_stack([np.ones(n), data[:,[predictor_cols.index(c) for c in selected]]]),y
        ) if selected else float('inf'), 4),
        final_bic=round(final_bic, 4),
        full_model_aic=round(full_crit, 4),
        improvement=round(full_crit - final_crit, 4),
        final_model=final_model,
    )
