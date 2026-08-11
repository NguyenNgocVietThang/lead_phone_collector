/**
 * ui/static/js/main.js — Frontend utilities cho Lead Phone Collector
 */

// ── Toast notification system ─────────────────────────────────────────────
function showToast(message, type = 'success', duration = 2500) {
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    requestAnimationFrame(() => toast.classList.add('toast--show'));
  });

  setTimeout(() => {
    toast.classList.remove('toast--show');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ── Auto-dismiss flash messages ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const flashes = document.querySelectorAll('.flash');
  flashes.forEach((flash) => {
    setTimeout(() => {
      flash.style.transition = 'opacity 0.4s ease, max-height 0.4s ease';
      flash.style.opacity = '0';
      flash.style.maxHeight = '0';
      flash.style.overflow = 'hidden';
      setTimeout(() => flash.remove(), 450);
    }, 5000);
  });
});

// ── Format phone display ──────────────────────────────────────────────────
function formatPhone(phone) {
  if (!phone || phone.length !== 10) return phone;
  return `${phone.slice(0, 4)} ${phone.slice(4, 7)} ${phone.slice(7)}`;
}

// ── Copy to clipboard ─────────────────────────────────────────────────────
function copyPhone(phone) {
  navigator.clipboard.writeText(phone)
    .then(() => showToast(`Đã copy: ${formatPhone(phone)}`))
    .catch(() => {
      // Fallback cho trình duyệt cũ
      const el = document.createElement('textarea');
      el.value = phone;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      showToast(`Đã copy: ${phone}`);
    });
}

// ── Lead status update ────────────────────────────────────────────────────
async function updateStatus(leadId, status) {
  try {
    const resp = await fetch(`/api/leads/${leadId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const data = await resp.json();
    if (data.ok) {
      const row = document.querySelector(`tr[data-lead-id="${leadId}"]`);
      if (row) {
        row.className = row.className.replace(/status-\w+/, `status-${status}`);
      }

      const labels = {
        'new': 'Mới', 'contacted': 'Đã gọi',
        'qualified': 'Tiềm năng', 'rejected': 'Loại',
      };
      showToast(`Đã cập nhật: ${labels[status] || status}`);
    } else {
      showToast('Lỗi cập nhật', 'error');
    }
  } catch (e) {
    console.error('updateStatus error:', e);
    showToast('Lỗi kết nối', 'error');
  }
}

// ── Form loading state ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', function () {
      const btn = this.querySelector('button[type="submit"]');
      if (!btn) return;
      btn.disabled = true;
      const originalHTML = btn.innerHTML;
      btn.innerHTML = '<span class="spinner"></span> Đang xử lý...';

      // Reset sau 60s phòng trường hợp lỗi
      setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = originalHTML;
      }, 60_000);
    });
  });
});

// ── Keyboard shortcut: Ctrl+K = focus search ──────────────────────────────
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const search = document.querySelector('input[name="search"]');
    if (search) { search.focus(); search.select(); }
  }
});

// ── Live stats refresh (every 60s nếu đang ở dashboard) ─────────────────
if (window.location.pathname === '/') {
  setInterval(async () => {
    try {
      const resp = await fetch('/api/stats');
      const stats = await resp.json();
      const totalEl = document.querySelector('.stat-card--primary .stat-card__value');
      const todayEl = document.querySelector('.stat-card--success .stat-card__value');
      if (totalEl) totalEl.textContent = stats.total;
      if (todayEl) todayEl.textContent = stats.today;
    } catch (e) { /* Bỏ qua lỗi network */ }
  }, 60_000);
}
