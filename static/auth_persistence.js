/**
 * StatMind Auth Persistence Patch
 * Adds to ui_patch_v2.js — replaces sessionStorage with localStorage for JWT
 * so signing in on one tab keeps you signed in across all tabs and page reloads.
 *
 * Also auto-restores login state on page load.
 */

(function patchAuthPersistence() {
  // Wait for the main auth module to load
  function applyPatch() {
    // Override signIn to use localStorage instead of sessionStorage
    const _origSignIn = window._smAuthSignIn;

    window._smAuthSignIn = function(email, token) {
      const user = { email, token, initials: email.slice(0, 2).toUpperCase() };
      // Store in BOTH localStorage (cross-tab) and memory
      try {
        localStorage.setItem('sm_auth_user', JSON.stringify(user));
        localStorage.setItem('sm_auth_ts', Date.now().toString());
      } catch(e) {}
      // Also update the module state via the existing signIn
      if (_origSignIn) _origSignIn(email, token);
    };

    // Override signOut to clear localStorage
    const _origSignOut = window._smAuthSignOut;
    window._smAuthSignOut = function() {
      try {
        localStorage.removeItem('sm_auth_user');
        localStorage.removeItem('sm_auth_ts');
      } catch(e) {}
      if (_origSignOut) _origSignOut();
    };

    // Auto-restore from localStorage on page load
    try {
      const raw = localStorage.getItem('sm_auth_user');
      const ts  = parseInt(localStorage.getItem('sm_auth_ts') || '0');
      const AGE = 7 * 24 * 60 * 60 * 1000; // 7 days

      if (raw && (Date.now() - ts) < AGE) {
        const user = JSON.parse(raw);

        // Verify token is still valid with backend
        fetch('/api/v1/auth/me', {
          headers: { 'Authorization': `Bearer ${user.token}` }
        }).then(r => {
          if (r.ok) {
            // Token still valid — restore session
            window._smAuthUser = user;

            // Update nav UI
            const signinBtn = document.getElementById('nav-signin-btn');
            const userPill  = document.getElementById('nav-user-pill');
            if (signinBtn) signinBtn.style.display = 'none';
            if (userPill) {
              userPill.style.display = 'flex';
              const avatar = userPill.querySelector('.nav-user-avatar');
              const emailEl = userPill.querySelector('.nav-user-email');
              if (avatar) avatar.textContent = user.initials;
              if (emailEl) emailEl.textContent = user.email;
            }

            // Hide auth banner
            document.getElementById('auth-banner')?.classList.remove('visible');

          } else {
            // Token expired — clear storage
            localStorage.removeItem('sm_auth_user');
            localStorage.removeItem('sm_auth_ts');
          }
        }).catch(() => {
          // Network error — restore anyway (offline tolerance)
          window._smAuthUser = user;
        });
      }
    } catch(e) {}

    // Listen for storage events (another tab signed in/out)
    window.addEventListener('storage', function(e) {
      if (e.key === 'sm_auth_user') {
        if (e.newValue) {
          // Another tab signed in
          try {
            const user = JSON.parse(e.newValue);
            window._smAuthUser = user;
            const signinBtn = document.getElementById('nav-signin-btn');
            const userPill  = document.getElementById('nav-user-pill');
            if (signinBtn) signinBtn.style.display = 'none';
            if (userPill) {
              userPill.style.display = 'flex';
              const avatar = userPill.querySelector('.nav-user-avatar');
              const emailEl = userPill.querySelector('.nav-user-email');
              if (avatar) avatar.textContent = user.initials;
              if (emailEl) emailEl.textContent = user.email;
            }
          } catch(e) {}
        } else {
          // Another tab signed out
          window._smAuthUser = null;
          const signinBtn = document.getElementById('nav-signin-btn');
          const userPill  = document.getElementById('nav-user-pill');
          if (signinBtn) signinBtn.style.display = 'flex';
          if (userPill)  userPill.style.display  = 'none';
        }
      }
    });
  }

  // Apply after DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyPatch);
  } else {
    applyPatch();
  }
})();
