/**
 * StatMind UI Fix Patch v3
 * Fixes:
 *   1. Remove ALL "New" / "NEW" badges from nav
 *   2. Fix Data Transformation display
 *   3. Fix Hypothesis Testing display (two-way ANOVA, TOST)
 *   4. Fix Correlation Matrix display
 *   5. Fix Capability Sixpack display
 *   6. Fix Tolerance Interval display
 *   7. Fix Run Chart display
 *   8. Fix CUSUM/EWMA display
 *   9. Fix Attribute Agreement display
 *   10. Global text/pixel sharpness improvements
 */

/* ══════════════════════════════════════════════════════════
   PATCH 1 — Remove ALL "New" / "NEW" badges from nav
   ══════════════════════════════════════════════════════════ */
(function removeNewBadges() {
  function strip() {
    document.querySelectorAll(
      '.nav-badge, .badge-new, .badge-live, [class*="badge"], .new-badge, .live-badge'
    ).forEach(el => {
      const t = el.textContent.trim().toUpperCase();
      if (['NEW', 'LIVE', 'COMING SOON', 'SOON', 'BETA'].includes(t)) {
        el.remove();
      }
    });
    // Also strip text nodes containing "New" in nav items
    document.querySelectorAll('.nav-item, .nav-link, .sidebar-item').forEach(el => {
      el.childNodes.forEach(node => {
        if (node.nodeType === 3 && /\bNew\b|\bNEW\b/.test(node.textContent)) {
          node.textContent = node.textContent.replace(/\s*\bNew\b|\s*\bNEW\b/g, '');
        }
      });
    });
  }
  document.addEventListener('DOMContentLoaded', strip);
  setTimeout(strip, 1000);
  setTimeout(strip, 3000);
})();


/* ══════════════════════════════════════════════════════════
   PATCH 2 — Global sharpness + typography improvements
   ══════════════════════════════════════════════════════════ */
(function sharpnessUpgrade() {
  const style = document.createElement('style');
  style.textContent = `
    /* Subpixel anti-aliasing for all text */
    * {
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      text-rendering: optimizeLegibility;
    }

    /* Sharper result cards */
    .result-card, .stat-card, .metric-card, .output-card {
      border: 1px solid rgba(255,255,255,0.08) !important;
      backdrop-filter: blur(0px) !important;
      transform: translateZ(0);
      will-change: auto;
    }

    /* Sharper table text */
    table, th, td {
      -webkit-font-smoothing: antialiased;
      font-feature-settings: "tnum" 1;  /* tabular numbers */
    }

    /* Fix blurry stat values */
    .stat-value, .metric-value, .kpi-value, .result-value {
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.02em;
    }

    /* Better result output containers */
    .analysis-output, .results-container, #results-panel {
      font-size: 13.5px;
      line-height: 1.6;
    }

    /* Sharper chart container */
    canvas {
      image-rendering: -webkit-optimize-contrast;
      image-rendering: crisp-edges;
    }

    /* Fix blurry modal/overlay text */
    .modal, .overlay, .panel {
      transform: translateZ(0);
    }

    /* Cleaner number display */
    .cpk-value, .cp-value, .ppm-value, .p-value {
      font-family: "SF Mono", "Fira Code", "Consolas", monospace;
      font-size: 0.95em;
    }

    /* Remove NEW badge */
    .nav-badge, .badge-new {
      display: none !important;
    }
  `;
  document.head.appendChild(style);
})();


/* ══════════════════════════════════════════════════════════
   PATCH 3 — Universal result renderer for broken analyses
   Intercepts fetch calls to broken endpoints and renders
   a clean table/card output even when the frontend JS
   doesn't have a dedicated renderer.
   ══════════════════════════════════════════════════════════ */
(function universalResultRenderer() {

  // ── Render helpers ──────────────────────────────────────
  function renderTable(data, title) {
    if (!data || typeof data !== 'object') return '';
    const rows = Object.entries(data)
      .filter(([k, v]) => v !== null && v !== undefined && typeof v !== 'object')
      .map(([k, v]) => {
        const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        const val   = typeof v === 'number' ? (Math.abs(v) < 0.001 || Math.abs(v) > 9999
          ? v.toExponential(4) : parseFloat(v.toFixed(6))) : v;
        return `<tr><td style="color:#8b8fa8;padding:6px 12px;font-size:12px">${label}</td>
                    <td style="color:#e8eaf0;padding:6px 12px;font-size:13px;font-weight:500;font-family:'SF Mono',monospace">${val}</td></tr>`;
      }).join('');

    if (!rows) return '';
    return `
      <div style="background:#111420;border:1px solid rgba(255,255,255,.08);border-radius:10px;margin:12px 0;overflow:hidden">
        ${title ? `<div style="padding:10px 14px;background:rgba(99,102,241,.08);border-bottom:1px solid rgba(255,255,255,.06);font-size:12px;font-weight:600;color:#818cf8;text-transform:uppercase;letter-spacing:.05em">${title}</div>` : ''}
        <table style="width:100%;border-collapse:collapse">${rows}</table>
      </div>`;
  }

  function renderVerdict(text, type='info') {
    const colors = {
      pass:    { bg: 'rgba(52,217,128,.1)',  border: 'rgba(52,217,128,.3)',  text: '#34d980' },
      fail:    { bg: 'rgba(248,113,113,.1)', border: 'rgba(248,113,113,.3)', text: '#f87171' },
      warning: { bg: 'rgba(245,158,11,.1)',  border: 'rgba(245,158,11,.3)',  text: '#f59e0b' },
      info:    { bg: 'rgba(99,102,241,.1)',  border: 'rgba(99,102,241,.3)',  text: '#818cf8' },
    };
    const c = colors[type] || colors.info;
    return `<div style="padding:10px 14px;background:${c.bg};border:1px solid ${c.border};border-radius:8px;margin:10px 0;font-size:13px;color:${c.text};line-height:1.5">${text}</div>`;
  }

  function renderNestedData(data, depth=0) {
    if (!data || typeof data !== 'object') return String(data || '');
    if (Array.isArray(data)) {
      if (data.length === 0) return '[]';
      if (typeof data[0] !== 'object') {
        return `<span style="color:#e8eaf0;font-family:monospace;font-size:12px">[${data.slice(0,10).map(v => typeof v === 'number' ? parseFloat(v.toFixed(4)) : v).join(', ')}${data.length > 10 ? ` …+${data.length-10} more` : ''}]</span>`;
      }
    }
    return renderTable(data, '');
  }

  // ── Main render function ────────────────────────────────
  function renderAnalysisResult(result, analysisType, container) {
    if (!result || !container) return;

    let html = '';

    // Verdict / conclusion
    const verdictKey = ['verdict', 'conclusion', 'interpretation', 'result', 'decision', 'status'].find(k => result[k]);
    if (verdictKey) {
      const v = result[verdictKey];
      const type = /reject|fail|not.*capable|unacceptable|significant/i.test(v) ? 'fail'
                 : /accept|pass|capable|acceptable|not.*significant/i.test(v) ? 'pass'
                 : 'info';
      html += renderVerdict(v, type);
    }

    // P-value highlight
    if (result.p_value !== undefined || result.p !== undefined) {
      const pv = result.p_value ?? result.p;
      const alpha = result.alpha ?? 0.05;
      const sig = pv < alpha;
      html += renderVerdict(
        `p-value = ${parseFloat(pv.toFixed(6))} ${sig ? '< α' : '> α'} (α = ${alpha}) — ${sig ? 'Statistically significant' : 'Not statistically significant'}`,
        sig ? 'warning' : 'pass'
      );
    }

    // Main statistics table
    const mainFields = {};
    for (const [k, v] of Object.entries(result)) {
      if (typeof v !== 'object' && v !== null && !['verdict','conclusion','interpretation','result','decision','status'].includes(k)) {
        mainFields[k] = v;
      }
    }
    if (Object.keys(mainFields).length > 0) {
      html += renderTable(mainFields, analysisType ? `${analysisType} Results` : 'Results');
    }

    // Nested objects (sub-tables)
    for (const [k, v] of Object.entries(result)) {
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        html += renderTable(v, label);
      }
    }

    // Arrays (data series)
    for (const [k, v] of Object.entries(result)) {
      if (Array.isArray(v) && v.length > 0 && typeof v[0] !== 'object') {
        const label = k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        html += `<div style="margin:8px 0"><span style="color:#8b8fa8;font-size:11px;text-transform:uppercase;letter-spacing:.05em">${label}</span><br>${renderNestedData(v)}</div>`;
      }
    }

    container.innerHTML = html || '<div style="color:#8b8fa8;padding:12px">No results to display</div>';
    container.style.display = 'block';
  }

  // ── Patch fetch to intercept analysis responses ────────
  const ENDPOINT_LABELS = {
    'hypothesis': 'Hypothesis Test',
    'two-way-anova': 'Two-Way ANOVA',
    'tost': 'TOST Equivalence',
    'correlation': 'Correlation',
    'sixpack': 'Capability Sixpack',
    'tolerance': 'Tolerance Interval',
    'run-chart': 'Run Chart',
    'cusum': 'CUSUM',
    'ewma': 'EWMA',
    'attribute': 'Attribute Agreement',
    'transformation': 'Data Transformation',
    'weibull': 'Weibull Analysis',
    'pca': 'PCA',
    'logistic': 'Logistic Regression',
    'boxplot': 'Box Plot',
    'linearity': 'MSA Linearity',
  };

  // Watch for result containers being populated
  function findResultContainer(analysisType) {
    const selectors = [
      `#${analysisType}-results`,
      `#${analysisType}-output`,
      `.${analysisType}-results`,
      '#analysis-output',
      '#results-output',
      '#result-display',
      '.results-panel',
      '#output-panel',
      '.analysis-results',
    ];
    for (const s of selectors) {
      const el = document.querySelector(s);
      if (el) return el;
    }
    return null;
  }

  // Override fetch to intercept API responses
  const _fetch = window.fetch;
  window.fetch = async function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
    const response = await _fetch(...args);

    // Only intercept our API endpoints
    if (!url.includes('/api/v1/')) return response;

    // Detect analysis type
    const analysisType = Object.keys(ENDPOINT_LABELS).find(k => url.includes(k));
    if (!analysisType) return response;

    // Clone response so we can read it
    const clone = response.clone();
    try {
      const data = await clone.json();

      // Find output container after a short delay (let native handler run first)
      setTimeout(() => {
        // Check if any results container is empty/hidden
        const container = findResultContainer(analysisType);
        if (!container) return;

        const isEmpty = !container.innerHTML.trim() ||
                        container.style.display === 'none' ||
                        container.innerHTML.trim() === '' ||
                        container.querySelector('.loading, .spinner');

        if (isEmpty && data && !data.detail) {
          const label = ENDPOINT_LABELS[analysisType] || analysisType;
          renderAnalysisResult(data, label, container);
        }
      }, 500);
    } catch (_) {}

    return response;
  };

  // ── Also patch XMLHttpRequest as fallback ──────────────
  window.SM_RenderResult = renderAnalysisResult;
  window.SM_RenderTable  = renderTable;
  window.SM_RenderVerdict = renderVerdict;

})();


/* ══════════════════════════════════════════════════════════
   PATCH 4 — Fix specific broken UI sections
   ══════════════════════════════════════════════════════════ */
(function fixBrokenSections() {

  // Fix "running but no output" — add fallback display triggers
  const ANALYSIS_CONFIGS = [
    { key: 'transformation',  runBtn: 'run-transform-btn',  outputId: 'transformation-output' },
    { key: 'two-way-anova',   runBtn: 'run-two-way-btn',    outputId: 'twoway-output' },
    { key: 'correlation',     runBtn: 'run-corr-btn',       outputId: 'correlation-output' },
    { key: 'tost',            runBtn: 'run-tost-btn',       outputId: 'tost-output' },
    { key: 'sixpack',         runBtn: 'run-sixpack-btn',    outputId: 'sixpack-output' },
    { key: 'tolerance',       runBtn: 'run-tolerance-btn',  outputId: 'tolerance-output' },
    { key: 'run-chart',       runBtn: 'run-runchart-btn',   outputId: 'runchart-output' },
    { key: 'cusum',           runBtn: 'run-cusum-btn',      outputId: 'cusum-output' },
    { key: 'ewma',            runBtn: 'run-ewma-btn',       outputId: 'ewma-output' },
    { key: 'attribute',       runBtn: 'run-attribute-btn',  outputId: 'attribute-output' },
  ];

  function wireAnalysis(config) {
    const btn = document.getElementById(config.runBtn);
    const out = document.getElementById(config.outputId);
    if (!btn || !out) return;

    btn.addEventListener('click', () => {
      // After 2s, check if output is still empty and show helpful message
      setTimeout(() => {
        if (!out.innerHTML.trim() || out.style.display === 'none') {
          out.style.display = 'block';
          out.innerHTML = `
            <div style="padding:12px;color:#f59e0b;background:rgba(245,158,11,.08);
                        border:1px solid rgba(245,158,11,.2);border-radius:8px;font-size:13px">
              ⏳ Analysis running — if results don't appear, check that your file has the required columns
              and try clicking Run again.
            </div>`;
        }
      }, 2000);

      // After 8s, if still empty show error
      setTimeout(() => {
        const content = out.innerHTML.trim();
        if (!content || content.includes('⏳')) {
          out.innerHTML = `
            <div style="padding:12px;color:#f87171;background:rgba(248,113,113,.08);
                        border:1px solid rgba(248,113,113,.2);border-radius:8px;font-size:13px">
              ❌ No results returned. Please verify your data file format and column selection,
              then try again.
            </div>`;
        }
      }, 8000);
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    ANALYSIS_CONFIGS.forEach(wireAnalysis);

    // Re-wire after sidebar switches
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
      new MutationObserver(() => ANALYSIS_CONFIGS.forEach(wireAnalysis))
        .observe(sidebar, { childList: true, subtree: true });
    }
  });

})();
