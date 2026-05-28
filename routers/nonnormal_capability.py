"""
StatMind N6 — Non-Normal Capability (ISO 22514-2)
Percentile-based Cpk for Weibull, lognormal, exponential.
When Box-Cox fails, this is the correct method.
"""
import numpy as np
from scipy import stats
from scipy.optimize import minimize
from dataclasses import dataclass
from typing import Optional
import warnings; warnings.filterwarnings("ignore")

@dataclass
class NonNormalCapResult:
    column: str
    n: int
    distribution_fit: str     # "weibull", "lognormal", "exponential", "gamma"
    dist_params: dict
    fit_aic: float
    fit_bic: float
    # Percentile-based capability (ISO 22514-2)
    p0135: float              # 0.135th percentile (lower natural tolerance)
    p99865: float             # 99.865th percentile (upper natural tolerance)
    usl: Optional[float]
    lsl: Optional[float]
    # Non-normal capability indices
    cpu_hat: Optional[float]  # (USL - p99.865) / (USL - p50) * Cp_factor
    cpl_hat: Optional[float]
    cpk_hat: Optional[float]  # min(cpu_hat, cpl_hat)
    ppm_lower: Optional[float]
    ppm_upper: Optional[float]
    ppm_total: Optional[float]
    # Comparison vs normal
    cpk_normal: Optional[float]
    difference_note: str
    # Chart data
    chart_data: dict
    conclusion: str

def _fit_distributions(data):
    """Fit multiple distributions, return best by AIC."""
    fits = {}
    n = len(data)
    for name, dist in [('lognormal', stats.lognorm), ('weibull_min', stats.weibull_min),
                        ('gamma', stats.gamma), ('expon', stats.expon)]:
        try:
            params = dist.fit(data, floc=0)
            loglik = np.sum(dist.logpdf(data, *params))
            k = len(params)
            aic = 2*k - 2*loglik
            bic = k*np.log(n) - 2*loglik
            fits[name] = {'params': params, 'dist': dist, 'aic': aic, 'bic': bic, 'loglik': loglik}
        except Exception:
            pass
    if not fits:
        return 'normal', None, None, 1e9, 1e9
    best = min(fits, key=lambda x: fits[x]['aic'])
    f = fits[best]
    return best, f['dist'], f['params'], f['aic'], f['bic']

def nonnormal_capability(
    data: np.ndarray, column: str = "Measurement",
    usl: float = None, lsl: float = None,
) -> NonNormalCapResult:
    data = data[~np.isnan(data)].astype(float)
    n = len(data)
    if n < 20: raise ValueError("Need ≥ 20 data points for non-normal capability.")

    dist_name, dist, params, aic, bic = _fit_distributions(data[data > 0] if np.all(data >= 0) else data)

    if dist and params:
        p0135 = float(dist.ppf(0.00135, *params))
        p99865 = float(dist.ppf(0.99865, *params))
        p50 = float(dist.ppf(0.50, *params))
    else:
        p0135 = float(np.percentile(data, 0.135))
        p99865 = float(np.percentile(data, 99.865))
        p50 = float(np.median(data))

    # ISO 22514-2 percentile-based indices
    cpu_hat = cpl_hat = cpk_hat = None
    ppm_l = ppm_u = ppm_t = None

    if usl is not None and dist and params:
        cdf_usl = float(dist.cdf(usl, *params))
        ppm_u = round((1 - cdf_usl) * 1e6, 1)
        cpu_hat = round((usl - p50) / (p99865 - p50) if (p99865 - p50) > 0 else 0, 4)
    if lsl is not None and dist and params:
        cdf_lsl = float(dist.cdf(lsl, *params))
        ppm_l = round(cdf_lsl * 1e6, 1)
        cpl_hat = round((p50 - lsl) / (p50 - p0135) if (p50 - p0135) > 0 else 0, 4)
    if cpu_hat and cpl_hat: cpk_hat = round(min(cpu_hat, cpl_hat), 4)
    elif cpu_hat: cpk_hat = cpu_hat
    elif cpl_hat: cpk_hat = cpl_hat
    if ppm_l or ppm_u: ppm_t = round((ppm_l or 0) + (ppm_u or 0), 1)

    # Normal Cpk for comparison
    mean, std = float(np.mean(data)), float(np.std(data, ddof=1))
    cpk_normal = None
    if usl and lsl and std > 0:
        cpk_normal = round(min((usl-mean)/(3*std), (mean-lsl)/(3*std)), 4)

    diff_note = ""
    if cpk_hat and cpk_normal:
        delta = abs(cpk_hat - cpk_normal)
        if delta > 0.1:
            diff_note = f"Significant difference: Normal Cpk={cpk_normal} vs Non-Normal Cpk={cpk_hat}. Use non-normal method for this data."
        else:
            diff_note = f"Normal and non-normal Cpk agree closely (Δ={delta:.3f}). Either method acceptable."

    # Chart data
    x_min = max(data.min() * 0.9, data.min() - 3*std)
    x_max = data.max() * 1.1
    x = np.linspace(x_min, x_max, 200)
    fitted_pdf = dist.pdf(x, *params).tolist() if dist and params else []
    counts, edges = np.histogram(data, bins=min(20, n))

    chart_data = {
        "histogram": {"bin_centers": [float((edges[i]+edges[i+1])/2) for i in range(len(edges)-1)],
                      "counts": counts.tolist(), "bin_width": float(edges[1]-edges[0])},
        "fitted_x": [float(v) for v in x],
        "fitted_pdf": [float(v) for v in fitted_pdf],
        "p0135": p0135, "p99865": p99865, "p50": float(p50),
        "usl": usl, "lsl": lsl, "mean": mean,
    }

    conclusion = (
        f"Best-fit distribution: {dist_name} (AIC={aic:.1f}). "
        f"Natural tolerance: [{p0135:.4f}, {p99865:.4f}]. "
        + (f"Non-normal Cpk = {cpk_hat:.3f}. " if cpk_hat else "")
        + (f"Expected PPM = {ppm_t:,.0f}. " if ppm_t else "")
        + diff_note
    )

    return NonNormalCapResult(
        column=column, n=n,
        distribution_fit=dist_name,
        dist_params={k: round(float(v), 6) for k, v in zip(['shape','loc','scale'][:len(params)], params)} if params else {},
        fit_aic=round(aic, 2), fit_bic=round(bic, 2),
        p0135=round(p0135, 5), p99865=round(p99865, 5),
        usl=usl, lsl=lsl,
        cpu_hat=cpu_hat, cpl_hat=cpl_hat, cpk_hat=cpk_hat,
        ppm_lower=ppm_l, ppm_upper=ppm_u, ppm_total=ppm_t,
        cpk_normal=cpk_normal,
        difference_note=diff_note,
        chart_data=chart_data,
        conclusion=conclusion,
    )
