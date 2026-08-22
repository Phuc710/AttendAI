/**
 * header.js — Shared Kiosk Header Logic
 * Auto-sets the active nav-tab based on current URL.
 * Also runs the shared clock update.
 */

(function () {
  // ── Auto-mark active tab based on URL ──────────────────
  const path = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-tab').forEach(tab => {
    const href = tab.getAttribute('href') || '';
    const tabPage = href.split('/').pop();
    if (tabPage === path) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });

  // ── Shared clock ───────────────────────────────────────
  function updateClock() {
    const clock = document.getElementById('clock');
    if (clock) {
      clock.textContent = new Date().toLocaleTimeString('vi-VN', { hour12: false });
    }
  }
  setInterval(updateClock, 1000);
  updateClock();
})();
