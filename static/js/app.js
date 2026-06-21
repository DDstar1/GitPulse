function getAuthToken() {
  return localStorage.getItem('gitpulse_token');
}

function clearAuthAndRedirect() {
  localStorage.removeItem('gitpulse_token');
  window.location.href = '/login';
}

async function apiFetch(url, options = {}) {
  const token = getAuthToken();
  const headers = Object.assign({}, options.headers || {});
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(url, Object.assign({}, options, { headers }));

  if (response.status === 401) {
    clearAuthAndRedirect();
    throw new Error('Unauthorized');
  }

  return response;
}

function formatTime(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function truncate(text, length) {
  if (!text) return '';
  return text.length > length ? text.substring(0, length) + '...' : text;
}

function statusBadgeClass(status) {
  if (status === 'success') return 'badge-success';
  if (status === 'failed') return 'badge-failed';
  if (status === 'skipped') return 'badge-skipped';
  return '';
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    window.dispatchEvent(new CustomEvent('gitpulse-toast', { detail: { message: 'Copied to clipboard', type: 'success' } }));
  } catch (e) {
    window.dispatchEvent(new CustomEvent('gitpulse-toast', { detail: { message: 'Failed to copy', type: 'error' } }));
  }
}

function gitpulseApp() {
  return {
    view: 'projects',
    toasts: [],
    toastId: 0,

    init() {
      if (!getAuthToken()) {
        window.location.href = '/login';
        return;
      }
      window.addEventListener('gitpulse-toast', (e) => {
        this.showToast(e.detail.message, e.detail.type);
      });
    },

    setView(view) {
      this.view = view;
    },

    showToast(message, type = 'success') {
      const id = ++this.toastId;
      this.toasts.push({ id, message, type });
      setTimeout(() => {
        this.toasts = this.toasts.filter((t) => t.id !== id);
      }, 3000);
    },
  };
}
