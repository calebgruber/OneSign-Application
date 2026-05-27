/**
 * admin.js — shared helpers for OneSign admin UI
 */

/**
 * HTML-escape a string for safe innerHTML insertion.
 * @param {string} str
 * @returns {string}
 */
function escHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Format an ISO datetime string.
 * @param {string} dateStr  — ISO or MySQL datetime
 * @param {boolean} includeTime
 * @returns {string}
 */
function fmtDate(dateStr, includeTime = true) {
  if (!dateStr) return '—';
  const d = new Date(dateStr.replace(' ', 'T'));
  if (isNaN(d)) return dateStr;
  const opts = { year: 'numeric', month: 'short', day: 'numeric' };
  if (includeTime) {
    opts.hour = '2-digit';
    opts.minute = '2-digit';
  }
  return d.toLocaleString(undefined, opts);
}

/**
 * Filter a table body by a search string.
 * Rows must have a data-search attribute with lowercase searchable text.
 * @param {string} tbodyId
 * @param {string} query
 */
function filterTable(tbodyId, query) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  const q = query.toLowerCase().trim();
  Array.from(tbody.rows).forEach(row => {
    const haystack = (row.dataset.search || row.textContent).toLowerCase();
    row.style.display = !q || haystack.includes(q) ? '' : 'none';
  });
}

/**
 * Toggle a password field between text and password type.
 * @param {string} id — element id
 */
function togglePw(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.type = el.type === 'password' ? 'text' : 'password';
}

/**
 * Show a Tabler toast/alert at the top of the page.
 * @param {string} message
 * @param {'success'|'danger'|'warning'|'info'} type
 */
function showToast(message, type = 'success') {
  const wrap = document.getElementById('toast-container');
  if (!wrap) return;
  const id = 'toast-' + Date.now();
  wrap.insertAdjacentHTML('beforeend', `
    <div id="${id}" class="alert alert-${type} alert-dismissible fade show shadow-sm" role="alert">
      ${escHtml(message)}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    </div>`);
  setTimeout(() => {
    const el = document.getElementById(id);
    if (el) el.remove();
  }, 5000);
}

/**
 * Create a modal controller that works with Bootstrap when available,
 * with a lightweight fallback for environments where bootstrap JS is missing.
 * @param {string} id
 * @returns {{show: Function, hide: Function}}
 */
function createModalController(id) {
  const el = document.getElementById(id);
  if (!el) {
    return { show() {}, hide() {} };
  }
  if (window.bootstrap?.Modal) return new window.bootstrap.Modal(el);

  const backdropId = `${id}-backdrop`;
  const closeBtns = el.querySelectorAll('[data-bs-dismiss="modal"]');
  const controller = {
    show() {
      el.style.display = 'block';
      el.classList.add('show');
      el.setAttribute('aria-modal', 'true');
      el.removeAttribute('aria-hidden');
      document.body.classList.add('modal-open');
      if (!document.getElementById(backdropId)) {
        const backdrop = document.createElement('div');
        backdrop.id = backdropId;
        backdrop.className = 'modal-backdrop fade show';
        document.body.appendChild(backdrop);
      }
    },
    hide() {
      el.classList.remove('show');
      el.style.display = 'none';
      el.removeAttribute('aria-modal');
      el.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('modal-open');
      document.getElementById(backdropId)?.remove();
    }
  };

  closeBtns.forEach(btn => btn.addEventListener('click', controller.hide));
  return controller;
}

/**
 * Confirm and call DELETE on an API endpoint.
 * @param {string} url
 * @param {string} confirmMsg
 * @param {Function} onSuccess  — called after successful delete
 */
async function confirmDelete(url, confirmMsg, onSuccess) {
  if (!confirm(confirmMsg)) return;
  try {
    const r = await fetch(url, { method: 'DELETE' });
    if (r.ok) {
      if (onSuccess) onSuccess();
    } else {
      const e = await r.json().catch(() => ({}));
      showToast(e.error || 'Delete failed.', 'danger');
    }
  } catch (err) {
    showToast('Network error: ' + err.message, 'danger');
  }
}
