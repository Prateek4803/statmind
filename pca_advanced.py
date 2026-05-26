"""
StatMind S3-B — Principal Component Analysis with Biplots + Scatter Matrix
Full PCA: eigendecomposition, loadings, scores, explained variance, biplots.
Scatter Matrix: pairwise correlation matrix with distribution on diagonal.
References: Jolliffe (2002) Principal Component Analysis; R prcomp/pairs
"""
import numpy as np
from scipy import stats
from dataclasses import dataclass, field
from typing import Optional
import warnings; warnings.filterwarnings("ignore")


@dataclass
class PCAResult:
    columns: list
    n: int
    n_components: int
    # Eigenvalues / variance explained
    eigenvalues: list
    explained_variance_ratio: list
    cumulative_variance: list
    # Loadings (eigenvectors) — shape (n_vars, n_components)
    loadings: list            # [[comp1_loadings], [comp2_loadings], ...]
    # Scores — shape (n_obs, n_components)
    scores: list              # first 2 PCs for biplot
    # Biplot data
    biplot_scores: list       # [{x, y, label}] — observations
    biplot_arrows: list       # [{x, y, label}] — variable loadings
    # Summary statistics
    n_components_80pct: int   # how many PCs explain >80% variance
    n_components_95pct: int   # how many PCs explain >95% variance
    kaiser_components: int    # eigenvalue > 1 (Kaiser rule)
    # Correlations with PCs
    component_correlations: dict  # {var: [corr_pc1, corr_pc2, ...]}
    verdict: str


@dataclass
class ScatterMatrixResult:
    columns: list
    n: int
    correlation_matrix: list    # [[r_ij]] — full n×n matrix
    p_value_matrix: list        # [[p_ij]]
    significant_pairs: list     # [{col1, col2, r, p, significant}]
    strongest_correlation: dict # {col1, col2, r, direction}
    # Descriptive stats per column
    column_stats: list          # [{name, mean, std, min, max, skewness}]
    verdict: str


def analyze_pca(
    data: np.ndarray,
    columns: list,
    n_components: Optional[int] = None,
    scale: bool = True,
) -> PCAResult:
    """Full PCA with standardisation, biplots, and interpretation."""
    n, p = data.shape
    if n < p + 5:
        raise ValueError(f"PCA requires n > p+5. Got n={n}, p={p}.")

    # Standardise (correlation PCA if scale=True, covariance PCA if False)
    if scale:
        mean = data.mean(axis=0)
        std  = data.std(axis=0, ddof=1)
        std  = np.where(std == 0, 1, std)
        X    = (data - mean) / std
    else:
        X = data - data.mean(axis=0)

    # SVD-based PCA (numerically more stable than eigendecomposition of X^T X)
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    eigenvalues = (S ** 2) / (n - 1)
    total_var = eigenvalues.sum()
    explained = eigenvalues / total_var
    cumulative = np.cumsum(explained)

    if n_components is None:
        n_components = min(p, n - 1)
    n_components = min(n_components, p)

    # Loadings: eigenvectors (columns of V^T transposed) = Vt rows
    loadings = Vt[:n_components]  # shape (n_components, p)
    scores = X @ Vt.T[:, :n_components]   # shape (n, n_components)

    # Scale arrows for biplot (scale by sqrt(eigenvalue))
    arrow_scale = float(np.sqrt(eigenvalues[0])) * 0.8 if len(eigenvalues) > 0 else 1.0
    biplot_arrows = []
    for j, col in enumerate(columns):
        biplot_arrows.append({
            'x': round(float(loadings[0][j]) * arrow_scale, 4),
            'y': round(float(loadings[1][j]) * arrow_scale, 4) if n_components > 1 else 0.0,
            'label': col,
            'loading_pc1': round(float(loadings[0][j]), 4),
            'loading_pc2': round(float(loadings[1][j]), 4) if n_components > 1 else 0.0,
        })

    # Biplot scores (observations — sample 100 if large)
    idx_obs = np.arange(n) if n <= 100 else np.random.default_rng(42).choice(n, 100, replace=False)
    biplot_scores = [
        {'x': round(float(scores[i, 0]), 4),
         'y': round(float(scores[i, 1]), 4) if n_components > 1 else 0.0,
         'index': int(i)}
        for i in idx_obs
    ]

    # Component–variable correlations
    comp_corr = {}
    for j, col in enumerate(columns):
        corrs = []
        for k in range(min(n_components, 5)):
            r = float(np.corrcoef(data[:, j], scores[:, k])[0, 1])
            corrs.append(round(r, 4))
        comp_corr[col] = corrs

    # Interpretation thresholds
    n80 = int(np.searchsorted(cumulative, 0.80)) + 1
    n95 = int(np.searchsorted(cumulative, 0.95)) + 1
    kaiser = int((eigenvalues > 1).sum())

    if cumulative[0] > 0.60:
        verdict = f"PC1 explains {explained[0]*100:.1f}% — strong dominant dimension."
    elif n80 <= 3:
        verdict = f"First {n80} PCs explain 80% of variance — moderate dimensionality."
    else:
        verdict = f"High dimensionality — {n_components} components needed for 95% variance."

    return PCAResult(
        columns=list(columns), n=n, n_components=n_components,
        eigenvalues=[round(float(e), 6) for e in eigenvalues[:n_components]],
        explained_variance_ratio=[round(float(e), 6) for e in explained[:n_components]],
        cumulative_variance=[round(float(c), 6) for c in cumulative[:n_components]],
        loadings=[[round(float(loadings[k][j]), 4) for j in range(p)] for k in range(n_components)],
        scores=[[round(float(scores[i, k]), 4) for k in range(min(n_components, 3))] for i in range(min(n, 200))],
        biplot_scores=biplot_scores,
        biplot_arrows=biplot_arrows,
        n_components_80pct=min(n80, n_components),
        n_components_95pct=min(n95, n_components),
        kaiser_components=kaiser,
        component_correlations=comp_corr,
        verdict=verdict,
    )


def scatter_matrix(data: np.ndarray, columns: list) -> ScatterMatrixResult:
    """Pairwise correlation matrix with significance tests."""
    n, p = data.shape
    corr_mat = []
    p_mat = []
    sig_pairs = []

    for i in range(p):
        row_r, row_p = [], []
        for j in range(p):
            if i == j:
                row_r.append(1.0); row_p.append(0.0)
            else:
                r, pv = stats.pearsonr(data[:, i], data[:, j])
                row_r.append(round(float(r), 4))
                row_p.append(round(float(pv), 5))
                if i < j:
                    sig_pairs.append({
                        'col1': columns[i], 'col2': columns[j],
                        'r': round(float(r), 4),
                        'p': round(float(pv), 5),
                        'significant': bool(pv < 0.05),
                        'strength': 'Strong' if abs(r)>0.7 else 'Moderate' if abs(r)>0.4 else 'Weak',
                        'direction': 'Positive' if r > 0 else 'Negative',
                    })
        corr_mat.append(row_r)
        p_mat.append(row_p)

    sig_pairs.sort(key=lambda x: abs(x['r']), reverse=True)
    strongest = sig_pairs[0] if sig_pairs else {}

    col_stats = []
    for j, col in enumerate(columns):
        d = data[:, j]
        col_stats.append({
            'name': col,
            'mean': round(float(d.mean()), 6),
            'std': round(float(d.std(ddof=1)), 6),
            'min': round(float(d.min()), 6),
            'max': round(float(d.max()), 6),
            'skewness': round(float(stats.skew(d)), 4),
        })

    n_sig = sum(1 for x in sig_pairs if x['significant'])
    verdict = (
        f"{n_sig} of {len(sig_pairs)} pairs are significantly correlated (p<0.05). "
        + (f"Strongest: {strongest.get('col1','?')} vs {strongest.get('col2','?')} r={strongest.get('r','?')}" if strongest else "")
    )

    return ScatterMatrixResult(
        columns=list(columns), n=n,
        correlation_matrix=corr_mat, p_value_matrix=p_mat,
        significant_pairs=sig_pairs,
        strongest_correlation=strongest,
        column_stats=col_stats,
        verdict=verdict,
    )
