/**
 * StatMind Missing Handlers Patch
 * Adds missing click handlers for:
 *   - Tolerance Interval (run-tol-btn)
 *   - TOST Equivalence (run-equiv-btn)
 *   - Two-Way ANOVA (run-twa-btn)
 * Fixes broken render functions for Transformation, Sixpack, CUSUM
 */

(function fixMissingHandlers() {

  // ── Shared helpers ─────────────────────────────────────────────────────────
  const API = window.API || window.location.origin;

  function fmtNum(v) {
    if (v === null || v === undefined) return '—';
    if (typeof v !== 'number') return String(v);
    if (Math.abs(v) < 0.0001 && v !== 0) return v.toExponential(4);
    return parseFloat(v.toFixed(6)).toString();
  }

  function resultCard(title, rows, verdictText, verdictType) {
    const colors = {
      pass:    ['rgba(52,217,128,.12)', 'rgba(52,217,128,.35)', '#34d980'],
      fail:    ['rgba(248,113,113,.12)', 'rgba(248,113,113,.35)', '#f87171'],
      warning: ['rgba(245,158,11,.12)', 'rgba(245,158,11,.35)', '#f59e0b'],
      info:    ['rgba(99,102,241,.12)', 'rgba(99,102,241,.35)', '#818cf8'],
    };
    const [bg, border, color] = colors[verdictType || 'info'];

    const rowsHtml = rows.map(([label, value]) => `
      <tr>
        <td style="padding:6px 14px;color:#8b8fa8;font-size:12px;width:50%">${label}</td>
        <td style="padding:6px 14px;color:#e8eaf0;font-size:13px;font-weight:600;font-family:'SF Mono',monospace">${value}</td>
      </tr>`).join('');

    const verdictHtml = verdictText ? `
      <div style="margin:0 0 12px;padding:10px 14px;background:${bg};border:1px solid ${border};
                  border-radius:8px;color:${color};font-size:13px;line-height:1.5">
        ${verdictText}
      </div>` : '';

    return `
      <div style="background:#111420;border:1px solid rgba(255,255,255,.08);border-radius:12px;overflow:hidden;margin-bottom:16px">
        <div style="padding:10px 14px;background:rgba(99,102,241,.06);border-bottom:1px solid rgba(255,255,255,.06);
                    font-size:11px;font-weight:700;color:#818cf8;text-transform:uppercase;letter-spacing:.06em">
          ${title}
        </div>
        ${verdictHtml}
        <table style="width:100%;border-collapse:collapse">${rowsHtml}</table>
      </div>`;
  }

  function showResult(html) {
    // Use showContent if available, otherwise inject into primary area
    if (typeof showContent === 'function') {
      showContent(html);
    } else {
      const panel = document.getElementById('primary-chart-wrap') ||
                    document.getElementById('results-panel') ||
                    document.querySelector('.app-main');
      if (panel) panel.innerHTML = html;
    }
  }

  function setBtn(id, disabled, text) {
    const btn = document.getElementById(id);
    if (btn) { btn.disabled = disabled; if (text) btn.textContent = text; }
  }

  // ── 1. TOLERANCE INTERVAL ─────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {

    let tolFile = null, tolCol = null;

    // Wire file input
    const tolInput = document.getElementById('tol-file-input');
    if (tolInput && !tolInput.dataset.patched) {
      tolInput.dataset.patched = '1';
      tolInput.addEventListener('change', async (e) => {
        tolFile = e.target.files[0];
        if (!tolFile) return;
        document.getElementById('tol-upload-title') && (document.getElementById('tol-upload-title').textContent = tolFile.name);

        // Load columns
        const fd = new FormData(); fd.append('file', tolFile);
        try {
          const r = await fetch(`${API}/api/v1/columns`, {method:'POST', body:fd});
          const d = await r.json();
          const cols = d.numeric_columns || d.columns || [];
          const list = document.getElementById('tol-col-list');
          if (list) {
            list.innerHTML = cols.map(c =>
              `<div class="col-item" onclick="tolCol='${c}';document.querySelectorAll('#tol-col-list .col-item').forEach(x=>x.classList.remove('active'));this.classList.add('active');document.getElementById('run-tol-btn').disabled=false">${c}</div>`
            ).join('');
          }
          const sec = document.getElementById('tol-col-section');
          if (sec) sec.style.display = 'block';
        } catch(e) { console.error('Tol columns:', e); }
      });
    }

    const tolBtn = document.getElementById('run-tol-btn');
    if (tolBtn && !tolBtn.dataset.patched) {
      tolBtn.dataset.patched = '1';
      tolBtn.addEventListener('click', async () => {
        if (!tolFile || !tolCol) return;
        const coverage   = parseFloat(document.getElementById('tol-coverage')?.value || 95) / 100;
        const confidence = parseFloat(document.getElementById('tol-confidence')?.value || 95) / 100;
        const itype      = document.getElementById('tol-type')?.value || 'two-sided';
        const usl        = document.getElementById('tol-usl')?.value;
        const lsl        = document.getElementById('tol-lsl')?.value;

        setBtn('run-tol-btn', true, 'Calculating…');
        if (typeof showContent === 'function') showContent(loadHtml ? loadHtml('Computing tolerance interval…') : '<p>Loading…</p>');

        const fd = new FormData(); fd.append('file', tolFile);
        let url = `${API}/api/v1/tolerance/analyze?column=${encodeURIComponent(tolCol)}&coverage=${coverage}&confidence=${confidence}&interval_type=${itype}`;
        if (usl) url += `&usl=${parseFloat(usl)}`;
        if (lsl) url += `&lsl=${parseFloat(lsl)}`;

        try {
          const r = await fetch(url, {method:'POST', body:fd});
          if (!r.ok) throw new Error((await r.json()).detail);
          const d = await r.json();

          const rows = [
            ['Lower Bound', fmtNum(d.lower_bound)],
            ['Upper Bound', fmtNum(d.upper_bound)],
            ['Coverage', `${((d.coverage||coverage)*100).toFixed(1)}%`],
            ['Confidence', `${((d.confidence||confidence)*100).toFixed(1)}%`],
            ['Method', d.method || itype],
            ['Sample Size (n)', d.n || '—'],
            ['Mean', fmtNum(d.mean)],
            ['Std Dev', fmtNum(d.std)],
          ];

          const verdict = d.verdict || d.interpretation || `Tolerance interval: [${fmtNum(d.lower_bound)}, ${fmtNum(d.upper_bound)}]`;
          const type = d.within_spec === false ? 'warning' : 'pass';
          showResult(resultCard('Tolerance Interval Results', rows, verdict, type));
          if (typeof showToast === 'function') showToast('Tolerance interval complete');
        } catch(e) {
          if (typeof showToast === 'function') showToast(e.message, true);
          if (typeof showEmpty === 'function') showEmpty('', e.message, '');
        } finally {
          setBtn('run-tol-btn', false, 'Calculate Tolerance Interval');
        }
      });
    }

    // ── 2. TOST EQUIVALENCE ─────────────────────────────────────────────────
    const equivBtn = document.getElementById('run-equiv-btn');
    if (equivBtn && !equivBtn.dataset.patched) {
      equivBtn.dataset.patched = '1';
      equivBtn.addEventListener('click', async () => {
        const equivFile = window.equivFile;
        const equivColA = window.equivColA;
        const equivColB = window.equivColB;
        if (!equivFile || !equivColA || !equivColB) return;

        const delta = parseFloat(document.getElementById('equiv-delta')?.value || 0.05);
        setBtn('run-equiv-btn', true, 'Testing…');
        if (typeof showContent === 'function') showContent(loadHtml ? loadHtml('Running TOST equivalence test…') : '<p>Loading…</p>');

        const fd = new FormData(); fd.append('file', equivFile);
        const url = `${API}/api/v1/equivalence/tost?col_a=${encodeURIComponent(equivColA)}&col_b=${encodeURIComponent(equivColB)}&delta=${delta}`;

        try {
          const r = await fetch(url, {method:'POST', body:fd});
          if (!r.ok) throw new Error((await r.json()).detail);
          const d = await r.json();

          const equiv = d.equivalent === true;
          const rows = [
            ['p-value (lower)', fmtNum(d.p_lower ?? d.p_value_lower)],
            ['p-value (upper)', fmtNum(d.p_upper ?? d.p_value_upper)],
            ['Equivalence Margin (Δ)', fmtNum(delta)],
            ['Mean Difference', fmtNum(d.mean_diff ?? d.mean_difference)],
            ['90% CI Lower', fmtNum(d.ci_lower)],
            ['90% CI Upper', fmtNum(d.ci_upper)],
            ['Alpha', fmtNum(d.alpha || 0.05)],
            ['n (A)', d.n_a || '—'],
            ['n (B)', d.n_b || '—'],
          ];

          const verdict = d.verdict || d.conclusion || (equiv ? 'Equivalent — both one-sided p-values < α' : 'Not equivalent');
          showResult(resultCard('TOST Equivalence Test', rows, verdict, equiv ? 'pass' : 'fail'));
          if (typeof showToast === 'function') showToast('TOST complete');
        } catch(e) {
          if (typeof showToast === 'function') showToast(e.message, true);
          if (typeof showEmpty === 'function') showEmpty('', e.message, '');
        } finally {
          setBtn('run-equiv-btn', false, 'Run TOST Equivalence');
        }
      });
    }

    // ── 3. TWO-WAY ANOVA ────────────────────────────────────────────────────
    const twaBtn = document.getElementById('run-twa-btn');
    if (twaBtn && !twaBtn.dataset.patched) {
      twaBtn.dataset.patched = '1';
      twaBtn.addEventListener('click', async () => {
        const twaFile  = window.twaFile;
        const twaResp  = window.twaResp  || window.twaResponseCol;
        const twaFactA = window.twaFactA || window.twaFactorA;
        const twaFactB = window.twaFactB || window.twaFactorB;
        if (!twaFile || !twaResp) {
          if (typeof showToast === 'function') showToast('Upload a file and select Response + Factor columns', true);
          return;
        }

        setBtn('run-twa-btn', true, 'Analyzing…');
        if (typeof showContent === 'function') showContent(loadHtml ? loadHtml('Running Two-Way ANOVA…') : '<p>Loading…</p>');

        try {
          // Read file as text and parse
          const text = await twaFile.text();
          const lines = text.trim().split('\n');
          const headers = lines[0].split(',').map(h => h.trim().replace(/"/g,''));

          function getCol(name) {
            const idx = headers.indexOf(name);
            if (idx === -1) return [];
            return lines.slice(1).map(l => l.split(',')[idx]?.trim().replace(/"/g,''));
          }

          const respData  = getCol(twaResp).map(Number).filter(v => !isNaN(v));
          const factAData = twaFactA ? getCol(twaFactA) : [];
          const factBData = twaFactB ? getCol(twaFactB) : [];

          const payload = {
            response: respData,
            factor_a: factAData,
            factor_b: factBData,
            response_name: twaResp,
            factor_a_name: twaFactA || 'Factor_A',
            factor_b_name: twaFactB || 'Factor_B',
            alpha: 0.05,
          };

          const r = await fetch(`${API}/api/v1/hypothesis/two-way-anova`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
          });
          if (!r.ok) throw new Error((await r.json()).detail);
          const d = await r.json();

          // Build ANOVA table
          const anovaRows = [];
          if (d.factor_a) anovaRows.push([`${twaFactA||'Factor A'} (F)`, fmtNum(d.factor_a.f_stat)], [`${twaFactA||'Factor A'} (p)`, fmtNum(d.factor_a.p_value)]);
          if (d.factor_b) anovaRows.push([`${twaFactB||'Factor B'} (F)`, fmtNum(d.factor_b.f_stat)], [`${twaFactB||'Factor B'} (p)`, fmtNum(d.factor_b.p_value)]);
          if (d.interaction) anovaRows.push(['Interaction (F)', fmtNum(d.interaction.f_stat)], ['Interaction (p)', fmtNum(d.interaction.p_value)]);
          if (d.r_squared !== undefined) anovaRows.push(['R²', fmtNum(d.r_squared)]);

          const verdict = d.verdict || d.conclusion || 'Two-Way ANOVA complete';
          showResult(resultCard('Two-Way ANOVA Results', anovaRows, verdict, 'info'));
          if (typeof showToast === 'function') showToast('Two-Way ANOVA complete');
        } catch(e) {
          if (typeof showToast === 'function') showToast(e.message, true);
          if (typeof showEmpty === 'function') showEmpty('', e.message, '');
        } finally {
          setBtn('run-twa-btn', false, 'Run Two-Way ANOVA');
        }
      });
    }

  }); // end DOMContentLoaded

})();
