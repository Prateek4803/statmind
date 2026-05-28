/**
 * StatMind Onboarding + Loading State Patch
 * - Replaces blank first-time screen with guided onboarding card
 * - Fixes "Checking API..." cold start impression
 * - Adds skeleton loading state
 */

(function statmindOnboarding() {

  // ── 1. Fix API status — show nothing until confirmed connected ─────────────
  // Override the checking state to be invisible until resolved
  const origSetStatus = window.setStatus;
  window.setStatus = function(s, t) {
    const dot  = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    const mdot = document.getElementById('mob-status-dot');
    const mtxt = document.getElementById('mob-status-text');

    if (s === 'ok') {
      // Connected — show briefly then hide after 3s
      [dot, text, mdot, mtxt].forEach(el => el && (el.style.display = ''));
      if (origSetStatus) origSetStatus(s, t);
      setTimeout(() => {
        [dot, text, mdot, mtxt].forEach(el => el && (el.style.display = 'none'));
      }, 3000);
    } else if (s === 'err') {
      // Error — show red indicator
      [dot, text, mdot, mtxt].forEach(el => el && (el.style.display = ''));
      if (origSetStatus) origSetStatus(s, t);
    }
    // 'checking' state — stay hidden (already hidden by style="display:none")
  };

  // ── 2. Onboarding card for first-time visitors ────────────────────────────
  const ONBOARDING_CSS = `
    #sm-onboarding {
      position: absolute;
      top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      background: #111420;
      border: 1px solid rgba(99,102,241,.25);
      border-radius: 16px;
      padding: 32px 36px;
      max-width: 480px; width: 90%;
      text-align: center;
      z-index: 100;
      box-shadow: 0 24px 60px rgba(0,0,0,.5);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
    }
    #sm-onboarding h2 {
      font-size: 22px; font-weight: 700;
      color: #e8eaf0; margin: 0 0 8px;
      letter-spacing: -.02em;
    }
    #sm-onboarding p {
      font-size: 14px; color: #8b8fa8;
      line-height: 1.6; margin: 0 0 24px;
    }
    .sm-ob-steps {
      display: flex; gap: 8px;
      margin-bottom: 24px;
      text-align: left;
    }
    .sm-ob-step {
      flex: 1;
      background: rgba(99,102,241,.08);
      border: 1px solid rgba(99,102,241,.2);
      border-radius: 10px;
      padding: 12px 10px;
    }
    .sm-ob-step-num {
      font-size: 11px; font-weight: 700;
      color: #6366f1; margin-bottom: 4px;
      text-transform: uppercase; letter-spacing: .05em;
    }
    .sm-ob-step-text {
      font-size: 12px; color: #c8cad8; line-height: 1.4;
    }
    .sm-ob-btn {
      display: inline-block;
      background: linear-gradient(135deg,#6366f1,#818cf8);
      color: #fff; border: none; border-radius: 9px;
      padding: 12px 28px; font-size: 14px; font-weight: 700;
      cursor: pointer; transition: opacity .15s;
      font-family: inherit; margin-right: 8px;
    }
    .sm-ob-btn:hover { opacity: .9; }
    .sm-ob-sample {
      background: rgba(45,212,160,.1);
      border: 1px solid rgba(45,212,160,.3);
      color: #2dd4a0;
      display: inline-block; border-radius: 9px;
      padding: 12px 20px; font-size: 13px; font-weight: 600;
      cursor: pointer; transition: all .15s; font-family: inherit;
    }
    .sm-ob-sample:hover { background: rgba(45,212,160,.18); }
    .sm-ob-dismiss {
      display: block; margin-top: 14px;
      background: none; border: none;
      color: #4b4f66; font-size: 12px; cursor: pointer;
      font-family: inherit;
    }
    .sm-ob-dismiss:hover { color: #8b8fa8; }
  `;

  function showOnboarding() {
    // Don't show if user has data or has dismissed
    if (sessionStorage.getItem('sm_ob_dismissed')) return;
    if (window.globalFile || (window.capData && Object.keys(window.capData).length > 0)) return;

    const style = document.createElement('style');
    style.textContent = ONBOARDING_CSS;
    document.head.appendChild(style);

    const card = document.createElement('div');
    card.id = 'sm-onboarding';
    card.innerHTML = `
      <div style="font-size:36px;margin-bottom:12px">📊</div>
      <h2>Welcome to StatMind</h2>
      <p>Free process statistics for quality engineers.<br>
         Upload your data or try a sample dataset to get started.</p>
      <div class="sm-ob-steps">
        <div class="sm-ob-step">
          <div class="sm-ob-step-num">Step 1</div>
          <div class="sm-ob-step-text">Upload a CSV or Excel file with measurement data</div>
        </div>
        <div class="sm-ob-step">
          <div class="sm-ob-step-num">Step 2</div>
          <div class="sm-ob-step-text">Select your analysis: Capability, SPC, GRR, or CAPA</div>
        </div>
        <div class="sm-ob-step">
          <div class="sm-ob-step-num">Step 3</div>
          <div class="sm-ob-step-text">Get results instantly and export a PDF report</div>
        </div>
      </div>
      <button class="sm-ob-btn" id="sm-ob-upload">Upload My Data</button>
      <button class="sm-ob-sample" id="sm-ob-sample">Try Sample Dataset</button>
      <button class="sm-ob-dismiss" id="sm-ob-dismiss">I know how to use this, skip intro</button>
    `;

    // Insert into welcome screen or main content area
    const welcome = document.getElementById('welcome-screen') ||
                    document.querySelector('.welcome-screen') ||
                    document.querySelector('.app-body');
    if (welcome) {
      welcome.style.position = 'relative';
      welcome.appendChild(card);
    } else {
      document.body.appendChild(card);
    }

    // Wire buttons
    document.getElementById('sm-ob-upload')?.addEventListener('click', () => {
      card.remove();
      sessionStorage.setItem('sm_ob_dismissed', '1');
      // Trigger file input
      document.querySelector('input[type=file]')?.click();
    });

    document.getElementById('sm-ob-sample')?.addEventListener('click', () => {
      card.remove();
      sessionStorage.setItem('sm_ob_dismissed', '1');
      // Trigger sample dataset load if function exists
      if (typeof loadSampleDataset === 'function') loadSampleDataset();
      else if (typeof loadDemoData === 'function') loadDemoData();
      else {
        // Find and click the sample dataset button
        const sampleBtn = Array.from(document.querySelectorAll('button'))
          .find(b => b.textContent.toLowerCase().includes('sample'));
        if (sampleBtn) sampleBtn.click();
      }
    });

    document.getElementById('sm-ob-dismiss')?.addEventListener('click', () => {
      card.remove();
      sessionStorage.setItem('sm_ob_dismissed', '1');
    });
  }

  // Show after a short delay to let the app load
  document.addEventListener('DOMContentLoaded', () => {
    setTimeout(showOnboarding, 800);
  });

})();
