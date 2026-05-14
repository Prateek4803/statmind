"""
StatMind E1 — Chart generator for all hypothesis tests
Returns base64-encoded PNG strings
"""
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import stats
import io, base64

# ── Palette ─────────────────────────────────
BG     = '#0f172a'
PANEL  = '#1e293b'
BORDER = '#334155'
TEAL   = '#0d9488'
PURPLE = '#8b5cf6'
BLUE   = '#3b82f6'
AMBER  = '#f59e0b'
GREEN  = '#10b981'
RED    = '#ef4444'
GRAY   = '#94a3b8'
WHITE  = '#e2e8f0'
GROUP_COLORS = [TEAL, PURPLE, BLUE, AMBER, GREEN, RED, '#f97316', '#ec4899']

def _b64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=130, bbox_inches='tight',
                facecolor=BG, edgecolor='none')
    buf.seek(0); enc = base64.b64encode(buf.read()).decode()
    plt.close(fig); return enc

def _ax(ax, title=''):
    ax.set_facecolor(PANEL)
    ax.tick_params(colors=GRAY, labelsize=8)
    ax.xaxis.label.set_color(GRAY); ax.yaxis.label.set_color(GRAY)
    for sp in ax.spines.values(): sp.set_color(BORDER)
    if title: ax.set_title(title, color=WHITE, fontsize=9, pad=6, fontweight='bold')

def _sig_label(sig, p):
    col = RED if sig else GREEN
    txt = f"p = {p:.4f}  →  {'SIGNIFICANT ✓' if sig else 'NOT SIGNIFICANT'}"
    return txt, col

def _boxplot_pairs(ax, datasets, labels, colors):
    bp = ax.boxplot(datasets, patch_artist=True, widths=0.45,
                    medianprops=dict(color='white', linewidth=2),
                    whiskerprops=dict(color=GRAY, linewidth=1.2),
                    capprops=dict(color=GRAY, linewidth=1.2),
                    flierprops=dict(marker='o', markerfacecolor=AMBER,
                                    markeredgecolor='none', markersize=4))
    for patch, c in zip(bp['boxes'], colors):
        patch.set_facecolor(c + 'bb')
    ax.set_xticklabels(labels, color=WHITE)


# ─────────────────────────────────────────────
def chart_one_sample_t(data, result):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), facecolor=BG)
    fig.subplots_adjust(wspace=0.35)
    target = result['target']; mean = result['sample_mean']

    ax = axes[0]; _ax(ax, 'Sample Distribution vs Target')
    ax.hist(data, bins=min(20, max(5, len(data)//3)), color=TEAL, alpha=0.65, density=True, label='Data')
    if len(data) > 4:
        kde = stats.gaussian_kde(data)
        x = np.linspace(min(data)-2*np.std(data), max(data)+2*np.std(data), 300)
        ax.plot(x, kde(x), color=TEAL, lw=2)
    ax.axvline(target, color=RED,   lw=2, ls='--', label=f'Target={target}')
    ax.axvline(mean,   color=GREEN, lw=2, ls='-',  label=f'Mean={mean:.3f}')
    ax.legend(facecolor=PANEL, labelcolor=WHITE, fontsize=8, framealpha=0.8)

    ax = axes[1]; _ax(ax, '95% CI for Sample Mean')
    ci = result['ci_mean']; c = RED if result['significant'] else GREEN
    ax.barh(0, mean, height=0.28, color=c, alpha=0.75, zorder=3)
    ax.errorbar(mean, 0, xerr=[[mean-ci[0]], [ci[1]-mean]],
                fmt='none', color=WHITE, capsize=9, capthick=2, elinewidth=2, zorder=4)
    ax.axvline(target, color=RED, ls='--', lw=2, label=f'Target={target}')
    ax.set_yticks([]); ax.set_xlabel('Value', color=GRAY)
    ax.legend(facecolor=PANEL, labelcolor=WHITE, fontsize=8, framealpha=0.8)
    txt, col = _sig_label(result['significant'], result['p_value'])
    ax.text(0.5, 0.92, txt, transform=ax.transAxes, ha='center',
            fontsize=9, color=col, fontweight='bold')
    return _b64(fig)


def chart_two_sample_t(data1, data2, result):
    l1 = result.get('label1','Group 1'); l2 = result.get('label2','Group 2')
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), facecolor=BG)
    fig.subplots_adjust(wspace=0.38)

    ax = axes[0]; _ax(ax, 'Distributions')
    _boxplot_pairs(ax, [data1, data2], [l1, l2], [TEAL, PURPLE])
    ax.axhline(result['mean1'], color=TEAL,   ls=':', lw=1.2, alpha=0.7)
    ax.axhline(result['mean2'], color=PURPLE, ls=':', lw=1.2, alpha=0.7)

    ax = axes[1]; _ax(ax, 'Overlapping Histograms')
    bins = min(18, max(6, (len(data1)+len(data2))//5))
    ax.hist(data1, bins=bins, alpha=0.5, color=TEAL,   label=l1, density=True)
    ax.hist(data2, bins=bins, alpha=0.5, color=PURPLE, label=l2, density=True)
    for d, c in [(data1,TEAL),(data2,PURPLE)]:
        if len(d) > 4:
            kde = stats.gaussian_kde(d)
            xr = np.linspace(min(d)-abs(np.std(d)), max(d)+abs(np.std(d)), 250)
            ax.plot(xr, kde(xr), color=c, lw=2)
    ax.axvline(result['mean1'], color=TEAL,   ls='--', lw=1.5, alpha=0.85)
    ax.axvline(result['mean2'], color=PURPLE, ls='--', lw=1.5, alpha=0.85)
    ax.legend(facecolor=PANEL, labelcolor=WHITE, fontsize=8, framealpha=0.8)

    ax = axes[2]; _ax(ax, '95% CI  for  Mean Difference')
    diff = result['diff']; ci = result['ci_diff']
    c = RED if result['significant'] else GREEN
    ax.barh(0, diff, height=0.28, color=c, alpha=0.75, zorder=3)
    ax.errorbar(diff, 0, xerr=[[diff-ci[0]],[ci[1]-diff]],
                fmt='none', color=WHITE, capsize=9, capthick=2, elinewidth=2, zorder=4)
    ax.axvline(0, color=GRAY, ls='--', lw=1.5)
    ax.set_yticks([]); ax.set_xlabel(f'{l1} − {l2}', color=GRAY)
    txt, col = _sig_label(result['significant'], result['p_value'])
    ax.text(0.5, 0.92, txt, transform=ax.transAxes, ha='center',
            fontsize=9, color=col, fontweight='bold')
    return _b64(fig)


def chart_paired_t(data1, data2, result):
    l1 = result.get('label1','Before'); l2 = result.get('label2','After')
    diffs = np.asarray(result['diffs'])
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), facecolor=BG)
    fig.subplots_adjust(wspace=0.38)

    ax = axes[0]; _ax(ax, 'Before–After Profile')
    for i,(v1,v2) in enumerate(zip(data1,data2)):
        col = GREEN if v2 > v1 else RED
        ax.plot([0,1],[v1,v2], color=col, alpha=0.35, lw=1)
    ax.plot([0,1],[np.mean(data1),np.mean(data2)], color=WHITE, lw=2.5, zorder=5, label='Mean')
    ax.set_xticks([0,1]); ax.set_xticklabels([l1,l2], color=WHITE)
    ax.legend(facecolor=PANEL, labelcolor=WHITE, fontsize=8, framealpha=0.8)

    ax = axes[1]; _ax(ax, 'Distribution of Differences')
    ax.hist(diffs, bins=min(15, max(5,len(diffs)//3)), color=TEAL, alpha=0.65, density=True)
    if len(diffs) > 4:
        kde = stats.gaussian_kde(diffs)
        xr = np.linspace(diffs.min()-abs(diffs.std()), diffs.max()+abs(diffs.std()), 250)
        ax.plot(xr, kde(xr), color=WHITE, lw=2)
    ax.axvline(0, color=RED,   ls='--', lw=2, label='Zero')
    ax.axvline(result['mean_diff'], color=GREEN, ls='--', lw=2, label=f"Mean={result['mean_diff']:.3f}")
    ax.legend(facecolor=PANEL, labelcolor=WHITE, fontsize=8, framealpha=0.8)

    ax = axes[2]; _ax(ax, '95% CI  for  Mean Difference')
    md = result['mean_diff']; ci = result['ci_diff']
    c = RED if result['significant'] else GREEN
    ax.barh(0, md, height=0.28, color=c, alpha=0.75, zorder=3)
    ax.errorbar(md, 0, xerr=[[md-ci[0]],[ci[1]-md]],
                fmt='none', color=WHITE, capsize=9, capthick=2, elinewidth=2, zorder=4)
    ax.axvline(0, color=GRAY, ls='--', lw=1.5)
    ax.set_yticks([]); ax.set_xlabel('Mean Difference', color=GRAY)
    txt, col = _sig_label(result['significant'], result['p_value'])
    ax.text(0.5, 0.92, txt, transform=ax.transAxes, ha='center',
            fontsize=9, color=col, fontweight='bold')
    return _b64(fig)


def chart_one_way_anova(groups_data, result):
    names = result['group_names']; k = result['k_groups']
    means = result['group_means']; stds = result['group_stds']; ns = result['group_ns']
    colors = GROUP_COLORS[:k]

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5), facecolor=BG)
    fig.subplots_adjust(wspace=0.35)

    ax = axes[0]; _ax(ax, 'Group Distributions')
    _boxplot_pairs(ax, groups_data, names, colors)
    ax.axhline(result['grand_mean'], color=WHITE, ls='--', lw=1.2, alpha=0.5, label='Grand mean')
    ax.legend(facecolor=PANEL, labelcolor=WHITE, fontsize=8, framealpha=0.8)
    if k > 4: ax.set_xticklabels(names, rotation=20, ha='right', color=WHITE, fontsize=7)

    ax = axes[1]; _ax(ax, 'Group Means ± SE')
    xs = np.arange(k)
    for i,(x,m,s,n,c) in enumerate(zip(xs,means,stds,ns,colors)):
        se = s/np.sqrt(n)
        ax.errorbar(x, m, yerr=se, fmt='o', color=c, capsize=7,
                    capthick=2, markersize=9, elinewidth=2)
    ax.axhline(result['grand_mean'], color=WHITE, ls='--', lw=1.2, alpha=0.5)
    ax.set_xticks(xs)
    ax.set_xticklabels(names, color=WHITE, rotation=20 if k>4 else 0,
                       ha='right' if k>4 else 'center', fontsize=8 if k<=4 else 7)
    txt, col = _sig_label(result['significant'], result['p_value'])
    ax.text(0.5, 0.94, f"F={result['f_stat']:.3f}   {txt}", transform=ax.transAxes,
            ha='center', fontsize=9, color=col, fontweight='bold')
    return _b64(fig)


def chart_chi_square(observed, result):
    obs = np.asarray(observed)
    fig, axes = plt.subplots(1, 2 if obs.ndim==1 else 1,
                             figsize=(12 if obs.ndim==1 else 8, 4.5), facecolor=BG)
    if obs.ndim == 1:
        axes = list(axes)
        ax = axes[0]; _ax(ax, 'Observed vs Expected')
        exp = np.full(len(obs), obs.sum()/len(obs))
        x = np.arange(len(obs)); w = 0.38
        ax.bar(x-w/2, obs, width=w, color=TEAL,   alpha=0.8, label='Observed')
        ax.bar(x+w/2, exp, width=w, color=PURPLE, alpha=0.8, label='Expected')
        ax.set_xticks(x); ax.set_xticklabels([f'Cat {i+1}' for i in x], color=WHITE)
        ax.legend(facecolor=PANEL, labelcolor=WHITE, fontsize=8, framealpha=0.8)

        ax = axes[1]; _ax(ax, 'Residuals (Obs − Exp)')
        res = obs - exp
        cols = [GREEN if r>=0 else RED for r in res]
        ax.bar(x, res, color=cols, alpha=0.8)
        ax.axhline(0, color=GRAY, lw=1.2)
        ax.set_xticks(x); ax.set_xticklabels([f'Cat {i+1}' for i in x], color=WHITE)
    else:
        ax = axes; _ax(ax, 'Contingency Table (Observed Counts)')
        im = ax.imshow(obs, cmap='YlOrRd', aspect='auto')
        plt.colorbar(im, ax=ax)
        for i in range(obs.shape[0]):
            for j in range(obs.shape[1]):
                ax.text(j, i, str(obs[i,j]), ha='center', va='center',
                        fontsize=10, fontweight='bold', color='black')
        ax.tick_params(colors=WHITE)

    txt, col = _sig_label(result['significant'], result['p_value'])
    fig.text(0.5, 0.01, f"χ²={result['chi2_stat']:.3f}   {txt}",
             ha='center', fontsize=9, color=col, fontweight='bold')
    return _b64(fig)


def chart_mann_whitney(data1, data2, result):
    l1=result.get('label1','Group 1'); l2=result.get('label2','Group 2')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), facecolor=BG)
    fig.subplots_adjust(wspace=0.35)

    ax = axes[0]; _ax(ax, 'Distributions (Non-Parametric)')
    _boxplot_pairs(ax, [data1,data2], [l1,l2], [TEAL,PURPLE])
    ax.axhline(result['median1'], color=TEAL,   ls=':', lw=1.5, alpha=0.8)
    ax.axhline(result['median2'], color=PURPLE, ls=':', lw=1.5, alpha=0.8)
    for y,c,lbl in [(result['median1'],TEAL,f"Med={result['median1']:.3f}"),
                    (result['median2'],PURPLE,f"Med={result['median2']:.3f}")]:
        ax.text(0.02, y, lbl, transform=ax.get_yaxis_transform(),
                color=c, fontsize=7.5, va='bottom')

    ax = axes[1]; _ax(ax, 'Rank Distributions')
    all_d = np.concatenate([data1,data2])
    ranks = stats.rankdata(all_d)
    r1 = ranks[:len(data1)]; r2 = ranks[len(data1):]
    ax.hist(r1, bins=12, alpha=0.55, color=TEAL,   label=l1, density=True)
    ax.hist(r2, bins=12, alpha=0.55, color=PURPLE, label=l2, density=True)
    ax.legend(facecolor=PANEL, labelcolor=WHITE, fontsize=8, framealpha=0.8)
    ax.set_xlabel('Rank', color=GRAY)
    txt, col = _sig_label(result['significant'], result['p_value'])
    ax.text(0.5, 0.94, txt, transform=ax.transAxes, ha='center',
            fontsize=9, color=col, fontweight='bold')
    return _b64(fig)


def chart_kruskal_wallis(groups_data, result):
    names=result['group_names']; k=result['k_groups']
    colors=GROUP_COLORS[:k]
    fig, ax = plt.subplots(1, 1, figsize=(10, 4.5), facecolor=BG)
    _ax(ax, 'Group Distributions (Non-Parametric)')
    _boxplot_pairs(ax, groups_data, names, colors)
    for m,c in zip(result['group_medians'],colors):
        ax.axhline(m, color=c, ls=':', lw=1, alpha=0.6)
    if k > 4: ax.set_xticklabels(names, rotation=20, ha='right', fontsize=7)
    txt, col = _sig_label(result['significant'], result['p_value'])
    ax.text(0.5, 0.96, f"H={result['h_stat']:.3f}   {txt}",
            transform=ax.transAxes, ha='center', fontsize=9,
            color=col, fontweight='bold')
    return _b64(fig)
