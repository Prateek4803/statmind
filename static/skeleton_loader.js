/**
 * StatMind Skeleton Loading State
 * Replaces blank load screen with professional skeleton UI
 * Handles cold-start gracefully
 */

(function skeletonLoader() {
  const CSS = `
    .sm-skeleton {
      background: linear-gradient(90deg,
        rgba(30,37,53,0) 0%,
        rgba(99,102,241,0.08) 50%,
        rgba(30,37,53,0) 100%);
      background-size: 200% 100%;
      animation: sm-shimmer 1.5s infinite;
      border-radius: 6px;
    }
    @keyframes sm-shimmer {
      0%   { background-position: -200% 0; }
      100% { background-position:  200% 0; }
    }

    #sm-loading-overlay {
      position: fixed; inset: 0;
      background: #0b0d14;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      z-index: 9999;
      gap: 12px;
      transition: opacity .4s ease;
    }
    #sm-loading-overlay.fade-out {
      opacity: 0; pointer-events: none;
    }

    .sm-load-logo {
      width: 52px; height: 52px;
      background: linear-gradient(135deg,#6366f1,#818cf8);
      border-radius: 14px;
      display: flex; align-items: center; justify-content: center;
      font-size: 24px; font-weight: 800; color: #fff;
      margin-bottom: 8px;
      box-shadow: 0 8px 32px rgba(99,102,241,.4);
    }

    .sm-load-title {
      font-size: 20px; font-weight: 700;
      color: #e8eaf0; letter-spacing: -.02em;
      font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    }

    .sm-load-sub {
      font-size: 13px; color: #4b4f66;
      font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    }

    .sm-load-bar {
      width: 200px; height: 3px;
      background: rgba(99,102,241,.15);
      border-radius: 9px;
      overflow: hidden;
      margin-top: 12px;
    }
    .sm-load-bar-fill {
      height: 100%;
      background: linear-gradient(90deg,#6366f1,#818cf8);
      border-radius: 9px;
      width: 0%;
      transition: width .6s ease;
    }

    /* App skeleton shown while content loads */
    .sm-app-skeleton {
      display: none;
      padding: 24px;
      gap: 16px;
      flex-direction: column;
    }
    .sm-app-skeleton.visible { display: flex; }
    .sm-skel-bar { height: 14px; background: rgba(255,255,255,.05); border-radius: 4px; }
    .sm-skel-card {
      background: rgba(255,255,255,.03);
      border: 1px solid rgba(255,255,255,.06);
      border-radius: 10px;
      padding: 20px; display: flex; flex-direction: column; gap: 10px;
    }
  `;

  // Inject CSS
  const style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);

  // Create loading overlay
  const overlay = document.createElement('div');
  overlay.id = 'sm-loading-overlay';
  overlay.innerHTML = `
    <div class="sm-load-logo">S</div>
    <div class="sm-load-title">StatMind</div>
    <div class="sm-load-sub">Loading statistical engine…</div>
    <div class="sm-load-bar">
      <div class="sm-load-bar-fill" id="sm-load-fill"></div>
    </div>
  `;
  document.body.appendChild(overlay);

  // Animate progress bar
  const fill = document.getElementById('sm-load-fill');
  let progress = 0;
  const interval = setInterval(() => {
    progress = Math.min(progress + Math.random() * 15, 85);
    if (fill) fill.style.width = progress + '%';
  }, 200);

  // Hide overlay when app is ready
  function hideOverlay() {
    clearInterval(interval);
    if (fill) fill.style.width = '100%';
    setTimeout(() => {
      overlay.classList.add('fade-out');
      setTimeout(() => overlay.remove(), 400);
    }, 300);
  }

  // Watch for app readiness — health check passes = app ready
  let attempts = 0;
  const checkReady = setInterval(() => {
    attempts++;
    // Check if main app content has loaded
    const sidebar = document.getElementById('sidebar');
    const welcome = document.getElementById('welcome-screen');
    const appBody = document.querySelector('.app-body');

    if (sidebar || welcome || appBody || attempts > 20) {
      clearInterval(checkReady);
      hideOverlay();
    }
  }, 300);

  // Also hide on DOMContentLoaded as fallback
  window.addEventListener('load', () => {
    setTimeout(hideOverlay, 500);
  });

})();
