/**
 * StatMind UI Patch v2
 * Fixes:
 *   1. Mobile nav toggle
 *   2. Upload area redesign
 *   3. PDF loading spinner
 *   4. Email capture before PDF download  (already in index.html — enhanced here)
 *   5. Magic link authentication
 *
 * Drop this <script> tag into index.html right before </body>
 * <script src="/static/ui_patch_v2.js"></script>
 */

/* ══════════════════════════════════════════════════════════════════
   PATCH 1 — MOBILE NAV TOGGLE FIX
   The hamburger button calls openMobDrawer() but the drawer panel
   wasn't transitioning because the CSS transform was applied before
   the 'open' class was added (no rAF tick). Fixed here.
   ══════════════════════════════════════════════════════════════════ */
(function fixMobileNav() {
  // Patch openMobDrawer to force a reflow before adding 'open'
  const _orig = window.openMobDrawer;
  window.openMobDrawer = function () {
    const drawer = document.getElementById('mob-drawer');
    const panel  = document.querySelector('.mob-drawer-panel');
    if (!drawer || !panel) { if (_orig) _orig(); return; }

    drawer.classList.add('open');
    document.body.style.overflow = 'hidden';

    // Force reflow so CSS transition fires
    panel.style.transform = 'translateX(-100%)';
    panel.style.transition = 'transform .28s cubic-bezier(.4,0,.2,1)';
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        panel.style.transform = 'translateX(0)';
      });
    });

    // Sync API status dot
    const dot    = document.getElementById('status-dot');
    const mobDot = document.getElementById('mob-status-dot');
    const txt    = document.getElementById('status-text');
    const mobTxt = document.getElementById('mob-status-text');
    if (dot && mobDot) mobDot.className = dot.className;
    if (txt && mobTxt) mobTxt.textContent = txt.textContent;
  };

  // Patch closeMobDrawer to animate out
  const _origClose = window.closeMobDrawer;
  window.closeMobDrawer = function () {
    const drawer = document.getElementById('mob-drawer');
    const panel  = document.querySelector('.mob-drawer-panel');
    if (!drawer || !panel) { if (_origClose) _origClose(); return; }

    panel.style.transform = 'translateX(-100%)';
    setTimeout(() => {
      drawer.classList.remove('open');
      document.body.style.overflow = '';
      panel.style.transform = '';
    }, 280);
  };

  // Also fix the hamburger button click — wire it if missing
  document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('mob-menu-btn');
    if (btn && !btn.dataset.patched) {
      btn.dataset.patched = '1';
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        window.openMobDrawer();
      });
    }

    // Close when tapping overlay
    const overlay = document.querySelector('.mob-drawer-overlay');
    if (overlay && !overlay.dataset.patched) {
      overlay.dataset.patched = '1';
      overlay.addEventListener('click', () => window.closeMobDrawer());
    }
  });
})();


/* ══════════════════════════════════════════════════════════════════
   PATCH 2 — UPLOAD AREA REDESIGN
   Replaces plain text upload zones with dashed-border, icon,
   file type chip design. Runs after DOM is ready.
   ══════════════════════════════════════════════════════════════════ */
(function upgradeUploadZones() {
  const CHIP_STYLE = `
    display:inline-block;padding:2px 8px;border-radius:20px;
    font-size:10px;font-weight:600;letter-spacing:.04em;
    background:rgba(45,212,160,0.1);color:var(--teal,#2dd4a0);
    border:1px solid rgba(45,212,160,0.25);margin:2px;
  `;

  // File type chips per analysis type
  const CHIPS = {
    default:    ['CSV', 'Excel', 'TSV'],
    grr:        ['CSV', 'Excel'],
    capa:       ['CSV', 'Excel', 'TSV'],
    spc:        ['CSV', 'Excel', 'CMM'],
    capability: ['CSV', 'Excel'],
    normality:  ['CSV', 'Excel', 'TSV'],
    report:     ['CSV', 'Excel', 'TSV'],
  };

  // SVG upload icon
  const UPLOAD_ICON = `
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" stroke-width="1.5"
         stroke-linecap="round" stroke-linejoin="round"
         style="color:var(--teal,#2dd4a0);opacity:.7;margin-bottom:8px">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="17 8 12 3 7 8"/>
      <line x1="12" y1="3" x2="12" y2="15"/>
    </svg>`;

  function upgradeZone(zone) {
    if (zone.dataset.upgraded) return;
    zone.dataset.upgraded = '1';

    // Preserve the hidden file input
    const input = zone.querySelector('input[type=file]');
    if (!input) return;

    // Detect which zone this is for chip selection
    const id = zone.id || '';
    const type = id.includes('grr') ? 'grr'
               : id.includes('cap') ? 'capability'
               : id.includes('norm') ? 'normality'
               : id.includes('spc') ? 'spc'
               : id.includes('capa') ? 'capa'
               : 'default';
    const chips = CHIPS[type] || CHIPS.default;

    // Current title text
    const titleEl = zone.querySelector('[id$="-upload-title"], [id$="-title"]');
    const titleText = titleEl ? titleEl.textContent : 'Drop file or click';

    // Style the zone
    Object.assign(zone.style, {
      border:        '1.5px dashed rgba(45,212,160,0.35)',
      borderRadius:  '10px',
      padding:       '18px 14px',
      textAlign:     'center',
      cursor:        'pointer',
      background:    'var(--bg3,#1e2535)',
      transition:    'border-color .2s, background .2s',
      position:      'relative',
    });

    // Build inner HTML (keep input)
    const chipsHTML = chips.map(c => `<span style="${CHIP_STYLE}">${c}</span>`).join('');
    const inner = document.createElement('div');
    inner.style.cssText = 'pointer-events:none';
    inner.innerHTML = `
      ${UPLOAD_ICON}
      <div style="font-size:13px;font-weight:600;color:var(--text,#f0f2f0);margin-bottom:6px"
           id="${titleEl ? titleEl.id : ''}">
        ${titleText}
      </div>
      <div style="margin-top:6px">${chipsHTML}</div>
    `;

    // Clear zone content except the input
    while (zone.firstChild) zone.removeChild(zone.firstChild);
    zone.appendChild(input);
    zone.appendChild(inner);

    // Hover effect
    zone.addEventListener('mouseenter', () => {
      zone.style.borderColor = 'rgba(45,212,160,.7)';
      zone.style.background  = 'rgba(45,212,160,.06)';
    });
    zone.addEventListener('mouseleave', () => {
      if (!zone.classList.contains('drag-over')) {
        zone.style.borderColor = 'rgba(45,212,160,.35)';
        zone.style.background  = 'var(--bg3,#1e2535)';
      }
    });
    zone.addEventListener('dragover', () => {
      zone.style.borderColor = 'rgba(45,212,160,.9)';
      zone.style.background  = 'rgba(45,212,160,.1)';
    });
    zone.addEventListener('dragleave', () => {
      zone.style.borderColor = 'rgba(45,212,160,.35)';
      zone.style.background  = 'var(--bg3,#1e2535)';
    });

    // Update title text when file is selected
    input.addEventListener('change', () => {
      if (input.files[0]) {
        const t = inner.querySelector('div[id]') || inner.querySelector('div');
        if (t) t.textContent = '✅ ' + input.files[0].name;
        zone.style.borderColor = 'rgba(52,217,128,.6)';
        zone.style.background  = 'rgba(52,217,128,.05)';
      }
    });
  }

  function upgradeAll() {
    document.querySelectorAll('.upload-zone').forEach(upgradeZone);
  }

  // Run on load + watch for dynamically shown sidebars
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', upgradeAll);
  } else {
    upgradeAll();
  }

  // Re-run when sidebar content changes (analysis switches)
  const sidebar = document.getElementById('sidebar');
  if (sidebar) {
    new MutationObserver(upgradeAll).observe(sidebar, {
      childList: true, subtree: true, attributes: true,
      attributeFilter: ['style', 'class'],
    });
  }
})();


/* ══════════════════════════════════════════════════════════════════
   PATCH 3 — PDF LOADING SPINNER
   Wraps the Generate PDF button with a proper loading state:
   spinner animation + progress text + prevents double-clicks.
   ══════════════════════════════════════════════════════════════════ */
(function pdfLoadingSpinner() {
  // Inject spinner CSS once
  const style = document.createElement('style');
  style.textContent = `
    .pdf-spinner {
      display: inline-block;
      width: 16px; height: 16px;
      border: 2px solid rgba(15,17,23,.3);
      border-top-color: #0f1117;
      border-radius: 50%;
      animation: pdf-spin .7s linear infinite;
      vertical-align: middle;
      margin-right: 8px;
      flex-shrink: 0;
    }
    @keyframes pdf-spin { to { transform: rotate(360deg); } }

    .pdf-progress-bar {
      width: 100%; height: 3px;
      background: rgba(15,17,23,.2);
      border-radius: 0 0 9px 9px;
      overflow: hidden;
      margin-top: 0;
    }
    .pdf-progress-fill {
      height: 100%;
      background: rgba(15,17,23,.4);
      border-radius: 9px;
      width: 0%;
      transition: width .4s ease;
    }
  `;
  document.head.appendChild(style);

  const STEPS = [
    { pct: 15, msg: 'Collecting analysis sessions…' },
    { pct: 35, msg: 'Rendering charts…' },
    { pct: 60, msg: 'Building PDF layout…' },
    { pct: 80, msg: 'Finalising document…' },
    { pct: 95, msg: 'Almost ready…' },
  ];

  function wrapPdfButton() {
    const btn = document.getElementById('run-report-btn');
    if (!btn || btn.dataset.spinnerPatched) return;
    btn.dataset.spinnerPatched = '1';

    // Wrap button in a container so we can add progress bar below it
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:relative;';
    btn.parentNode.insertBefore(wrapper, btn);
    wrapper.appendChild(btn);

    // Progress bar element
    const bar = document.createElement('div');
    bar.className = 'pdf-progress-bar';
    bar.style.display = 'none';
    const fill = document.createElement('div');
    fill.className = 'pdf-progress-fill';
    bar.appendChild(fill);
    wrapper.appendChild(bar);

    // Intercept the click
    btn.addEventListener('click', function patchedClick(e) {
      // Don't double-wrap if already loading
      if (btn.dataset.loading === '1') { e.stopImmediatePropagation(); return; }
      btn.dataset.loading = '1';

      // Immediately show loading state
      const originalText = btn.textContent;
      btn.disabled = true;
      btn.innerHTML = '<span class="pdf-spinner"></span> Generating PDF…';
      btn.style.opacity = '.85';
      bar.style.display = 'block';

      // Animate progress bar through steps
      let stepIndex = 0;
      const interval = setInterval(() => {
        if (stepIndex >= STEPS.length) { clearInterval(interval); return; }
        const step = STEPS[stepIndex++];
        fill.style.width = step.pct + '%';
        btn.innerHTML = `<span class="pdf-spinner"></span> ${step.msg}`;
      }, 900);

      // Watch for the download area to appear (PDF ready)
      const observer = new MutationObserver(() => {
        const dlArea = document.getElementById('report-download-area');
        if (dlArea && dlArea.style.display !== 'none') {
          clearInterval(interval);
          fill.style.width = '100%';
          setTimeout(() => {
            bar.style.display = 'none';
            fill.style.width = '0%';
            btn.disabled = false;
            btn.dataset.loading = '0';
            btn.textContent = originalText;
          }, 600);
          observer.disconnect();
        }
      });
      observer.observe(document.getElementById('sidebar') || document.body,
        { childList: true, subtree: true, attributes: true });

      // Safety timeout — restore after 90s no matter what
      setTimeout(() => {
        clearInterval(interval);
        observer.disconnect();
        bar.style.display = 'none';
        fill.style.width = '0%';
        if (btn.dataset.loading === '1') {
          btn.disabled = false;
          btn.dataset.loading = '0';
          btn.textContent = originalText;
        }
      }, 90000);
    }, true); // capture — fires before existing handler
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wrapPdfButton);
  } else {
    wrapPdfButton();
  }

  // Re-wire if sidebar re-renders
  document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
      new MutationObserver(wrapPdfButton).observe(sidebar,
        { childList: true, subtree: true });
    }
  });
})();


/* ══════════════════════════════════════════════════════════════════
   PATCH 4 — EMAIL CAPTURE (enhanced version)
   The base version in index.html already exists (_smShowEmailModal).
   This patch improves the modal UI to match StatMind's dark theme
   and adds a "remember" checkbox so power users aren't re-prompted.
   ══════════════════════════════════════════════════════════════════ */
(function enhanceEmailCapture() {
  const style = document.createElement('style');
  style.textContent = `
    #sm-email-modal-v2 {
      position: fixed; inset: 0;
      background: rgba(0,0,0,.72);
      display: flex; align-items: center; justify-content: center;
      z-index: 9999;
      backdrop-filter: blur(6px);
      -webkit-backdrop-filter: blur(6px);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
      animation: sm-fade-in .2s ease;
    }
    @keyframes sm-fade-in { from { opacity:0 } to { opacity:1 } }

    .sm-em-card {
      background: #111420;
      border: 1px solid rgba(255,255,255,.1);
      border-radius: 16px;
      padding: 32px 36px;
      max-width: 420px; width: 90%;
      box-shadow: 0 32px 80px rgba(0,0,0,.6);
      animation: sm-slide-up .22s cubic-bezier(.4,0,.2,1);
    }
    @keyframes sm-slide-up {
      from { transform: translateY(16px); opacity:0 }
      to   { transform: translateY(0);    opacity:1 }
    }

    .sm-em-icon {
      width: 48px; height: 48px; border-radius: 12px;
      background: linear-gradient(135deg,#6366f1,#818cf8);
      display: flex; align-items: center; justify-content: center;
      font-size: 22px; margin-bottom: 16px;
      box-shadow: 0 4px 20px rgba(99,102,241,.35);
    }

    .sm-em-title {
      font-size: 20px; font-weight: 700; color: #e8eaf0;
      margin-bottom: 6px; letter-spacing: -.02em;
    }

    .sm-em-sub {
      font-size: 13.5px; color: #8b8fa8; line-height: 1.6;
      margin-bottom: 20px;
    }

    .sm-em-input {
      width: 100%; box-sizing: border-box;
      padding: 11px 14px;
      background: #0f1117;
      border: 1px solid rgba(255,255,255,.1);
      border-radius: 9px;
      color: #e8eaf0; font-size: 14.5px;
      outline: none; transition: border-color .15s;
      margin-bottom: 8px;
    }
    .sm-em-input:focus { border-color: rgba(99,102,241,.6); }
    .sm-em-input::placeholder { color: #4b4f66; }

    .sm-em-err {
      color: #f87171; font-size: 12px; min-height: 16px;
      margin-bottom: 10px;
    }

    .sm-em-submit {
      width: 100%; padding: 12px;
      background: linear-gradient(135deg,#6366f1,#818cf8);
      color: #fff; border: none; border-radius: 9px;
      font-size: 14px; font-weight: 700; cursor: pointer;
      transition: opacity .15s, transform .1s;
      margin-bottom: 8px; letter-spacing: -.01em;
      display: flex; align-items: center; justify-content: center; gap: 8px;
    }
    .sm-em-submit:hover   { opacity: .92; }
    .sm-em-submit:active  { transform: scale(.98); }
    .sm-em-submit:disabled { opacity: .55; cursor: not-allowed; }

    .sm-em-skip {
      width: 100%; padding: 9px; background: transparent;
      border: none; color: #4b4f66; font-size: 12.5px;
      cursor: pointer; transition: color .15s;
    }
    .sm-em-skip:hover { color: #8b8fa8; }

    .sm-em-check {
      display: flex; align-items: center; gap: 8px;
      margin-bottom: 14px; cursor: pointer;
    }
    .sm-em-check input { accent-color: #6366f1; width: 14px; height: 14px; }
    .sm-em-check span  { font-size: 12px; color: #6b6f84; }

    .sm-em-privacy {
      font-size: 11px; color: #3d4166; text-align: center; margin-top: 10px;
    }
    .sm-em-privacy a { color: #6366f1; text-decoration: none; }
  `;
  document.head.appendChild(style);

  // Override the base _smShowEmailModal with our enhanced version
  window._smShowEmailModal = function (downloadUrl, filename) {
    const existing = document.getElementById('sm-email-modal-v2');
    if (existing) existing.remove();
    document.getElementById('sm-email-modal')?.remove();

    const modal = document.createElement('div');
    modal.id = 'sm-email-modal-v2';
    modal.innerHTML = `
      <div class="sm-em-card">
        <div class="sm-em-icon">📄</div>
        <div class="sm-em-title">Your report is ready</div>
        <div class="sm-em-sub">
          Drop your email to download. We send occasional quality engineering
          tips — no spam, unsubscribe any time.
        </div>
        <input class="sm-em-input" id="sm-em-input" type="email"
               placeholder="you@company.com" autocomplete="email"/>
        <div class="sm-em-err" id="sm-em-err"></div>
        <label class="sm-em-check">
          <input type="checkbox" id="sm-em-remember"/>
          <span>Don't ask me again this session</span>
        </label>
        <button class="sm-em-submit" id="sm-em-submit">
          Download PDF →
        </button>
        <button class="sm-em-skip" id="sm-em-skip">Skip for now</button>
        <div class="sm-em-privacy">
          No spam. <a href="/privacy" target="_blank">Privacy policy</a>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    const input  = modal.querySelector('#sm-em-input');
    const submit = modal.querySelector('#sm-em-submit');
    const skip   = modal.querySelector('#sm-em-skip');
    const err    = modal.querySelector('#sm-em-err');
    const remember = modal.querySelector('#sm-em-remember');

    input.focus();
    input.addEventListener('keydown', e => { if (e.key === 'Enter') submit.click(); });

    // Close on backdrop click
    modal.addEventListener('click', e => { if (e.target === modal) skip.click(); });

    submit.addEventListener('click', async () => {
      const email = input.value.trim();
      if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
        err.textContent = 'Please enter a valid email address.';
        input.focus(); return;
      }
      submit.disabled = true;
      submit.innerHTML = '<span style="width:14px;height:14px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;display:inline-block;animation:pdf-spin .7s linear infinite"></span> Saving…';
      err.textContent = '';

      try {
        await fetch('/api/v1/email/capture', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, source: 'pdf_download' }),
        });
      } catch (_) { /* non-blocking */ }

      if (remember.checked) {
        window._smEmailCaptured = true;
        sessionStorage.setItem('sm_email_captured', '1');
      }
      modal.remove();
      window._smTriggerDownload(downloadUrl, filename);
    });

    skip.addEventListener('click', () => {
      modal.remove();
      window._smTriggerDownload(downloadUrl, filename);
    });
  };
})();


/* ══════════════════════════════════════════════════════════════════
   PATCH 5 — MAGIC LINK AUTHENTICATION
   Adds a lightweight auth layer:
   - "Sign In" button in nav
   - Email → magic link flow (backend sends link)
   - JWT stored in sessionStorage
   - Soft gate: app still works without auth but shows
     "Sign in to save sessions & unlock team features" banner
   ══════════════════════════════════════════════════════════════════ */
(function magicLinkAuth() {
  // ── CSS ──────────────────────────────────────────────────────────
  const style = document.createElement('style');
  style.textContent = `
    #auth-modal {
      position: fixed; inset: 0;
      background: rgba(0,0,0,.72);
      display: none; align-items: center; justify-content: center;
      z-index: 9990;
      backdrop-filter: blur(6px);
      -webkit-backdrop-filter: blur(6px);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
    }
    #auth-modal.open { display: flex; }

    .auth-card {
      background: #111420;
      border: 1px solid rgba(255,255,255,.1);
      border-radius: 16px;
      padding: 36px 38px;
      max-width: 400px; width: 90%;
      box-shadow: 0 32px 80px rgba(0,0,0,.6);
      animation: sm-slide-up .22s cubic-bezier(.4,0,.2,1);
    }

    .auth-logo {
      width: 44px; height: 44px; border-radius: 11px;
      background: linear-gradient(135deg,#6366f1,#818cf8);
      display: flex; align-items: center; justify-content: center;
      font-size: 20px; font-weight: 800; color: #fff;
      margin-bottom: 18px;
      box-shadow: 0 4px 20px rgba(99,102,241,.35);
    }

    .auth-title {
      font-size: 22px; font-weight: 700; color: #e8eaf0;
      margin-bottom: 6px; letter-spacing: -.02em;
    }

    .auth-sub {
      font-size: 13px; color: #8b8fa8; line-height: 1.6;
      margin-bottom: 22px;
    }

    .auth-label {
      font-size: 11px; font-weight: 600; color: #6b6f84;
      text-transform: uppercase; letter-spacing: .06em;
      display: block; margin-bottom: 6px;
    }

    .auth-input {
      width: 100%; box-sizing: border-box;
      padding: 11px 14px;
      background: #0f1117;
      border: 1px solid rgba(255,255,255,.1);
      border-radius: 9px;
      color: #e8eaf0; font-size: 14.5px;
      outline: none; transition: border-color .15s;
      margin-bottom: 14px;
    }
    .auth-input:focus { border-color: rgba(99,102,241,.6); }
    .auth-input::placeholder { color: #4b4f66; }

    .auth-btn {
      width: 100%; padding: 12px;
      background: linear-gradient(135deg,#6366f1,#818cf8);
      color: #fff; border: none; border-radius: 9px;
      font-size: 14px; font-weight: 700; cursor: pointer;
      transition: opacity .15s, transform .1s;
      letter-spacing: -.01em; margin-bottom: 10px;
    }
    .auth-btn:hover   { opacity: .92; }
    .auth-btn:active  { transform: scale(.98); }
    .auth-btn:disabled { opacity: .5; cursor: not-allowed; }

    .auth-cancel {
      width: 100%; padding: 8px; background: transparent;
      border: none; color: #4b4f66; font-size: 12.5px; cursor: pointer;
    }
    .auth-cancel:hover { color: #8b8fa8; }

    .auth-err {
      color: #f87171; font-size: 12px; margin-bottom: 10px; min-height: 16px;
    }

    .auth-success {
      text-align: center; padding: 10px 0;
    }
    .auth-success-icon {
      font-size: 44px; margin-bottom: 12px;
    }
    .auth-success-title {
      font-size: 18px; font-weight: 700; color: #e8eaf0; margin-bottom: 6px;
    }
    .auth-success-sub {
      font-size: 13px; color: #8b8fa8; line-height: 1.6;
    }

    /* Nav sign-in button */
    #nav-signin-btn {
      display: flex; align-items: center; gap: 6px;
      padding: 5px 13px;
      background: rgba(99,102,241,.12);
      border: 1px solid rgba(99,102,241,.3);
      color: #818cf8;
      border-radius: 7px; font-size: 12px; font-weight: 600;
      cursor: pointer; transition: all .15s;
      font-family: inherit; white-space: nowrap;
    }
    #nav-signin-btn:hover {
      background: rgba(99,102,241,.2);
      border-color: rgba(99,102,241,.5);
    }

    /* Signed-in user pill */
    #nav-user-pill {
      display: none;
      align-items: center; gap: 7px;
      padding: 4px 10px 4px 5px;
      background: rgba(99,102,241,.1);
      border: 1px solid rgba(99,102,241,.25);
      border-radius: 20px; font-size: 12px; color: #818cf8; cursor: pointer;
    }
    #nav-user-pill:hover { background: rgba(99,102,241,.18); }
    .nav-user-avatar {
      width: 22px; height: 22px; border-radius: 50%;
      background: linear-gradient(135deg,#6366f1,#818cf8);
      display: flex; align-items: center; justify-content: center;
      font-size: 11px; font-weight: 700; color: #fff;
    }

    /* Soft-gate banner */
    #auth-banner {
      display: none;
      align-items: center; justify-content: space-between;
      padding: 9px 20px;
      background: rgba(99,102,241,.07);
      border-bottom: 1px solid rgba(99,102,241,.18);
      font-size: 12.5px; gap: 12px; flex-wrap: wrap;
    }
    #auth-banner.visible { display: flex; }
    .auth-banner-text { color: #8b8fa8; }
    .auth-banner-text strong { color: #818cf8; }
    .auth-banner-actions { display: flex; gap: 8px; align-items: center; }
    .auth-banner-btn {
      padding: 5px 14px;
      background: rgba(99,102,241,.15);
      border: 1px solid rgba(99,102,241,.3);
      color: #818cf8; border-radius: 6px;
      font-size: 12px; font-weight: 600; cursor: pointer;
      transition: all .15s; font-family: inherit;
    }
    .auth-banner-btn:hover { background: rgba(99,102,241,.25); }
    .auth-banner-dismiss {
      background: none; border: none; color: #4b4f66;
      font-size: 16px; cursor: pointer; padding: 0 4px;
    }
    .auth-banner-dismiss:hover { color: #8b8fa8; }
  `;
  document.head.appendChild(style);

  // ── State ─────────────────────────────────────────────────────────
  let _authUser = null;
  try {
    const raw = sessionStorage.getItem('sm_auth_user');
    if (raw) _authUser = JSON.parse(raw);
  } catch (_) {}

  function isSignedIn() { return !!_authUser; }

  function signIn(email, token) {
    _authUser = { email, token, initials: email.slice(0, 2).toUpperCase() };
    sessionStorage.setItem('sm_auth_user', JSON.stringify(_authUser));
    updateNavUI();
    hideBanner();
  }

  function signOut() {
    _authUser = null;
    sessionStorage.removeItem('sm_auth_user');
    updateNavUI();
  }

  // ── DOM helpers ───────────────────────────────────────────────────
  function updateNavUI() {
    const signinBtn = document.getElementById('nav-signin-btn');
    const userPill  = document.getElementById('nav-user-pill');
    if (!signinBtn || !userPill) return;

    if (isSignedIn()) {
      signinBtn.style.display = 'none';
      userPill.style.display  = 'flex';
      userPill.querySelector('.nav-user-avatar').textContent = _authUser.initials;
      userPill.querySelector('.nav-user-email').textContent  = _authUser.email;
    } else {
      signinBtn.style.display = 'flex';
      userPill.style.display  = 'none';
    }
  }

  function showBanner() {
    const b = document.getElementById('auth-banner');
    if (b && !isSignedIn() && !sessionStorage.getItem('sm_banner_dismissed')) {
      b.classList.add('visible');
    }
  }

  function hideBanner() {
    document.getElementById('auth-banner')?.classList.remove('visible');
  }

  // ── Modal ─────────────────────────────────────────────────────────
  function openAuthModal() {
    document.getElementById('auth-modal')?.classList.add('open');
    setTimeout(() => document.getElementById('auth-email-input')?.focus(), 50);
  }

  function closeAuthModal() {
    document.getElementById('auth-modal')?.classList.remove('open');
  }

  window.openAuthModal = openAuthModal;
  window.closeAuthModal = closeAuthModal;

  // ── Build DOM ─────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    // Auth modal
    const modal = document.createElement('div');
    modal.id = 'auth-modal';
    modal.innerHTML = `
      <div class="auth-card">
        <div id="auth-step-email">
          <div class="auth-logo">S</div>
          <div class="auth-title">Sign in to StatMind</div>
          <div class="auth-sub">
            Enter your work email. We'll send a magic link — no password needed.
          </div>
          <label class="auth-label" for="auth-email-input">Work email</label>
          <input class="auth-input" id="auth-email-input" type="email"
                 placeholder="you@company.com" autocomplete="email"/>
          <div class="auth-err" id="auth-err"></div>
          <button class="auth-btn" id="auth-send-btn">Send magic link →</button>
          <button class="auth-cancel" id="auth-cancel-btn">Continue without signing in</button>
        </div>
        <div id="auth-step-sent" style="display:none">
          <div class="auth-success">
            <div class="auth-success-icon">✉️</div>
            <div class="auth-success-title">Check your inbox</div>
            <div class="auth-success-sub">
              We sent a sign-in link to<br>
              <strong id="auth-sent-email" style="color:#818cf8"></strong><br><br>
              Click the link in the email to sign in.
              The link expires in 15 minutes.
            </div>
            <button class="auth-cancel" onclick="closeAuthModal()" style="margin-top:20px">
              Close
            </button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    // Close on backdrop
    modal.addEventListener('click', e => { if (e.target === modal) closeAuthModal(); });

    // Send magic link
    const sendBtn   = modal.querySelector('#auth-send-btn');
    const emailInput = modal.querySelector('#auth-email-input');
    const errDiv    = modal.querySelector('#auth-err');

    emailInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') sendBtn.click();
    });

    sendBtn.addEventListener('click', async () => {
      const email = emailInput.value.trim();
      if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
        errDiv.textContent = 'Please enter a valid email address.';
        emailInput.focus(); return;
      }
      sendBtn.disabled = true;
      sendBtn.textContent = 'Sending…';
      errDiv.textContent = '';

      try {
        const r = await fetch('/api/v1/auth/magic-link', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email }),
        });

        if (r.ok) {
          // Show success screen
          modal.querySelector('#auth-step-email').style.display = 'none';
          modal.querySelector('#auth-step-sent').style.display  = 'block';
          modal.querySelector('#auth-sent-email').textContent   = email;
        } else {
          // Backend not yet implemented — show "coming soon" gracefully
          errDiv.textContent = 'Magic link auth coming soon. Continue without signing in.';
          sendBtn.disabled = false;
          sendBtn.textContent = 'Send magic link →';
        }
      } catch (_) {
        // Backend endpoint not yet available — graceful fallback
        errDiv.textContent = 'Auth service unavailable. You can still use all features.';
        sendBtn.disabled = false;
        sendBtn.textContent = 'Send magic link →';
      }
    });

    modal.querySelector('#auth-cancel-btn').addEventListener('click', closeAuthModal);

    // ── Soft-gate banner ────────────────────────────────────────────
    const banner = document.createElement('div');
    banner.id = 'auth-banner';
    banner.innerHTML = `
      <div class="auth-banner-text">
        <strong>Sign in free</strong> to save sessions, get PDF history, and unlock team sharing.
      </div>
      <div class="auth-banner-actions">
        <button class="auth-banner-btn" onclick="openAuthModal()">Sign in with email →</button>
        <button class="auth-banner-dismiss" title="Dismiss" onclick="
          sessionStorage.setItem('sm_banner_dismissed','1');
          document.getElementById('auth-banner').classList.remove('visible');
        ">✕</button>
      </div>
    `;

    // Insert banner after context-bar
    const ctxBar = document.getElementById('context-bar');
    if (ctxBar) {
      ctxBar.parentNode.insertBefore(banner, ctxBar.nextSibling);
    } else {
      document.querySelector('.app-body')?.prepend(banner);
    }

    // ── Nav buttons ─────────────────────────────────────────────────
    const navRight = document.querySelector('.nav-right');
    if (navRight) {
      // Sign-in button
      const signinBtn = document.createElement('button');
      signinBtn.id = 'nav-signin-btn';
      signinBtn.innerHTML = `
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
          <polyline points="10 17 15 12 10 7"/>
          <line x1="15" y1="12" x2="3" y2="12"/>
        </svg>
        Sign in
      `;
      signinBtn.addEventListener('click', openAuthModal);

      // User pill (shown when signed in)
      const userPill = document.createElement('div');
      userPill.id = 'nav-user-pill';
      userPill.innerHTML = `
        <div class="nav-user-avatar">??</div>
        <span class="nav-user-email" style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span>
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      `;
      userPill.addEventListener('click', () => {
        if (confirm('Sign out of StatMind?')) signOut();
      });

      navRight.prepend(userPill);
      navRight.prepend(signinBtn);
    }

    // ── Check for magic link token in URL ──────────────────────────
    const params = new URLSearchParams(window.location.search);
    const token  = params.get('auth_token');
    const email  = params.get('email');
    if (token && email) {
      // Verify token with backend
      fetch('/api/v1/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, email }),
      }).then(r => {
        if (r.ok) {
          signIn(email, token);
          // Clean URL
          const url = new URL(window.location.href);
          url.searchParams.delete('auth_token');
          url.searchParams.delete('email');
          window.history.replaceState({}, '', url.toString());
          showToast?.('✅ Signed in as ' + email);
        }
      }).catch(() => { /* silent */ });
    }

    // ── Show banner after 8s if not signed in ─────────────────────
    setTimeout(() => {
      if (!isSignedIn() && !sessionStorage.getItem('sm_banner_dismissed')) {
        // Only show if user has loaded a file (engaged)
        if (window.globalFile || window.capData && Object.keys(window.capData).length) {
          showBanner();
        }
      }
    }, 8000);

    updateNavUI();
  });
})();
