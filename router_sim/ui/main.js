const inferredApiBase = window.location.port === "3000"
  ? "http://127.0.0.1:8080"
  : window.location.origin;
const API_URL = window.API_BASE || inferredApiBase;
window.API_URL = API_URL;
window.API_BASE = window.API_BASE || API_URL;
console.log("[API] Using API base:", API_URL);

// --- Auth helpers ---
function authHeaders() {
  const token = localStorage.getItem("token");
  return token ? { "Authorization": `Bearer ${token}` } : {};
}

function clearAuthToken() {
  localStorage.removeItem("token");
  localStorage.removeItem("username");
  localStorage.removeItem("role");
}

// --- Global API fetch wrapper ---
async function apiFetch(path, opts = {}) {
  opts = Object.assign({}, opts);
  opts.headers = Object.assign({}, opts.headers || {}, {
    "Content-Type": "application/json",
    ...authHeaders()
  });
  try {
    const res = await fetch(`${API_URL}${path}`, opts);
    
    if (res.status === 401) {
      clearAuthToken();
      window.location.href = "login.html";
      throw new Error("Unauthorized");
    }

    return res;
  } catch (err) {
    console.error("API Fetch Error:", err, { url: `${API_URL}${path}`, options: opts });
    throw err;
  }
}

// --- WebSocket Manager ---
const WSManager = {
  sockets: {},
  start(name, path, onMessage) {
    if (this.sockets[name]) return;
    const base = API_URL.replace(/^http/, "ws");
    const url = `${base}${path}`;
    const connect = () => {
      const ws = new WebSocket(url);
      ws.onmessage = (event) => {
        try { onMessage(JSON.parse(event.data)); } catch (e) { console.error(e); }
      };
      ws.onclose = () => {
        this.sockets[name] = null;
        setTimeout(connect, 5000);
      };
      this.sockets[name] = ws;
    };
    connect();
  }
};
window.WSManager = WSManager;

// --- Global UI components & logic ---
document.addEventListener('DOMContentLoaded', () => {
    // Handle global logout button
    const btnLogout = document.getElementById('btnLogout');
    if (btnLogout) {
        btnLogout.addEventListener('click', () => {
            clearAuthToken();
            window.location.href = 'login.html';
        });
    }
});

// Enhanced Toast Function
function showToast(message, type = 'info', duration = 4000) {
  const toastContainer = document.getElementById('toasts');
  if (!toastContainer) return;
  
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  const icons = {
    success: '✓',
    error: '✗',
    info: 'ℹ'
  };
  
  toast.innerHTML = `
    <span style="font-size:18px; width:24px; text-align:center;">${icons[type] || 'ℹ'}</span>
    <div class="msg" style="flex:1; font-weight:500;">${message}</div>
    <button onclick="this.parentElement.remove()" style="background:transparent; border:none; color:var(--muted); cursor:pointer; font-size:16px; padding:0 4px;">×</button>
  `;
  
  toastContainer.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Add slideOut animation
const style = document.createElement('style');
style.textContent = `
  @keyframes slideOut {
    to {
      transform: translateX(100%);
      opacity: 0;
    }
  }
`;
document.head.appendChild(style);