/**
 * StatMind Saved Sessions v1
 * ---------------------------------------------------------------------------
 * Extends the existing single-slot auto-save (session_persistence.js) into a
 * named, listable set of saved sessions, and replaces the bare "Sign out?"
 * profile click with a proper dropdown menu (Profile / Saved Sessions / Log out).
 *
 * Storage: browser localStorage only (per this device/browser). Sessions do NOT
 * sync across devices or browsers — this is disclosed to the user in the UI.
 *
 * Builds on window.SM_Session (save/load/restore/clear) from
 * session_persistence.js; if that isn't present it degrades gracefully.
 *
 * Add to index.html AFTER session_persistence.js and ui_patch_v2.js:
 *   <script src="/static/saved_sessions.js"></script>
 */
(function StatMindSavedSessions() {
  'use strict';

  const LIST_KEY = 'statmind_saved_sessions_v1';
  const MAX_SESSIONS = 20;          // cap to stay well under localStorage quota
  const MAX_TOTAL_BYTES = 4.5 * 1024 * 1024;

  // ── Storage helpers ────────────────────────────────────────────────
  function readList() {
    try {
      const raw = localStorage.getItem(LIST_KEY);
      if (!raw) return [];
      const arr = JSON.parse(raw);
      return Array.isArray(arr) ? arr : [];
    } catch (e) {
      return [];
    }
  }

  function writeList(list) {
    try {
      const json = JSON.stringify(list);
      if (json.length > MAX_TOTAL_BYTES) {
        toast('Saved sessions storage is full — delete some to free space.', true);
        return false;
      }
      localStorage.setItem(LIST_KEY, json);
      return true;
    } catch (e) {
      toast('Could not save — browser storage may be full or disabled.', true);
      return false;
    }
  }

  // Snapshot the CURRENT in-app analysis state (same shape SM_Session uses).
  function snapshotCurrent() {
    return {
      capData:     window.capData     || {},
      spcData:     window.spcData     || {},
      normData:    window.normData    || null,
      grrData:     window.grrData     || {},
      capaReports: window.capaReports || {},
      globalProcType: window.globalProcType || '',
      globalFileName: window.globalFile?.name || '',
      colNameMap:  window.colNameMap  || {},
      analysisHistory: window.analysisHistory || [],
    };
  }

  function currentHasData(s) {
    return (Object.keys(s.capData || {}).length > 0)
        || (Object.keys(s.spcData || {}).length > 0)
        || (s.normData != null)
        || (Object.keys(s.grrData || {}).length > 0);
  }

  function analysisCount(s) {
    return Object.keys(s.capData || {}).length
         + Object.keys(s.spcData || {}).length
         + (s.normData ? 1 : 0)
         + Object.keys(s.grrData || {}).length;
  }

  // ── Public-ish operations ──────────────────────────────────────────
  function saveCurrentAs(name) {
    const snap = snapshotCurrent();
    if (!currentHasData(snap)) {
      toast('Nothing to save yet — run an analysis first.', true);
      return false;
    }
    const list = readList();
    if (list.length >= MAX_SESSIONS) {
      toast(`You can keep up to ${MAX_SESSIONS} saved sessions. Delete one first.`, true);
      return false;
    }
    const entry = {
      id: 's_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7),
      name: (name || '').trim() || defaultName(snap),
      ts: Date.now(),
      fileName: snap.globalFileName || 'unknown file',
      count: analysisCount(snap),
      data: snap,
    };
    list.unshift(entry);
    if (writeList(list)) {
      toast('💾 Session saved: ' + entry.name);
      return true;
    }
    return false;
  }

  function defaultName(snap) {
    const base = snap.globalFileName ? snap.globalFileName.replace(/\.[^.]+$/, '') : 'Session';
    const d = new Date();
    const stamp = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
                + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    return `${base} — ${stamp}`;
  }

  function deleteSession(id) {
    const list = readList().filter(s => s.id !== id);
    writeList(list);
  }

  function restoreSession(id) {
    const entry = readList().find(s => s.id === id);
    if (!entry) { toast('Session not found.', true); return; }
    if (window.SM_Session && typeof window.SM_Session.restore === 'function') {
      window.SM_Session.restore(entry.data);
      toast('✅ Restored: ' + entry.name);
    } else {
      toast('Restore engine unavailable.', true);
    }
  }

  // ── Excel dashboard export (feat/session-excel-export) ─────────────────
  // Sends the saved snapshot to the backend, which builds a formatted
  // multi-sheet workbook (dashboard + per-analysis sheets with native Excel
  // charts) entirely in memory and streams it back.
  async function exportSessionXlsx(id, btn) {
    const entry = readList().find(s => s.id === id);
    if (!entry) { toast('Session not found.', true); return; }
    const orig = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
      const API = window.API || '';
      const r = await fetch(`${API}/api/v1/export/xlsx`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session: entry.data, name: entry.name }),
      });
      if (!r.ok) {
        let msg = 'Export failed.';
        try { msg = (await r.json()).detail || msg; } catch (_) {}
        throw new Error(msg);
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = (entry.name || 'statmind_session').replace(/[^\w .\-]/g, '') + '.xlsx';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
      toast('📊 Excel dashboard downloaded');
    } catch (e) {
      toast(e.message || 'Export failed.', true);
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = orig; }
    }
  }

  // ── Toast (reuse app toast if present) ─────────────────────────────
  function toast(msg, isErr) {
    if (typeof window.showToast === 'function') { window.showToast(msg, !!isErr); return; }
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);'
      + 'background:#111420;border:1px solid rgba(99,102,241,.35);border-radius:10px;'
      + 'padding:11px 16px;font-family:var(--font,system-ui,sans-serif);font-size:13px;'
      + 'color:#e8eaf0;z-index:9000;box-shadow:0 8px 32px rgba(0,0,0,.5)';
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 4000);
  }

  function fmtAge(ts) {
    const mins = Math.round((Date.now() - ts) / 60000);
    if (mins < 2) return 'just now';
    if (mins < 60) return `${mins} min ago`;
    const h = Math.round(mins / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.round(h / 24)}d ago`;
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── Saved Sessions modal ───────────────────────────────────────────
  function openSavedSessions() {
    closeProfileMenu();
    const list = readList();
    const existing = document.getElementById('sm-sessions-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'sm-sessions-modal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9500;'
      + 'display:flex;align-items:center;justify-content:center;font-family:var(--font,system-ui,sans-serif)';

    const rows = list.length ? list.map(s => `
      <div class="sm-sess-row" data-id="${s.id}"
           style="display:flex;align-items:center;gap:12px;padding:12px 14px;
                  border:1px solid rgba(255,255,255,.07);border-radius:10px;margin-bottom:8px;background:#161b24">
        <div style="font-size:20px">💾</div>
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;color:#e8eaf0;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(s.name)}</div>
          <div style="color:#8b8fa8;font-size:12px">${s.count} result${s.count !== 1 ? 's' : ''} · ${escapeHtml(s.fileName)} · ${fmtAge(s.ts)}</div>
        </div>
        <button class="sm-sess-xlsx" data-id="${s.id}" title="Download as Excel dashboard"
          style="background:rgba(56,140,255,.12);border:1px solid rgba(56,140,255,.35);color:#6aa9ff;
                 padding:6px 12px;border-radius:7px;font-size:12px;font-weight:600;cursor:pointer;font-family:var(--font,system-ui,sans-serif)">Excel</button>
        <button class="sm-sess-restore" data-id="${s.id}"
          style="background:rgba(45,212,160,.15);border:1px solid rgba(45,212,160,.4);color:#2dd4a0;
                 padding:6px 12px;border-radius:7px;font-size:12px;font-weight:600;cursor:pointer;font-family:var(--font,system-ui,sans-serif)">Restore</button>
        <button class="sm-sess-delete" data-id="${s.id}" title="Delete"
          style="background:none;border:none;color:#6b6f85;font-size:16px;cursor:pointer;padding:4px">🗑</button>
      </div>`).join('')
      : `<div style="text-align:center;color:#8b8fa8;padding:32px 12px;font-size:14px">
           No saved sessions yet.<br>Run an analysis, then click <strong>Save current session</strong>.
         </div>`;

    modal.innerHTML = `
      <div style="background:#0f1117;border:1px solid rgba(255,255,255,.1);border-radius:16px;
                  width:90%;max-width:480px;max-height:80vh;display:flex;flex-direction:column;
                  box-shadow:0 24px 64px rgba(0,0,0,.6)">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:18px 20px;border-bottom:1px solid rgba(255,255,255,.08)">
          <div style="font-weight:700;color:#f0f2f0;font-size:17px">Saved Sessions</div>
          <button id="sm-sess-close" style="background:none;border:none;color:#8b8fa8;font-size:22px;cursor:pointer;line-height:1">×</button>
        </div>
        <div style="padding:16px 20px;overflow-y:auto;flex:1">
          <button id="sm-sess-save-current"
            style="width:100%;background:rgba(45,212,160,.15);border:1px solid rgba(45,212,160,.4);
                   color:#2dd4a0;padding:10px;border-radius:9px;font-size:13px;font-weight:600;cursor:pointer;
                   margin-bottom:16px;font-family:var(--font,system-ui,sans-serif)">+ Save current session</button>
          ${rows}
        </div>
        <div style="padding:10px 20px;border-top:1px solid rgba(255,255,255,.08);color:#6b6f85;font-size:11px;text-align:center">
          Saved in this browser only — sessions don't sync across devices.
        </div>
      </div>`;

    document.body.appendChild(modal);

    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    modal.querySelector('#sm-sess-close').addEventListener('click', () => modal.remove());
    modal.querySelector('#sm-sess-save-current').addEventListener('click', () => {
      const name = prompt('Name this session:', defaultName(snapshotCurrent()));
      if (name === null) return;             // cancelled
      if (saveCurrentAs(name)) { modal.remove(); openSavedSessions(); }
    });
    modal.querySelectorAll('.sm-sess-restore').forEach(btn => {
      btn.addEventListener('click', () => { restoreSession(btn.dataset.id); modal.remove(); });
    });
    modal.querySelectorAll('.sm-sess-xlsx').forEach(btn => {
      btn.addEventListener('click', () => { exportSessionXlsx(btn.dataset.id, btn); });
    });
    modal.querySelectorAll('.sm-sess-delete').forEach(btn => {
      btn.addEventListener('click', () => {
        if (confirm('Delete this saved session? This cannot be undone.')) {
          deleteSession(btn.dataset.id); modal.remove(); openSavedSessions();
        }
      });
    });
  }

  // ── Profile modal (simple, read-only) ──────────────────────────────
  function openProfile() {
    closeProfileMenu();
    const email = (window.SM_currentEmail || localStorage.getItem('statmind_user_email') || '').trim();
    const modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9500;'
      + 'display:flex;align-items:center;justify-content:center;font-family:var(--font,system-ui,sans-serif)';
    modal.innerHTML = `
      <div style="background:#0f1117;border:1px solid rgba(255,255,255,.1);border-radius:16px;
                  width:90%;max-width:380px;box-shadow:0 24px 64px rgba(0,0,0,.6)">
        <div style="display:flex;align-items:center;justify-content:space-between;padding:18px 20px;border-bottom:1px solid rgba(255,255,255,.08)">
          <div style="font-weight:700;color:#f0f2f0;font-size:17px">Profile</div>
          <button class="sm-pf-close" style="background:none;border:none;color:#8b8fa8;font-size:22px;cursor:pointer;line-height:1">×</button>
        </div>
        <div style="padding:22px 20px">
          <div style="display:flex;align-items:center;gap:14px;margin-bottom:8px">
            <div style="width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,#2dd4a0,#0fb888);
                        display:flex;align-items:center;justify-content:center;color:#0f1117;font-weight:800;font-size:18px">
              ${escapeHtml((email[0] || '?').toUpperCase())}
            </div>
            <div style="min-width:0">
              <div style="color:#e8eaf0;font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(email || 'Signed in')}</div>
              <div style="color:#8b8fa8;font-size:12px">StatMind account</div>
            </div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    modal.querySelector('.sm-pf-close').addEventListener('click', () => modal.remove());
  }

  // ── Profile dropdown menu (replaces the bare confirm() ) ───────────
  function closeProfileMenu() {
    document.getElementById('sm-profile-menu')?.remove();
  }

  function openProfileMenu(anchorEl) {
    closeProfileMenu();
    const menu = document.createElement('div');
    menu.id = 'sm-profile-menu';
    menu.style.cssText = 'position:absolute;z-index:9600;background:#161b24;border:1px solid rgba(255,255,255,.12);'
      + 'border-radius:10px;min-width:180px;padding:6px;box-shadow:0 12px 32px rgba(0,0,0,.5);'
      + 'font-family:var(--font,system-ui,sans-serif)';

    const items = [
      { label: 'Profile',        icon: '👤', fn: openProfile },
      { label: 'Saved Sessions', icon: '💾', fn: openSavedSessions },
      { sep: true },
      { label: 'Log out',        icon: '↩', fn: doSignOut, danger: true },
    ];
    items.forEach(it => {
      if (it.sep) {
        const d = document.createElement('div');
        d.style.cssText = 'height:1px;background:rgba(255,255,255,.08);margin:5px 4px';
        menu.appendChild(d);
        return;
      }
      const b = document.createElement('button');
      b.innerHTML = `<span style="width:18px;display:inline-block">${it.icon}</span> ${it.label}`;
      b.style.cssText = 'display:block;width:100%;text-align:left;background:none;border:none;'
        + 'color:' + (it.danger ? '#f87171' : '#e8eaf0') + ';padding:9px 10px;border-radius:7px;'
        + 'font-size:13px;cursor:pointer;font-family:var(--font,system-ui,sans-serif)';
      b.addEventListener('mouseenter', () => b.style.background = 'rgba(255,255,255,.06)');
      b.addEventListener('mouseleave', () => b.style.background = 'none');
      b.addEventListener('click', () => { closeProfileMenu(); it.fn(); });
      menu.appendChild(b);
    });

    // Position under the anchor (the user pill).
    const r = anchorEl.getBoundingClientRect();
    menu.style.top = (r.bottom + window.scrollY + 6) + 'px';
    menu.style.left = (r.right + window.scrollX - 180) + 'px';
    document.body.appendChild(menu);

    // Close on outside click
    setTimeout(() => {
      document.addEventListener('click', function onDoc(e) {
        if (!menu.contains(e.target) && !anchorEl.contains(e.target)) {
          closeProfileMenu();
          document.removeEventListener('click', onDoc);
        }
      });
    }, 0);
  }

  function doSignOut() {
    if (!confirm('Sign out of StatMind?')) return;
    if (typeof window._smAuthSignOut === 'function') { window._smAuthSignOut(); return; }
    if (typeof window.signOut === 'function') { window.signOut(); return; }
    // Fallback: clear auth and reload
    try {
      localStorage.removeItem('statmind_auth_token');
      localStorage.removeItem('statmind_user_email');
    } catch (e) {}
    location.reload();
  }

  // ── Hook the existing user pill: replace its confirm() click ───────
  function attachToUserPill() {
    const pill = document.getElementById('nav-user-pill');
    if (!pill || pill.dataset.smMenuAttached) return;
    pill.dataset.smMenuAttached = '1';
    // Replace the original click (bare confirm) with the dropdown menu.
    const fresh = pill.cloneNode(true);     // strips old listeners
    pill.parentNode.replaceChild(fresh, pill);
    fresh.addEventListener('click', (e) => {
      e.stopPropagation();
      if (document.getElementById('sm-profile-menu')) { closeProfileMenu(); return; }
      openProfileMenu(fresh);
    });
    fresh.style.cursor = 'pointer';
  }

  // The pill is created by ui_patch_v2.js after auth resolves; it may not exist
  // at DOMContentLoaded. Poll briefly until it appears, then attach.
  function watchForPill() {
    let tries = 0;
    const iv = setInterval(() => {
      attachToUserPill();
      if (document.getElementById('nav-user-pill')?.dataset.smMenuAttached || ++tries > 40) {
        clearInterval(iv);
      }
    }, 250);
  }

  document.addEventListener('DOMContentLoaded', watchForPill);
  // Also re-attach if auth state flips later (sign-in after load).
  window.SM_SavedSessions = { open: openSavedSessions, saveCurrentAs, attachToUserPill };
})();
