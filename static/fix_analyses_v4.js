/**
 * StatMind Complete Analysis Fix v4
 * Fixes ALL broken analyses with CORRECT endpoint URLs and payload formats
 * Based on actual main.py audit
 */

(function fixAllAnalyses() {

  const API = window.API || window.location.origin;

  // ── Shared UI helpers ──────────────────────────────────────────────────────
  function fmtNum(v) {
    if (v === null || v === undefined) return '—';
    if (typeof v !== 'number') return String(v);
    if (Math.abs(v) < 0.0001 && v !== 0) return v.toExponential(4);
    return parseFloat(v.toFixed(6)).toString();
  }

  function mkCard(title, rows, verdict, vtype) {
    const C = {
      pass:    ['rgba(52,217,128,.1)','rgba(52,217,128,.3)','#34d980'],
      fail:    ['rgba(248,113,113,.1)','rgba(248,113,113,.3)','#f87171'],
      warning: ['rgba(245,158,11,.1)','rgba(245,158,11,.3)','#f59e0b'],
      info:    ['rgba(99,102,241,.1)','rgba(99,102,241,.3)','#818cf8'],
    };
    const [bg,bdr,clr] = C[vtype||'info'];
    const rowHtml = rows.map(([l,v])=>
      `<tr><td style="padding:6px 14px;color:#8b8fa8;font-size:12px;white-space:nowrap">${l}</td>
           <td style="padding:6px 14px;color:#e8eaf0;font-size:13px;font-weight:600;font-family:monospace">${v}</td></tr>`
    ).join('');
    const vHtml = verdict
      ? `<div style="margin:12px 14px 0;padding:10px;background:${bg};border:1px solid ${bdr};border-radius:8px;color:${clr};font-size:13px">${verdict}</div>`
      : '';
    return `<div style="background:#111420;border:1px solid rgba(255,255,255,.08);border-radius:12px;overflow:hidden;margin:12px 0">
      <div style="padding:9px 14px;background:rgba(99,102,241,.07);border-bottom:1px solid rgba(255,255,255,.06);font-size:11px;font-weight:700;color:#818cf8;text-transform:uppercase;letter-spacing:.06em">${title}</div>
      ${vHtml}
      <table style="width:100%;border-collapse:collapse;margin-top:4px">${rowHtml}</table>
    </div>`;
  }

  function show(html) {
    if (typeof showContent === 'function') showContent(html);
  }
  function toast(msg, err) {
    if (typeof showToast === 'function') showToast(msg, err);
  }
  function empty(msg) {
    if (typeof showEmpty === 'function') showEmpty('❌', msg, '');
  }
  function setBtn(id, dis, txt) {
    const b = document.getElementById(id);
    if (b) { b.disabled = dis; if (txt) b.textContent = txt; }
  }

  // ── ANOVA table renderer ───────────────────────────────────────────────────
  function renderAnovaTable(table, title) {
    const hdr = `<tr style="background:rgba(99,102,241,.1)">
      ${['Source','SS','df','MS','F','p','Sig'].map(h=>`<th style="padding:6px 10px;color:#818cf8;font-size:11px;text-align:left">${h}</th>`).join('')}
    </tr>`;
    const rows = table.map(row => `<tr>
      <td style="padding:5px 10px;color:#e8eaf0;font-size:12px">${row.source}</td>
      <td style="padding:5px 10px;color:#c8cae0;font-size:12px;font-family:monospace">${fmtNum(row.ss)}</td>
      <td style="padding:5px 10px;color:#c8cae0;font-size:12px;font-family:monospace">${row.df}</td>
      <td style="padding:5px 10px;color:#c8cae0;font-size:12px;font-family:monospace">${row.ms ? fmtNum(row.ms) : '—'}</td>
      <td style="padding:5px 10px;color:#c8cae0;font-size:12px;font-family:monospace">${row.f ? fmtNum(row.f) : '—'}</td>
      <td style="padding:5px 10px;color:#c8cae0;font-size:12px;font-family:monospace">${row.p != null ? fmtNum(row.p) : '—'}</td>
      <td style="padding:5px 10px;font-size:13px">${row.significant ? '<span style="color:#34d980">✓</span>' : '<span style="color:#4b4f66">—</span>'}</td>
    </tr>`).join('');
    return `<div style="background:#111420;border:1px solid rgba(255,255,255,.08);border-radius:12px;overflow:hidden;margin:12px 0">
      <div style="padding:9px 14px;background:rgba(99,102,241,.07);border-bottom:1px solid rgba(255,255,255,.06);font-size:11px;font-weight:700;color:#818cf8;text-transform:uppercase;letter-spacing:.06em">${title}</div>
      <div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse">${hdr}${rows}</table></div>
    </div>`;
  }

  document.addEventListener('DOMContentLoaded', () => {

    // ════════════════════════════════════════════════════════════════
    // FIX 1: TOLERANCE INTERVAL
    // Correct endpoint: POST /api/v1/tolerance/analyze
    // Params: column (Query), coverage, confidence, interval_type, usl, lsl
    // ════════════════════════════════════════════════════════════════
    (function fixTolerance() {
      let tolFile = null, tolCol = null;

      const zone = document.getElementById('tol-upload');
      const inp  = document.getElementById('tol-file-input');
      if (zone && inp && !zone.dataset.fpatch) {
        zone.dataset.fpatch = '1';
        zone.addEventListener('click', () => inp.click());
        zone.addEventListener('dragover', e => { e.preventDefault(); zone.style.borderColor='rgba(45,212,160,.7)'; });
        zone.addEventListener('dragleave', () => zone.style.borderColor='');
        zone.addEventListener('drop', e => { e.preventDefault(); if (e.dataTransfer.files[0]) { inp.files = e.dataTransfer.files; inp.dispatchEvent(new Event('change')); } });
      }

      if (inp && !inp.dataset.tpatch) {
        inp.dataset.tpatch = '1';
        inp.addEventListener('change', async e => {
          tolFile = e.target.files[0];
          if (!tolFile) return;
          const lbl = document.getElementById('tol-upload-title');
          if (lbl) lbl.textContent = tolFile.name;

          const fd = new FormData(); fd.append('file', tolFile);
          try {
            const r = await fetch(`${API}/api/v1/columns`, {method:'POST', body:fd});
            const d = await r.json();
            const cols = d.numeric_columns || [];
            const list = document.getElementById('tol-col-list');
            if (list) {
              list.innerHTML = cols.map(c =>
                `<div class="col-item" onclick="
                  document.querySelectorAll('#tol-col-list .col-item').forEach(x=>x.classList.remove('active'));
                  this.classList.add('active');
                  window._tolCol='${c}';
                  document.getElementById('run-tol-btn').disabled=false;
                ">${c}</div>`
              ).join('');
            }
            const sec = document.getElementById('tol-col-section');
            if (sec) sec.style.display = 'block';
          } catch(e) { toast('Could not read columns: '+e.message, true); }
        });
      }

      const btn = document.getElementById('run-tol-btn');
      if (btn && !btn.dataset.tpatch) {
        btn.dataset.tpatch = '1';
        btn.addEventListener('click', async () => {
          tolCol = window._tolCol;
          if (!tolFile || !tolCol) { toast('Select a file and column first', true); return; }

          const coverage    = parseFloat(document.getElementById('tol-coverage')?.value || 99) / 100;
          const confidence  = parseFloat(document.getElementById('tol-confidence')?.value || 95) / 100;
          const itype       = (document.getElementById('tol-type')?.value || 'two_sided').replace('-','_');
          const usl         = document.getElementById('tol-usl')?.value;
          const lsl         = document.getElementById('tol-lsl')?.value;

          setBtn('run-tol-btn', true, 'Calculating…');
          show(typeof loadHtml === 'function' ? loadHtml('Computing tolerance interval…') : '<p>Loading…</p>');

          const fd = new FormData(); fd.append('file', tolFile);
          let url = `${API}/api/v1/tolerance/analyze?column=${encodeURIComponent(tolCol)}&coverage=${coverage}&confidence=${confidence}&interval_type=${itype}`;
          if (usl) url += `&usl=${parseFloat(usl)}`;
          if (lsl) url += `&lsl=${parseFloat(lsl)}`;

          try {
            const r = await fetch(url, {method:'POST', body:fd});
            if (!r.ok) { const e = await r.json(); throw new Error(e.detail || JSON.stringify(e)); }
            const d = await r.json();
            const rows = [
              ['Lower Bound', fmtNum(d.lower_bound)],
              ['Upper Bound', fmtNum(d.upper_bound)],
              ['Coverage', `${((d.coverage||coverage)*100).toFixed(1)}%`],
              ['Confidence', `${((d.confidence||confidence)*100).toFixed(1)}%`],
              ['Method', d.method||itype],
              ['n', d.n||'—'],
              ['Mean', fmtNum(d.mean)],
              ['Std Dev', fmtNum(d.std)],
            ].filter(([,v]) => v !== '—' && v !== null);
            const verdict = d.verdict || d.interpretation || `[${fmtNum(d.lower_bound)}, ${fmtNum(d.upper_bound)}]`;
            show(mkCard('Tolerance Interval', rows, verdict, 'info'));
            toast('✅ Tolerance interval complete');
          } catch(e) { toast(e.message, true); empty(e.message); }
          finally { setBtn('run-tol-btn', false, 'Calculate Tolerance Interval'); }
        });
      }
    })();

    // ════════════════════════════════════════════════════════════════
    // FIX 2: TOST EQUIVALENCE
    // Correct endpoint: POST /api/v1/equivalence/analyze
    // Params: col_a, col_b, delta_pct, alpha (Query) + file (Form)
    // ════════════════════════════════════════════════════════════════
    (function fixTOST() {
      const btn = document.getElementById('run-equiv-btn');
      if (!btn || btn.dataset.tostpatch) return;
      btn.dataset.tostpatch = '1';

      btn.addEventListener('click', async () => {
        const equivFile = window.equivFile;
        const equivColA = window.equivColA;
        const equivColB = window.equivColB;

        if (!equivFile || !equivColA || !equivColB) {
          toast('Upload a file and select both columns', true); return;
        }
        const deltaPct = parseFloat(document.getElementById('equiv-delta')?.value || 5);
        const alpha    = parseFloat(document.getElementById('equiv-alpha')?.value || 0.05);

        setBtn('run-equiv-btn', true, 'Testing…');
        show(typeof loadHtml === 'function' ? loadHtml('Running TOST equivalence test…') : '<p>Loading…</p>');

        const fd = new FormData(); fd.append('file', equivFile);
        const url = `${API}/api/v1/equivalence/analyze?col_a=${encodeURIComponent(equivColA)}&col_b=${encodeURIComponent(equivColB)}&delta_pct=${deltaPct}&alpha=${alpha}`;

        try {
          const r = await fetch(url, {method:'POST', body:fd});
          if (!r.ok) { const e = await r.json(); throw new Error(e.detail || JSON.stringify(e)); }
          const d = await r.json();

          const equiv = d.equivalent === true;
          const rows = [
            ['p-value (lower)', fmtNum(d.p_lower ?? d.p_lower_bound)],
            ['p-value (upper)', fmtNum(d.p_upper ?? d.p_upper_bound)],
            ['Equivalence Margin', `±${deltaPct}%`],
            ['Mean Difference', fmtNum(d.mean_diff ?? d.difference)],
            ['90% CI', `[${fmtNum(d.ci_lower)}, ${fmtNum(d.ci_upper)}]`],
            ['Alpha (α)', fmtNum(alpha)],
            ['n (A)', d.n_a||'—'],
            ['n (B)', d.n_b||'—'],
          ].filter(([,v]) => v && v !== '—' && v !== '[—, —]');

          const verdict = d.verdict || d.conclusion || (equiv ? '✅ Equivalent' : '❌ Not equivalent');
          show(mkCard('TOST Equivalence Test', rows, verdict, equiv ? 'pass' : 'fail'));
          toast(equiv ? '✅ Equivalent' : '⚠️ Not equivalent');
        } catch(e) { toast(e.message, true); empty(e.message); }
        finally { setBtn('run-equiv-btn', false, 'Run TOST Equivalence'); }
      });
    })();

    // ════════════════════════════════════════════════════════════════
    // FIX 3: TWO-WAY ANOVA
    // Correct endpoint: POST /api/v1/hypothesis/two-way-anova (JSON body)
    // Body: { data: [...], factor_a: [...], factor_b: [...], name_a, name_b, response }
    // ════════════════════════════════════════════════════════════════
    (function fixTwoWayAnova() {
      const btn = document.getElementById('run-twa-btn');
      if (!btn || btn.dataset.twapatch) return;
      btn.dataset.twapatch = '1';

      btn.addEventListener('click', async () => {
        const twaFile = window.twaFile;
        const twaResp = window.twaResp || window.twaResponseCol;
        const twaFactA = window.twaFactA || window.twaFactorA;
        const twaFactB = window.twaFactB || window.twaFactorB;

        if (!twaFile) { toast('Upload a file first', true); return; }
        if (!twaResp) { toast('Select a response column', true); return; }

        setBtn('run-twa-btn', true, 'Analyzing…');
        show(typeof loadHtml === 'function' ? loadHtml('Running Two-Way ANOVA…') : '<p>Loading…</p>');

        try {
          // Parse the CSV file client-side
          const text = await twaFile.text();
          const lines = text.trim().split('\n').filter(l => l.trim());
          const sep = lines[0].includes('\t') ? '\t' : ',';
          const headers = lines[0].split(sep).map(h => h.trim().replace(/^"|"$/g,''));

          function getColData(name) {
            const idx = headers.indexOf(name);
            if (idx === -1) return null;
            return lines.slice(1).map(l => l.split(sep)[idx]?.trim().replace(/^"|"$/g,''));
          }

          const respData  = getColData(twaResp)?.map(Number).filter(v => !isNaN(v));
          const factAData = twaFactA ? getColData(twaFactA) : null;
          const factBData = twaFactB ? getColData(twaFactB) : null;

          if (!respData || respData.length === 0) throw new Error(`Column "${twaResp}" not found or has no numeric data`);
          if (!factAData) throw new Error('Select Factor A column');

          const payload = {
            data: respData,
            factor_a: factAData || respData.map((_,i) => `Group${(i%2)+1}`),
            factor_b: factBData || respData.map((_,i) => `Level${(i%3)+1}`),
            name_a: twaFactA || 'Factor A',
            name_b: twaFactB || 'Factor B',
            response: twaResp,
            alpha: 0.05,
          };

          const r = await fetch(`${API}/api/v1/hypothesis/two-way-anova`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
          });
          if (!r.ok) { const e = await r.json(); throw new Error(e.detail || JSON.stringify(e)); }
          const d = await r.json();

          let html = '';
          if (d.anova_table) {
            html += renderAnovaTable(d.anova_table, `Two-Way ANOVA — ${twaResp}`);
          }

          const sigFactors = (d.anova_table||[]).filter(row => row.significant && row.source !== 'Error' && row.source !== 'Total');
          const verdict = sigFactors.length > 0
            ? `Significant effects: ${sigFactors.map(r=>r.source).join(', ')}`
            : 'No significant effects detected at α = 0.05';
          html += mkCard('Summary', [
            ['Response', twaResp],
            ['Factor A', twaFactA||'Factor A'],
            ['Factor B', twaFactB||'Factor B'],
            ['n total', d.n_total||respData.length],
            ['Grand mean', fmtNum(d.grand_mean)],
          ], verdict, sigFactors.length > 0 ? 'warning' : 'info');

          show(html);
          toast('✅ Two-Way ANOVA complete');
        } catch(e) { toast(e.message, true); empty(e.message); }
        finally { setBtn('run-twa-btn', false, 'Run Two-Way ANOVA'); }
      });
    })();

    // ════════════════════════════════════════════════════════════════
    // FIX 4: SIXPACK — patch renderSixpack if it's broken
    // ════════════════════════════════════════════════════════════════
    (function fixSixpack() {
      const origRunSixpack = window.runSixpack;
      if (!origRunSixpack) return;

      // Wrap runSixpack to catch errors and show them
      window.runSixpack = async function() {
        try {
          await origRunSixpack();
        } catch(e) {
          toast(e.message, true);
          empty('Sixpack error: ' + e.message);
          setBtn('run-sixpack-btn', false, 'Run Capability Sixpack');
        }
      };
    })();

  }); // end DOMContentLoaded

})();
