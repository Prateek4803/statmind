/**
 * StatMind Session Persistence v1
 * Saves analysis results to localStorage so page refresh doesn't lose work.
 *
 * Add to index.html before </body>:
 * <script src="/static/session_persistence.js"></script>
 */

(function StatMindPersistence() {
  const KEY     = 'statmind_session_v1';
  const MAX_AGE = 24 * 60 * 60 * 1000; // 24 hours

  // ── Save ──────────────────────────────────────────────────────────
  function save() {
    try {
      const session = {
        ts:         Date.now(),
        capData:    window.capData    || {},
        spcData:    window.spcData    || {},
        normData:   window.normData   || null,
        grrData:    window.grrData    || {},
        capaReports: window.capaReports || {},
        globalProcType: window.globalProcType || '',
        globalFileName: window.globalFile?.name || '',
        colNameMap: window.colNameMap  || {},
        analysisHistory: window.analysisHistory || [],
      };

      // Don't save empty sessions
      const hasData = Object.keys(session.capData).length > 0
                   || Object.keys(session.spcData).length > 0
                   || session.normData !== null;
      if (!hasData) return;

      const json = JSON.stringify(session);
      // Guard against localStorage quota (5MB limit)
      if (json.length > 4 * 1024 * 1024) {
        console.warn('[StatMind] Session too large to persist — skipping');
        return;
      }
      localStorage.setItem(KEY, json);
    } catch (e) {
      // localStorage might be full or disabled — silent fail
      console.warn('[StatMind] Could not save session:', e.message);
    }
  }

  // ── Load ──────────────────────────────────────────────────────────
  function load() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return null;
      const session = JSON.parse(raw);
      // Expire after 24 hours
      if (Date.now() - session.ts > MAX_AGE) {
        localStorage.removeItem(KEY);
        return null;
      }
      return session;
    } catch (e) {
      return null;
    }
  }

  // ── Restore ───────────────────────────────────────────────────────
  function restore(session) {
    if (session.capData)      Object.assign(window.capData    || {}, session.capData);
    if (session.spcData)      Object.assign(window.spcData    || {}, session.spcData);
    if (session.normData)     window.normData     = session.normData;
    if (session.grrData)      Object.assign(window.grrData    || {}, session.grrData);
    if (session.capaReports)  Object.assign(window.capaReports|| {}, session.capaReports);
    if (session.globalProcType) window.globalProcType = session.globalProcType;
    if (session.colNameMap)   Object.assign(window.colNameMap || {}, session.colNameMap);

    // Update context bar
    const ctxFn = document.getElementById('ctx-filename');
    if (ctxFn && session.globalFileName) {
      ctxFn.innerHTML = `📂 <strong>${session.globalFileName}</strong> <span style="color:var(--text3);font-size:10px">(restored)</span>`;
    }
    document.getElementById('context-bar')?.classList.add('visible');
    document.getElementById('sidebar')?.style.setProperty('display', 'flex');
    document.getElementById('welcome-screen') && (document.getElementById('welcome-screen').style.display = 'none');

    // Update attach status
    if (typeof updateAttachStatus === 'function') {
      window.attachedCap  = Object.values(session.capData || {})[0]  || null;
      window.attachedSpc  = Object.values(session.spcData || {})[0]  || null;
      window.attachedNorm = session.normData?.results?.[0]           || null;
      window.attachedGrr  = Object.values(session.grrData || {})[0]  || null;
      updateAttachStatus();
    }

    // Navigate to last active analysis
    const lastAnalysis = session.analysisHistory?.slice(-1)[0];
    if (lastAnalysis && typeof switchAnalysis === 'function') {
      setTimeout(() => switchAnalysis(lastAnalysis), 100);
    }
  }

  // ── Toast helper ──────────────────────────────────────────────────
  function showRestoreToast(session) {
    const mins = Math.round((Date.now() - session.ts) / 60000);
    const label = mins < 2 ? 'just now' : mins < 60 ? `${mins} min ago` : `${Math.round(mins/60)}h ago`;

    const toast = document.createElement('div');
    toast.style.cssText = [
      'position:fixed', 'bottom:24px', 'left:50%', 'transform:translateX(-50%)',
      'background:#111420', 'border:1px solid rgba(99,102,241,.35)',
      'border-radius:12px', 'padding:13px 18px',
      'font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif',
      'font-size:13px', 'color:#e8eaf0', 'z-index:8000',
      'display:flex', 'align-items:center', 'gap:14px',
      'box-shadow:0 8px 32px rgba(0,0,0,.5)',
      'max-width:420px', 'width:90%',
    ].join(';');

    const analysisCount = Object.keys(session.capData || {}).length
                        + Object.keys(session.spcData || {}).length
                        + (session.normData ? 1 : 0);

    toast.innerHTML = `
      <span style="font-size:20px">💾</span>
      <div style="flex:1">
        <div style="font-weight:600;margin-bottom:2px">Session found from ${label}</div>
        <div style="color:#8b8fa8;font-size:12px">${analysisCount} analysis result${analysisCount !== 1 ? 's' : ''} · ${session.globalFileName || 'unknown file'}</div>
      </div>
      <button id="sm-restore-btn"
        style="background:rgba(99,102,241,.15);border:1px solid rgba(99,102,241,.35);
               color:#818cf8;padding:6px 14px;border-radius:7px;font-size:12px;
               font-weight:600;cursor:pointer;white-space:nowrap;font-family:inherit">
        Restore →
      </button>
      <button id="sm-dismiss-btn"
        style="background:none;border:none;color:#4b4f66;font-size:18px;
               cursor:pointer;padding:0 4px;line-height:1">
        ✕
      </button>
    `;

    document.body.appendChild(toast);

    toast.querySelector('#sm-restore-btn').addEventListener('click', () => {
      restore(session);
      toast.remove();
      if (typeof showToast === 'function') showToast('✅ Session restored');
    });

    toast.querySelector('#sm-dismiss-btn').addEventListener('click', () => {
      toast.remove();
    });

    // Auto-dismiss after 12 seconds
    setTimeout(() => toast.remove(), 12000);
  }

  // ── Auto-save every 30 seconds ────────────────────────────────────
  function startAutoSave() {
    setInterval(save, 30 * 1000);

    // Also save when user is about to leave
    window.addEventListener('beforeunload', save);

    // Save after each analysis run (patch run buttons)
    const RUN_BTN_IDS = [
      'run-cap-btn', 'run-norm-btn', 'run-spc-btn',
      'run-grr-btn', 'run-capa-btn', 'run-report-btn',
    ];
    RUN_BTN_IDS.forEach(id => {
      const btn = document.getElementById(id);
      if (btn) {
        btn.addEventListener('click', () => {
          // Save 3 seconds after run button clicked (results should be back)
          setTimeout(save, 3000);
        });
      }
    });
  }

  // ── Init ──────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    // Check for saved session
    const session = load();
    const hasData = session && (
      Object.keys(session.capData || {}).length > 0  ||
      Object.keys(session.spcData || {}).length > 0  ||
      session.normData !== null
    );

    if (hasData) {
      showRestoreToast(session);
    }

    startAutoSave();
  });

  // Expose for manual use
  window.SM_Session = { save, load, restore, clear: () => localStorage.removeItem(KEY) };
})();
