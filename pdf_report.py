"""
StatMind — Session 6: PDF Report Generator
Professional downloadable report with all charts embedded
Uses reportlab for layout, matplotlib for chart rendering
"""

import io
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime
from scipy import stats as scipy_stats

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import BalancedColumns
from reportlab.lib.colors import HexColor

# ── Design tokens — light/print-friendly theme ────────────────────────────────
BG_DARK    = HexColor('#f0f4f8')   # page background: very light grey
BG_CARD    = HexColor('#e8edf3')   # card background: light grey
BG_CARD2   = HexColor('#dde3ea')   # header row background: slightly darker
ACCENT     = HexColor('#1a56db')   # primary accent: deep blue
ACCENT2    = HexColor('#5521b5')   # secondary accent: deep purple
GREEN      = HexColor('#057a55')   # green: dark enough to read on white
AMBER      = HexColor('#b45309')   # amber: dark enough to read on white
RED        = HexColor('#c81e1e')   # red: dark enough to read on white
PURPLE     = HexColor('#6c2bd9')   # purple: readable
TEXT       = HexColor('#111827')   # body text: near-black
TEXT2      = HexColor('#374151')   # secondary text: dark grey
TEXT3      = HexColor('#6b7280')   # tertiary text: medium grey
WHITE      = colors.white
BLACK      = colors.black

PAGE_W, PAGE_H = A4
MARGIN = 18*mm

# ── Matplotlib style ──────────────────────────────────────────────────────────
CHART_STYLE = {
    'figure.facecolor': '#f8fafc',
    'axes.facecolor':   '#ffffff',
    'axes.edgecolor':   '#9ca3af',
    'axes.labelcolor':  '#374151',
    'xtick.color':      '#374151',
    'ytick.color':      '#374151',
    'grid.color':       '#e5e7eb',
    'grid.linestyle':   '--',
    'grid.alpha':       0.6,
    'text.color':       '#111827',
    'font.family':      'sans-serif',
    'font.size':        9,
}

def apply_chart_style():
    plt.rcParams.update(CHART_STYLE)

# ── Chart generators ──────────────────────────────────────────────────────────

def chart_to_image(fig, dpi=150) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=dpi, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf


def make_normality_charts(norm_result: dict, width_pt: float) -> list:
    """Returns list of (Image, caption) for normality section."""
    apply_chart_style()
    hd = norm_result.get('histogram_data', {})
    pd = norm_result.get('probability_plot_data', {})
    images = []

    # Histogram
    if hd:
        fig, ax = plt.subplots(figsize=(5, 3), facecolor='#141720')
        ax.set_facecolor('#1c2030')
        bc = hd.get('bin_centers', [])
        counts = hd.get('counts', [])
        bw = hd.get('bin_width', 1)
        cx = hd.get('curve_x', [])
        cy = hd.get('curve_y', [])
        if bc:
            ax.bar(bc, counts, width=bw*0.9, color='#4f7cff', alpha=0.6, edgecolor='#6b8aff')
        if cx:
            ax.plot(cx, cy, color='#2dd4a0', linewidth=2, label='Normal fit')
        mu = hd.get('mean', 0)
        ax.axvline(mu, color='#f5a623', linestyle='--', linewidth=1.2, label=f'Mean={mu:.4f}')
        ax.set_xlabel('Value'); ax.set_ylabel('Count')
        ax.legend(fontsize=7, facecolor='#f8fafc', edgecolor='#9ca3af', labelcolor='#374151')
        ax.grid(True, alpha=0.4)
        fig.tight_layout()
        buf = chart_to_image(fig)
        img = Image(buf, width=width_pt*0.48, height=width_pt*0.48*0.6)
        images.append((img, 'Histogram with Normal Curve Overlay'))

    # Normal probability plot
    if pd:
        fig, ax = plt.subplots(figsize=(5, 3), facecolor='#141720')
        ax.set_facecolor('#1c2030')
        tq = pd.get('theoretical_quantiles', [])
        sv = pd.get('sample_values', [])
        fl = pd.get('fit_line_x', [])
        fy = pd.get('fit_line_y', [])
        r2 = pd.get('r_squared', 0)
        if tq:
            ax.scatter(tq, sv, color='#4f7cff', s=18, alpha=0.75, zorder=3)
        if fl:
            ax.plot(fl, fy, color='#f2525a', linewidth=1.5, linestyle='--', label=f'R²={r2:.5f}')
        ax.set_xlabel('Theoretical Quantiles'); ax.set_ylabel('Sample Values')
        ax.legend(fontsize=7, facecolor='#f8fafc', edgecolor='#9ca3af', labelcolor='#374151')
        ax.grid(True, alpha=0.4)
        fig.tight_layout()
        buf = chart_to_image(fig)
        img = Image(buf, width=width_pt*0.48, height=width_pt*0.48*0.6)
        images.append((img, f'Normal Probability Plot (R²={r2:.5f})'))

    return images


def make_capability_chart(cap_result: dict, width_pt: float) -> Image:
    apply_chart_style()
    hd = cap_result.get('histogram_data', {})
    fig, ax = plt.subplots(figsize=(8, 3.5), facecolor='#141720')
    ax.set_facecolor('#1c2030')

    bc = hd.get('bin_centers', [])
    counts = hd.get('counts', [])
    bw = hd.get('bin_width', 1)
    cx = hd.get('curve_x', [])
    cw = hd.get('curve_within', [])
    co = hd.get('curve_overall', [])
    usl = hd.get('usl', None)
    lsl = hd.get('lsl', None)
    mean = hd.get('mean', 0)

    if bc:
        ax.bar(bc, counts, width=bw*0.9, color='#4f7cff', alpha=0.55, edgecolor='#6b8aff')
    if cx:
        ax.plot(cx, cw, color='#2dd4a0', linewidth=2, label='Within')
        ax.plot(cx, co, color='#b47aff', linewidth=1.5, linestyle='--', label='Overall')
    if lsl is not None:
        ax.axvline(lsl, color='#f2525a', linewidth=1.5, linestyle='--', label=f'LSL={lsl}')
    if usl is not None:
        ax.axvline(usl, color='#f2525a', linewidth=1.5, linestyle='-.', label=f'USL={usl}')
    ax.axvline(mean, color='#f5a623', linewidth=1.2, label=f'Mean={mean:.4f}')
    ax.set_xlabel('Value'); ax.set_ylabel('Count')
    ax.legend(fontsize=7, facecolor='#f8fafc', edgecolor='#9ca3af', labelcolor='#374151', ncol=3)
    ax.grid(True, alpha=0.4)
    fig.tight_layout()
    buf = chart_to_image(fig)
    return Image(buf, width=width_pt, height=width_pt*0.42)


def make_spc_chart(spc_result: dict, width_pt: float) -> list:
    apply_chart_style()
    images = []

    pv = spc_result.get('primary_values', [])
    sv = spc_result.get('secondary_values', [])
    ucl_p = spc_result.get('primary_ucl', 0)
    cl_p  = spc_result.get('primary_cl', 0)
    lcl_p = spc_result.get('primary_lcl', 0)
    ucl_s = spc_result.get('secondary_ucl', 0)
    cl_s  = spc_result.get('secondary_cl', 0)
    pl    = spc_result.get('primary_label', 'Value')
    sl    = spc_result.get('secondary_label', 'Range')
    sigma = spc_result.get('process_sigma', 1)

    all_alarms = (spc_result.get('western_electric_alarms') or []) + (spc_result.get('nelson_alarms') or [])
    alarm_idx = set(a.get('index', -1) for a in all_alarms)

    xs = list(range(1, len(pv)+1))
    colors_pt = ['#f2525a' if i-1 in alarm_idx else '#4f7cff' for i in xs]

    # Primary chart
    fig, ax = plt.subplots(figsize=(9, 3.2), facecolor='#141720')
    ax.set_facecolor('#1c2030')
    ax.plot(xs, pv, color='#4f7cff', linewidth=1, alpha=0.8)
    ax.scatter(xs, pv, c=colors_pt, s=12, zorder=3)
    ax.axhline(ucl_p, color='#f2525a', linestyle='--', linewidth=1, label=f'UCL={ucl_p:.4f}')
    ax.axhline(cl_p,  color='#f5a623', linestyle='--', linewidth=1.2, label=f'CL={cl_p:.4f}')
    ax.axhline(lcl_p, color='#f2525a', linestyle='--', linewidth=1, label=f'LCL={lcl_p:.4f}')
    # Sigma zone bands
    for mult, alpha in [(1, 0.06), (2, 0.04)]:
        ax.axhspan(cl_p - mult*sigma, cl_p + mult*sigma, alpha=alpha, color='#4f7cff')
    ax.set_xlabel('Subgroup'); ax.set_ylabel(pl)
    ax.legend(fontsize=7, facecolor='#f8fafc', edgecolor='#9ca3af', labelcolor='#374151', ncol=3)
    ax.grid(True, alpha=0.35)
    fig.tight_layout()
    buf = chart_to_image(fig)
    images.append(Image(buf, width=width_pt, height=width_pt*0.35))

    # Secondary chart (MR / R / S)
    if sv:
        xs2 = list(range(1, len(sv)+1))
        fig2, ax2 = plt.subplots(figsize=(9, 2.2), facecolor='#141720')
        ax2.set_facecolor('#1c2030')
        ax2.bar(xs2, sv, color='#22d3ee', alpha=0.6, width=0.6)
        ax2.axhline(ucl_s, color='#f2525a', linestyle='--', linewidth=1, label=f'UCL={ucl_s:.4f}')
        ax2.axhline(cl_s,  color='#f5a623', linestyle='--', linewidth=1.2, label=f'CL={cl_s:.4f}')
        ax2.set_xlabel('Subgroup'); ax2.set_ylabel(sl)
        ax2.legend(fontsize=7, facecolor='#f8fafc', edgecolor='#9ca3af', labelcolor='#374151')
        ax2.grid(True, alpha=0.35)
        fig2.tight_layout()
        buf2 = chart_to_image(fig2)
        images.append(Image(buf2, width=width_pt, height=width_pt*0.24))

    return images


def make_grr_chart(grr_result: dict, width_pt: float) -> Image:
    apply_chart_style()
    sources = ['Repeatability\n(EV)', 'Reproducibility\n(AV)', 'Gauge R&R\n(GRR)', 'Part-to-Part\n(PV)']
    values = [
        grr_result.get('repeatability', {}).get('pct_study_var', 0),
        grr_result.get('reproducibility', {}).get('pct_study_var', 0),
        grr_result.get('gauge_rr', {}).get('pct_study_var', 0),
        grr_result.get('part_to_part', {}).get('pct_study_var', 0),
    ]
    bar_colors = ['#4f7cff', '#ff6b8a', '#f2525a', '#2dd4a0']

    fig, ax = plt.subplots(figsize=(7, 3), facecolor='#141720')
    ax.set_facecolor('#1c2030')
    bars = ax.bar(sources, values, color=bar_colors, alpha=0.8, width=0.5)
    ax.axhline(10, color='#2dd4a0', linestyle='--', linewidth=1, label='10% threshold')
    ax.axhline(30, color='#f2525a', linestyle='--', linewidth=1, label='30% threshold')
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f'{val:.1f}%', ha='center', va='bottom', fontsize=8, color='#111827')
    ax.set_ylabel('% Study Variation')
    ax.set_ylim(0, max(max(values)+8, 35))
    ax.legend(fontsize=7, facecolor='#f8fafc', edgecolor='#9ca3af', labelcolor='#374151')
    ax.grid(True, axis='y', alpha=0.35)
    fig.tight_layout()
    buf = chart_to_image(fig)
    return Image(buf, width=width_pt*0.7, height=width_pt*0.7*3/7)


# ── ReportLab styles ──────────────────────────────────────────────────────────

def make_styles():
    s = getSampleStyleSheet()
    styles = {
        'cover_title': ParagraphStyle('cover_title', fontName='Helvetica-Bold',
            fontSize=28, textColor=WHITE, leading=34, alignment=TA_LEFT),
        'cover_sub':   ParagraphStyle('cover_sub', fontName='Helvetica',
            fontSize=13, textColor=TEXT2, leading=18, alignment=TA_LEFT),
        'cover_meta':  ParagraphStyle('cover_meta', fontName='Helvetica',
            fontSize=10, textColor=TEXT3, leading=14, alignment=TA_LEFT),
        'section_h':   ParagraphStyle('section_h', fontName='Helvetica-Bold',
            fontSize=14, textColor=ACCENT, leading=18, spaceBefore=14, spaceAfter=6),
        'sub_h':       ParagraphStyle('sub_h', fontName='Helvetica-Bold',
            fontSize=11, textColor=WHITE, leading=14, spaceBefore=8, spaceAfter=4),
        'body':        ParagraphStyle('body', fontName='Helvetica', textColor=TEXT2,
            leading=14, fontSize=9, spaceAfter=4),
        'small':       ParagraphStyle('small', fontName='Helvetica', textColor=TEXT3,
            leading=12, fontSize=8),
        'mono':        ParagraphStyle('mono', fontName='Courier', fontSize=8,
            textColor=TEXT2, leading=12, leftIndent=8),
        'verdict_ok':  ParagraphStyle('verdict_ok', fontName='Helvetica-Bold',
            fontSize=11, textColor=GREEN, leading=14),
        'verdict_warn':ParagraphStyle('verdict_warn', fontName='Helvetica-Bold',
            fontSize=11, textColor=AMBER, leading=14),
        'verdict_bad': ParagraphStyle('verdict_bad', fontName='Helvetica-Bold',
            fontSize=11, textColor=RED, leading=14),
        'caption':     ParagraphStyle('caption', fontName='Helvetica-Oblique',
            fontSize=8, textColor=TEXT3, leading=11, alignment=TA_CENTER, spaceAfter=6),
        'toc_item':    ParagraphStyle('toc_item', fontName='Helvetica',
            fontSize=9, textColor=TEXT2, leading=14, leftIndent=12),
        'exec_body':   ParagraphStyle('exec_body', fontName='Helvetica',
            fontSize=10, textColor=TEXT, leading=16, spaceAfter=6),
    }
    return styles


def table_style_base():
    return TableStyle([
        ('BACKGROUND', (0,0), (-1,0), BG_CARD2),
        ('TEXTCOLOR',  (0,0), (-1,0), ACCENT),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,0), 8),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [BG_CARD, BG_DARK]),
        ('TEXTCOLOR',  (0,1), (-1,-1), TEXT2),
        ('FONTNAME',   (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',   (0,1), (-1,-1), 8),
        ('GRID',       (0,0), (-1,-1), 0.4, HexColor('#252a3a')),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 7),
        ('RIGHTPADDING',(0,0), (-1,-1), 7),
    ])


def verdict_color(verdict: str):
    v = (verdict or '').lower()
    if any(x in v for x in ['normal','capable','excellent','acceptable','in control']): return GREEN
    if any(x in v for x in ['likely','marginal','minor']): return AMBER
    return RED


# ── Section builders ──────────────────────────────────────────────────────────

def build_cover(styles, meta: dict) -> list:
    story = []
    # Dark banner rectangle via a Table (workaround for colored background)
    banner = Table([['']], colWidths=[PAGE_W - 2*MARGIN], rowHeights=[180])
    banner.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_CARD),
        ('ROUNDEDCORNERS', [8]),
    ]))
    story.append(banner)
    story.append(Spacer(1, -170))  # overlap

    story.append(Paragraph('StatMind', ParagraphStyle('sm', fontName='Helvetica-Bold',
        fontSize=11, textColor=ACCENT, leading=14)))
    story.append(Paragraph('Process Statistics Report', styles['cover_title']))
    story.append(Spacer(1, 6))
    story.append(Paragraph(meta.get('parameter', 'Process Parameter'), styles['cover_sub']))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"Generated: {meta.get('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M'))}  |  "
        f"Process: {meta.get('process', 'N/A')}  |  n = {meta.get('n', 'N/A')}",
        styles['cover_meta']))
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width='100%', thickness=1, color=ACCENT2))
    story.append(Spacer(1, 10))
    return story


def build_executive_summary(styles, results: dict) -> list:
    story = [Paragraph('Executive Summary', styles['section_h'])]

    lines = []
    cap = results.get('capability')
    spc = results.get('spc')
    grr = results.get('grr')
    norm = results.get('normality')
    capa = results.get('capa')

    if norm:
        v = norm.get('overall_verdict', 'N/A')
        lines.append(f"<b>Normality:</b> {v} — {norm.get('capability_hint',{}).get('recommended_approach','')}")
    if cap:
        cpk = cap.get('cpk', 0)
        v = cap.get('verdict', 'N/A')
        col = 'green' if cpk >= 1.33 else 'orange' if cpk >= 1.0 else 'red'
        lines.append(f"<b>Capability:</b> Cpk = <font color='{col}'><b>{cpk:.3f}</b></font> — {v}. "
                     f"Sigma level: {cap.get('sigma_level','N/A')}. "
                     f"PPM (within): {cap.get('ppm_within','N/A'):,.0f}" if isinstance(cap.get('ppm_within'), (int,float)) else
                     f"<b>Capability:</b> Cpk = <b>{cpk:.3f}</b> — {v}.")
    if spc:
        ta = spc.get('total_alarms', 0)
        ic = spc.get('in_control', True)
        lines.append(f"<b>SPC:</b> {spc.get('chart_type','I-MR')} chart — "
                     f"{'<font color=\"green\">In Control</font>' if ic else f'<font color=\"red\">{ta} rule violation(s)</font>'}. "
                     f"{spc.get('stability_verdict','')}")
    if grr:
        pct = grr.get('gauge_rr', {}).get('pct_study_var', 0)
        col = 'green' if pct < 10 else 'orange' if pct < 30 else 'red'
        lines.append(f"<b>GRR:</b> %GRR = <font color='{col}'><b>{pct:.1f}%</b></font> — {grr.get('verdict','N/A')}. ndc = {grr.get('ndc','N/A')}")
    if capa:
        fp = capa.get('fault_pattern', '')
        sev = capa.get('problem_statement', {}).get('severity', '')
        disp = capa.get('disposition', {}).get('recommendation', '')
        if fp:
            col = 'red' if sev == 'Critical' else 'orange' if sev == 'Major' else 'green'
            lines.append(f"<b>CAPA:</b> <font color='{col}'>{sev}</font> — {fp}. Disposition: <b>{disp}</b>")

    for line in lines:
        story.append(Paragraph(line, styles['exec_body']))
        story.append(Spacer(1, 3))

    story.append(Spacer(1, 10))
    return story


def build_normality_section(styles, norm: dict, width_pt: float) -> list:
    if not norm: return []
    story = [Paragraph('1. Normality Analysis', styles['section_h'])]

    # Verdict
    v = norm.get('overall_verdict', 'N/A')
    vs = styles['verdict_ok'] if v == 'Normal' else styles['verdict_warn'] if 'Likely' in v else styles['verdict_bad']
    story.append(Paragraph(f"Verdict: {v} (Confidence: {norm.get('confidence','N/A')})", vs))
    story.append(Spacer(1, 4))

    # Descriptive stats table
    rows = [['Statistic', 'Value', 'Statistic', 'Value']]
    rows.append(['n', str(norm.get('n','N/A')), 'Skewness', f"{norm.get('skewness',0):.4f}"])
    rows.append(['Mean', f"{norm.get('mean',0):.5f}", 'Kurtosis', f"{norm.get('kurtosis',3):.4f}"])
    rows.append(['Std Dev', f"{norm.get('std',0):.5f}", 'Min', f"{norm.get('min_val',0):.5f}"])
    t = Table(rows, colWidths=[(width_pt/4)]*4)
    t.setStyle(table_style_base())
    story.append(t)
    story.append(Spacer(1, 8))

    # Test results table
    sw = norm.get('shapiro_wilk', {})
    ad = norm.get('anderson_darling', {})
    rj = norm.get('ryan_joiner', {})
    rows2 = [['Test', 'Statistic', 'p-value', 'Result']]
    for name, d, stat_key in [('Shapiro-Wilk', sw, 'statistic'),
                               ('Anderson-Darling', ad, 'statistic'),
                               ('Ryan-Joiner', rj, 'statistic')]:
        reject = d.get('reject_null', False)
        result_txt = 'NOT Normal' if reject else 'Normal'
        col_hex = '#f2525a' if reject else '#2dd4a0'
        rows2.append([name, f"{d.get(stat_key,0):.5f}", f"{d.get('p_value',0):.5f}",
                      Paragraph(f"<font color='{col_hex}'><b>{result_txt}</b></font>",
                                ParagraphStyle('r', fontName='Helvetica-Bold', fontSize=8, textColor=TEXT2))])
    t2 = Table(rows2, colWidths=[width_pt*0.35, width_pt*0.2, width_pt*0.2, width_pt*0.25])
    t2.setStyle(table_style_base())
    story.append(t2)
    story.append(Spacer(1, 10))

    # Charts
    chart_imgs = make_normality_charts(norm, width_pt)
    if chart_imgs:
        img_row = [ci[0] for ci in chart_imgs]
        cap_row = [Paragraph(ci[1], styles['caption']) for ci in chart_imgs]
        if len(img_row) == 2:
            t3 = Table([img_row, cap_row], colWidths=[width_pt*0.49, width_pt*0.49])
            t3.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2)]))
            story.append(t3)

    # Downstream guidance
    notes = norm.get('capability_hint', {}).get('downstream_notes', [])
    if notes:
        story.append(Spacer(1, 6))
        story.append(Paragraph('Downstream Analysis Guidance', styles['sub_h']))
        for note in notes:
            story.append(Paragraph(f'• {note}', styles['body']))

    story.append(Spacer(1, 6))
    return story


def build_capability_section(styles, cap: dict, width_pt: float) -> list:
    if not cap: return []
    story = [Paragraph('2. Process Capability', styles['section_h'])]

    v = cap.get('verdict', 'N/A')
    vs = styles['verdict_ok'] if v in ('Capable','Excellent') else styles['verdict_warn'] if v == 'Marginal' else styles['verdict_bad']
    story.append(Paragraph(f"Verdict: {v} — Sigma Level: {cap.get('sigma_level','N/A')}σ", vs))
    story.append(Paragraph(cap.get('verdict_detail', ''), styles['body']))
    story.append(Spacer(1, 6))

    # Main indices table
    idx_rows = [['Index', 'Value', 'Index', 'Value', 'Index', 'Value']]
    def fmt_idx(v, threshold=1.33):
        if v is None: return '—'
        col = '#2dd4a0' if v >= threshold else '#f5a623' if v >= 1.0 else '#f2525a'
        return Paragraph(f"<font color='{col}'><b>{v:.4f}</b></font>",
                         ParagraphStyle('idx', fontName='Helvetica-Bold', fontSize=9, textColor=TEXT2))
    idx_rows.append([
        'Cp',   fmt_idx(cap.get('cp')),
        'Cpk',  fmt_idx(cap.get('cpk')),
        'Cpm',  fmt_idx(cap.get('cpm'), 1.0),
    ])
    idx_rows.append([
        'Pp',   fmt_idx(cap.get('pp')),
        'Ppk',  fmt_idx(cap.get('ppk')),
        'CPU/CPL', f"{cap.get('cpu',0):.4f} / {cap.get('cpl',0):.4f}",
    ])
    cw = width_pt / 6
    t = Table(idx_rows, colWidths=[cw]*6)
    t.setStyle(table_style_base())
    story.append(t)
    story.append(Spacer(1, 6))

    # Spec limits + variation table
    rows2 = [['Parameter', 'Value', 'Parameter', 'Value']]
    rows2.append(['USL', str(cap.get('usl','N/A')), 'LSL', str(cap.get('lsl','N/A'))])
    rows2.append(['Target', f"{cap.get('target',0):.4f}", 'Mean', f"{cap.get('mean',0):.5f}"])
    rows2.append([u'\u03c3 Within', f"{cap.get('std_within',0):.5f}", u'\u03c3 Overall', f"{cap.get('std_overall',0):.5f}"])
    rows2.append(['PPM Within', f"{cap.get('ppm_within',0):,.1f}", 'PPM Overall', f"{cap.get('ppm_overall',0):,.1f}"])
    t2 = Table(rows2, colWidths=[width_pt*0.28, width_pt*0.22, width_pt*0.28, width_pt*0.22])
    t2.setStyle(table_style_base())
    story.append(t2)
    story.append(Spacer(1, 8))

    # CI table
    ci90 = cap.get('cpk_ci_90', {})
    ci95 = cap.get('cpk_ci_95', {})
    ci99 = cap.get('cpk_ci_99', {})
    ci_rows = [['Confidence', 'Lower', 'Cpk', 'Upper']]
    for ci, label in [(ci90,'90%'),(ci95,'95%'),(ci99,'99%')]:
        ci_rows.append([label, f"{ci.get('lower',0):.4f}", f"{cap.get('cpk',0):.4f}", f"{ci.get('upper',0):.4f}"])
    t3 = Table(ci_rows, colWidths=[width_pt*0.2, width_pt*0.27, width_pt*0.27, width_pt*0.26])
    t3.setStyle(table_style_base())
    story.append(Paragraph('Confidence Intervals on Cpk (Bissell Method)', styles['sub_h']))
    story.append(t3)
    story.append(Spacer(1, 8))

    # Capability chart
    cap_img = make_capability_chart(cap, width_pt)
    story.append(cap_img)
    story.append(Paragraph('Capability Histogram with Spec Limits, Within and Overall Normal Curves', styles['caption']))

    # CAPA notes
    notes = cap.get('capa_notes', [])
    if notes:
        story.append(Spacer(1, 4))
        story.append(Paragraph('Process Analysis Notes', styles['sub_h']))
        for note in notes:
            story.append(Paragraph(f'• {note}', styles['body']))

    story.append(Spacer(1, 6))
    return story


def build_spc_section(styles, spc: dict, width_pt: float) -> list:
    if not spc: return []
    story = [Paragraph('3. SPC Control Charts', styles['section_h'])]

    ic = spc.get('in_control', True)
    ta = spc.get('total_alarms', 0)
    vs = styles['verdict_ok'] if ic else styles['verdict_warn'] if ta <= 2 else styles['verdict_bad']
    story.append(Paragraph(f"{spc.get('chart_type','I-MR')} Chart — {spc.get('stability_verdict','')}", vs))
    story.append(Spacer(1, 4))

    # Limits table
    lim_rows = [['Parameter', 'Value', 'Parameter', 'Value']]
    lim_rows.append(['UCL', f"{spc.get('primary_ucl',0):.5f}", 'LCL', f"{spc.get('primary_lcl',0):.5f}"])
    lim_rows.append(['Center Line', f"{spc.get('primary_cl',0):.5f}", 'Process Sigma', f"{spc.get('process_sigma',0):.5f}"])
    lim_rows.append(['n Points', str(spc.get('n_points',0)), 'Total Alarms', str(ta)])
    t = Table(lim_rows, colWidths=[width_pt*0.28, width_pt*0.22, width_pt*0.28, width_pt*0.22])
    t.setStyle(table_style_base())
    story.append(t)
    story.append(Spacer(1, 8))

    # SPC charts
    spc_imgs = make_spc_chart(spc, width_pt)
    for i, img in enumerate(spc_imgs):
        story.append(img)
        label = spc.get('primary_label','') if i==0 else spc.get('secondary_label','')
        story.append(Paragraph(f'{label} Chart — alarm points highlighted in red', styles['caption']))

    # Alarm table
    all_alarms = (spc.get('western_electric_alarms') or []) + (spc.get('nelson_alarms') or [])
    all_alarms.sort(key=lambda a: a.get('index', 0))
    if all_alarms:
        story.append(Spacer(1, 6))
        story.append(Paragraph('Rule Violations', styles['sub_h']))
        alarm_rows = [['Point', 'Rule', 'Value', 'Description']]
        for a in all_alarms[:20]:
            alarm_rows.append([
                str(a.get('index',0)+1),
                a.get('rule',''),
                f"{a.get('value',0):.4f}",
                a.get('description','')[:60],
            ])
        if len(all_alarms) > 20:
            alarm_rows.append(['...', '', '', f'+ {len(all_alarms)-20} more violations'])
        t2 = Table(alarm_rows, colWidths=[width_pt*0.1, width_pt*0.1, width_pt*0.15, width_pt*0.65])
        t2.setStyle(table_style_base())
        story.append(t2)

    # Summary
    summary = spc.get('alarm_summary', [])
    if summary:
        story.append(Spacer(1, 6))
        for s in summary:
            story.append(Paragraph(f'• {s}', styles['body']))

    story.append(Spacer(1, 6))
    return story


def build_grr_section(styles, grr: dict, width_pt: float) -> list:
    if not grr: return []
    story = [Paragraph('4. Gauge R&R (MSA)', styles['section_h'])]

    v = grr.get('verdict', 'N/A')
    vs = styles['verdict_ok'] if v == 'Acceptable' else styles['verdict_warn'] if v == 'Marginal' else styles['verdict_bad']
    story.append(Paragraph(f"Verdict: {v} — {grr.get('verdict_detail','')}", vs))
    story.append(Spacer(1, 4))

    # Study design
    rows = [['Study Design', 'Value', 'Key Metric', 'Value']]
    rows.append(['Method', grr.get('method','ANOVA'), 'ndc', str(grr.get('ndc','N/A'))])
    rows.append(['Parts', str(grr.get('n_parts','N/A')), '%GRR', f"{grr.get('gauge_rr',{}).get('pct_study_var',0):.1f}%"])
    rows.append(['Operators', str(grr.get('n_operators','N/A')), '% Tolerance', f"{grr.get('pct_tolerance','N/A')}%"])
    rows.append(['Replicates', str(grr.get('n_replicates','N/A')), 'Total Readings', str(grr.get('n_total','N/A'))])
    t = Table(rows, colWidths=[width_pt*0.28, width_pt*0.22, width_pt*0.28, width_pt*0.22])
    t.setStyle(table_style_base())
    story.append(t)
    story.append(Spacer(1, 8))

    # Variance components
    vc_rows = [['Source', 'Variance', 'Std Dev', '% Contribution', 'Study Var', '% Study Var']]
    for vc in [grr.get('repeatability',{}), grr.get('reproducibility',{}),
               grr.get('operator_by_part',{}), grr.get('gauge_rr',{}),
               grr.get('part_to_part',{}), grr.get('total_variation',{})]:
        src = vc.get('source', '')
        pct = vc.get('pct_study_var', 0)
        col = '#2dd4a0' if pct < 10 else '#f5a623' if pct < 30 else '#f2525a'
        isBold = 'GRR' in src or 'Total' in src
        fn = 'Helvetica-Bold' if isBold else 'Helvetica'
        vc_rows.append([
            Paragraph(f"<b>{src}</b>" if isBold else src,
                      ParagraphStyle('vc', fontName=fn, fontSize=8, textColor=TEXT2)),
            f"{vc.get('variance',0):.2e}",
            f"{vc.get('std_dev',0):.6f}",
            f"{vc.get('pct_contribution',0):.1f}%",
            f"{vc.get('study_var',0):.5f}",
            Paragraph(f"<font color='{col}'><b>{pct:.1f}%</b></font>",
                      ParagraphStyle('pct', fontName='Helvetica-Bold', fontSize=8, textColor=TEXT2)),
        ])
    cw = [width_pt*0.28, width_pt*0.1, width_pt*0.12, width_pt*0.15, width_pt*0.15, width_pt*0.2]
    t2 = Table(vc_rows, colWidths=cw)
    t2.setStyle(table_style_base())
    story.append(t2)
    story.append(Spacer(1, 8))

    # GRR bar chart
    grr_img = make_grr_chart(grr, width_pt)
    story.append(grr_img)
    story.append(Paragraph('GRR Component Breakdown (% Study Variation)', styles['caption']))

    # ANOVA table
    anova = grr.get('anova_table', [])
    if anova and anova[0].get('source','') != 'XbarR method — no ANOVA table':
        story.append(Spacer(1, 6))
        story.append(Paragraph('Two-Way ANOVA Table', styles['sub_h']))
        a_rows = [['Source', 'SS', 'df', 'MS', 'F', 'p-value']]
        for row in anova:
            p = row.get('p_value', 1)
            sig = p < 0.05 and row.get('f_stat', 0) > 0
            p_str = Paragraph(
                f"<font color='{'#f2525a' if sig else '#2dd4a0'}'><b>{p:.4f}</b></font>",
                ParagraphStyle('p', fontName='Helvetica-Bold', fontSize=8, textColor=TEXT2))
            a_rows.append([
                row.get('source',''), f"{row.get('ss',0):.6f}", str(row.get('df',0)),
                f"{row.get('ms',0):.6f}",
                f"{row.get('f_stat',0):.3f}" if row.get('f_stat',0) > 0 else '—',
                p_str if row.get('f_stat',0) > 0 else '—',
            ])
        t3 = Table(a_rows, colWidths=[width_pt*0.3, width_pt*0.14, width_pt*0.07, width_pt*0.14, width_pt*0.12, width_pt*0.13])
        t3.setStyle(table_style_base())
        story.append(t3)

    # Notes
    notes = grr.get('capa_notes', [])
    if notes:
        story.append(Spacer(1, 6))
        for note in notes:
            story.append(Paragraph(f'• {note}', styles['body']))

    story.append(Spacer(1, 6))
    return story


def build_capa_section(styles, capa: dict, width_pt: float) -> list:
    if not capa: return []
    story = [Paragraph('5. CAPA Report', styles['section_h'])]

    sev = capa.get('problem_statement', {}).get('severity', 'N/A')
    conf = capa.get('confidence_level', 'N/A')
    rule_id = capa.get('rule_id', '')
    vs = styles['verdict_bad'] if sev == 'Critical' else styles['verdict_warn'] if sev == 'Major' else styles['verdict_ok']
    story.append(Paragraph(
        f"Severity: {sev}  |  Confidence: {conf}  |  Rule: {rule_id}  |  Process: {capa.get('process','')}",
        vs))
    story.append(Spacer(1, 4))

    # Fault pattern box
    fp = capa.get('fault_pattern', '')
    if fp:
        fp_table = Table([[Paragraph(fp, ParagraphStyle('fp', fontName='Helvetica-Bold',
            fontSize=11, textColor=ACCENT, leading=16))]],
            colWidths=[width_pt])
        fp_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), BG_CARD2),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
        ]))
        story.append(fp_table)
        story.append(Spacer(1, 8))

    # Problem + Root Cause side by side
    ps = capa.get('problem_statement', {})
    rca = capa.get('root_cause_analysis', {})

    prob_content = [Paragraph('Problem Statement', styles['sub_h'])]
    prob_content.append(Paragraph(ps.get('description',''), styles['body']))
    evidence = ps.get('statistical_evidence', [])
    if evidence:
        prob_content.append(Spacer(1, 4))
        for e in evidence:
            prob_content.append(Paragraph(f'• {e}', styles['body']))

    rca_content = [Paragraph('Root Cause Analysis', styles['sub_h'])]
    rca_content.append(Paragraph(
        f"<b>Confidence: {rca.get('confidence','N/A')}</b>", styles['body']))
    rca_content.append(Paragraph(rca.get('primary_hypothesis',''), styles['body']))
    detail = rca.get('detail', '')
    if detail:
        rca_content.append(Spacer(1, 3))
        rca_content.append(Paragraph(detail, styles['small']))
    alts = rca.get('alternative_hypotheses', [])
    if alts:
        rca_content.append(Spacer(1, 4))
        rca_content.append(Paragraph('Alternative causes:', styles['small']))
        for a in alts:
            rca_content.append(Paragraph(f'• {a}', styles['small']))

    two_col = Table([[prob_content, rca_content]],
                    colWidths=[width_pt*0.49, width_pt*0.49])
    two_col.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 8))

    # Corrective actions
    story.append(Paragraph('Corrective Actions', styles['sub_h']))
    for i, action in enumerate(capa.get('corrective_actions', []), 1):
        p = action.get('priority', 'P3')
        p_col = '#f2525a' if p == 'P1' else '#f5a623' if p == 'P2' else '#4f7cff'
        row_data = [[
            Paragraph(f"<font color='{p_col}'><b>{p}</b></font>",
                      ParagraphStyle('pr', fontName='Helvetica-Bold', fontSize=9, textColor=TEXT2)),
            Paragraph(f"<b>{action.get('action','')}</b><br/>"
                      f"<font color='#8b92b0'>{action.get('expected_impact','')}</font>",
                      ParagraphStyle('act', fontName='Helvetica', fontSize=8, textColor=TEXT, leading=12)),
            Paragraph(f"{action.get('timeline','')}<br/><font color='#5a607a'>{action.get('owner','')}</font>",
                      ParagraphStyle('tl', fontName='Helvetica', fontSize=8, textColor=TEXT2, leading=12)),
        ]]
        row_table = Table(row_data, colWidths=[width_pt*0.08, width_pt*0.72, width_pt*0.2])
        bg = BG_CARD if i % 2 == 1 else BG_DARK
        row_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#252a3a')),
        ]))
        story.append(row_table)
    story.append(Spacer(1, 8))

    # Preventive actions
    story.append(Paragraph('Preventive Actions', styles['sub_h']))
    for i, action in enumerate(capa.get('preventive_actions', []), 1):
        sc = action.get('system_change', '')
        row_data = [[
            Paragraph(f"<font color='#b47aff'><b>{sc}</b></font>",
                      ParagraphStyle('sc', fontName='Helvetica-Bold', fontSize=8, textColor=TEXT2)),
            Paragraph(f"<b>{action.get('action','')}</b>",
                      ParagraphStyle('pa', fontName='Helvetica', fontSize=8, textColor=TEXT, leading=12)),
            Paragraph(f"{action.get('timeline','')}<br/><font color='#5a607a'>{action.get('owner','')}</font>",
                      ParagraphStyle('ptl', fontName='Helvetica', fontSize=8, textColor=TEXT2, leading=12)),
        ]]
        row_table = Table(row_data, colWidths=[width_pt*0.12, width_pt*0.68, width_pt*0.2])
        bg = BG_CARD if i % 2 == 1 else BG_DARK
        row_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), bg),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.3, HexColor('#252a3a')),
        ]))
        story.append(row_table)
    story.append(Spacer(1, 8))

    # Disposition
    disp = capa.get('disposition', {})
    rec = disp.get('recommendation', 'N/A')
    disp_col = '#f2525a' if rec in ('Hold','Scrap') else '#2dd4a0' if rec == 'Release' else '#f5a623'
    disp_table = Table([[
        Paragraph(f"Disposition: <font color='{disp_col}'><b>{rec}</b></font>",
                  ParagraphStyle('dt', fontName='Helvetica-Bold', fontSize=10, textColor=TEXT)),
        Paragraph(disp.get('rationale',''),
                  ParagraphStyle('dr', fontName='Helvetica', fontSize=8, textColor=TEXT2, leading=12)),
    ]], colWidths=[width_pt*0.28, width_pt*0.72])
    disp_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_CARD2),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(disp_table)
    if disp.get('containment'):
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"Containment: {disp['containment']}", styles['small']))

    story.append(Spacer(1, 6))
    return story


# ── Page decorators ───────────────────────────────────────────────────────────

class StatMindDocTemplate(SimpleDocTemplate):
    """Custom template with header/footer on every page."""

    def __init__(self, filename, meta, **kwargs):
        self.meta = meta
        super().__init__(filename, **kwargs)

    def handle_pageBegin(self):
        super().handle_pageBegin()

    def afterPage(self):
        canvas = self.canv
        w, h = A4
        # Page background
        canvas.saveState()
        canvas.setFillColor(WHITE)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)
        canvas.restoreState()
        # Header bar
        canvas.saveState()
        canvas.setFillColor(BG_CARD)
        canvas.rect(0, h - 14*mm, w, 14*mm, fill=1, stroke=0)
        canvas.setFillColor(ACCENT)
        canvas.setFont('Helvetica-Bold', 8)
        canvas.drawString(MARGIN, h - 9*mm, 'StatMind')
        canvas.setFillColor(TEXT3)
        canvas.setFont('Helvetica', 7)
        param = self.meta.get('parameter', '')
        canvas.drawString(MARGIN + 45, h - 9*mm, f'Process Statistics Report — {param}')
        # Page number
        canvas.setFont('Helvetica', 7)
        canvas.drawRightString(w - MARGIN, h - 9*mm, f'Page {self.page}')
        # Footer
        canvas.setFillColor(BG_CARD)
        canvas.rect(0, 0, w, 10*mm, fill=1, stroke=0)
        canvas.setFillColor(TEXT3)
        canvas.setFont('Helvetica', 7)
        canvas.drawString(MARGIN, 6*mm,
            f"Generated: {self.meta.get('generated_at','')}  |  StatMind v5.0")
        canvas.drawRightString(w - MARGIN, 6*mm,
            f"CONFIDENTIAL — Internal Process Documentation")
        canvas.restoreState()


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_report(
    output_path: str,
    normality_result=None,
    capability_result=None,
    spc_result=None,
    grr_result=None,
    capa_result=None,
    meta: dict = None,
) -> str:
    """
    Generate a full PDF report and save to output_path.
    Returns the output path.
    """
    if meta is None:
        meta = {}
    meta.setdefault('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M'))
    meta.setdefault('parameter', 'Process Parameter')
    meta.setdefault('process', 'N/A')
    if normality_result:
        meta.setdefault('n', normality_result.get('n', 'N/A'))
    elif capability_result:
        meta.setdefault('n', capability_result.get('n', 'N/A'))

    styles = make_styles()
    content_width = PAGE_W - 2*MARGIN - 2*mm  # usable width

    doc = StatMindDocTemplate(
        output_path, meta=meta,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=18*mm, bottomMargin=14*mm,
    )

    results = {
        'normality': normality_result,
        'capability': capability_result,
        'spc': spc_result,
        'grr': grr_result,
        'capa': capa_result,
    }

    story = []
    story += build_cover(styles, meta)
    story.append(Spacer(1, 12))
    story += build_executive_summary(styles, results)
    story.append(HRFlowable(width='100%', thickness=0.5, color=TEXT3))
    story.append(PageBreak())

    if normality_result:
        story += build_normality_section(styles, normality_result, content_width)
        story.append(HRFlowable(width='100%', thickness=0.5, color=TEXT3))
        story.append(Spacer(1, 6))

    if capability_result:
        story += build_capability_section(styles, capability_result, content_width)
        story.append(HRFlowable(width='100%', thickness=0.5, color=TEXT3))
        story.append(Spacer(1, 6))

    if spc_result:
        story += build_spc_section(styles, spc_result, content_width)
        story.append(HRFlowable(width='100%', thickness=0.5, color=TEXT3))
        story.append(Spacer(1, 6))

    if grr_result:
        story += build_grr_section(styles, grr_result, content_width)
        story.append(HRFlowable(width='100%', thickness=0.5, color=TEXT3))
        story.append(Spacer(1, 6))

    if capa_result:
        story += build_capa_section(styles, capa_result, content_width)

    doc.build(story)
    return output_path
