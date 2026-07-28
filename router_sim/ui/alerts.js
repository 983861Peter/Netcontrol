/* ui/js/alerts.js - Enhanced for live activity display */
const alertFeed = document.getElementById("alertFeed");
const severityFilter = document.getElementById("severityFilter");
const searchInput = document.getElementById("searchInput");

// Cache of events for filtering
let allEvents = [];

async function loadAlerts(){
  try{
    const res = await apiFetch("/logs");
    const logs = await res.json();
    allEvents = logs || [];
    renderAlerts(allEvents);
  }catch(e){ 
    console.error("Load alerts error:", e); 
    UI.toaster.push("error","Failed to load alerts",2000); 
  }
}

function getActivityIcon(activityType) {
  const icons = {
    "device_created": "➕",
    "device_reset": "🔄",
    "device_discovered": "🔍",
    "config_deployed": "⚙️",
    "backup_created": "💾",
    "user_login": "🔓",
    "user_logout": "🔒",
    "device_adopted": "✅"
  };
  return icons[activityType] || "📋";
}

function getSeverityColor(severity) {
  const colors = {
    "INFO": "#3498db",
    "NOTICE": "#2ecc71",
    "WARNING": "#f39c12",
    "ALERT": "#e74c3c",
    "CRITICAL": "#c0392b"
  };
  return colors[severity] || "#95a5a6";
}

function renderAlerts(logs){
  const q = (searchInput.value || "").toLowerCase();
  const sev = severityFilter.value || "ALL";
  
  const items = logs.filter(l=>{
    const text = (l.message || l.device_id || l.username || "").toString().toLowerCase();
    const actType = (l.activity_type || "").toLowerCase();
    
    if(!text.includes(q) && !actType.includes(q)) return false;
    if(sev !== "ALL" && l.severity !== sev) return false;
    return true;
  });

  if (items.length === 0) {
    alertFeed.innerHTML = `<div class="card" style="text-align:center;color:#888;padding:24px">No activities yet</div>`;
    return;
  }

  alertFeed.innerHTML = items.map(l => {
    const icon = getActivityIcon(l.activity_type);
    const color = getSeverityColor(l.severity);
    const ts = new Date(l.timestamp || l.ts).toLocaleString();
    const activityLabel = (l.activity_type || "event").replace(/_/g, " ").toUpperCase();
    const userInfo = l.username ? `<span class="tag" style="background:#9b59b6;color:white">${l.username}</span>` : "";
    const deviceInfo = l.device_id ? `<span class="tag" style="background:#3498db;color:white">${l.device_id}</span>` : "";
    
    return `<div class="card" style="margin-bottom:12px;border-left:4px solid ${color}">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div style="display:flex;align-items:center;gap:12px">
          <span style="font-size:20px">${icon}</span>
          <div>
            <div style="font-weight:bold;margin-bottom:4px">${activityLabel}</div>
            <div style="color:#555;font-size:0.9em">${l.message}</div>
          </div>
        </div>
        <div style="text-align:right">
          <div class="muted small">${ts}</div>
        </div>
      </div>
      <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
        ${userInfo} ${deviceInfo}
      </div>
    </div>`;
  }).join("");
}

// Event filtering
severityFilter && severityFilter.addEventListener("change", () => renderAlerts(allEvents));
searchInput && searchInput.addEventListener("input", () => renderAlerts(allEvents));

/* WebSocket live push - real-time updates */
WSManager.start("alerts", "/ws/alerts", (msg) => {
  // Incoming event from server broadcast
  const icon = getActivityIcon(msg.activity_type || msg.type);
  const severity = msg.severity || "INFO";
  const color = getSeverityColor(severity);
  
  // Toast notification
  const toastMsg = `${icon} ${msg.message || msg.event || "Activity"}`;
  const toastLevel = (severity || "INFO").toLowerCase();
  UI.toaster.push(toastLevel, toastMsg, 3000);
  
  // Prepend to feed
  const el = document.createElement("div");
  el.className = "card";
  el.style.marginBottom = "12px";
  el.style.borderLeft = `4px solid ${color}`;
  
  const userInfo = msg.username ? `<span class="tag" style="background:#9b59b6;color:white">${msg.username}</span>` : "";
  const deviceInfo = msg.device_id ? `<span class="tag" style="background:#3498db;color:white">${msg.device_id}</span>` : "";
  const activityLabel = (msg.activity_type || msg.type || "event").replace(/_/g, " ").toUpperCase();
  const ts = new Date().toLocaleString();
  
  el.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div style="display:flex;align-items:center;gap:12px">
        <span style="font-size:20px">${icon}</span>
        <div>
          <div style="font-weight:bold;margin-bottom:4px">${activityLabel}</div>
          <div style="color:#555;font-size:0.9em">${msg.message}</div>
        </div>
      </div>
      <div style="text-align:right">
        <div class="muted small">${ts}</div>
      </div>
    </div>
    <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
      ${userInfo} ${deviceInfo}
    </div>
  `;
  
  // Prepend to top of feed
  if (alertFeed.firstChild) {
    alertFeed.insertBefore(el, alertFeed.firstChild);
  } else {
    alertFeed.appendChild(el);
  }
  
  // Keep only last 100 items in feed for performance
  while (alertFeed.children.length > 100) {
    alertFeed.removeChild(alertFeed.lastChild);
  }
  
  // Update local cache
  allEvents.unshift(msg);
});

// Load initial alerts on page load
document.addEventListener("DOMContentLoaded", () => {
  loadAlerts();
  const btnExport = document.getElementById("btnExportLogs");
  if (btnExport) btnExport.addEventListener("click", () => {
    window.location.href = `${API_URL}/export/logs`;
  });
});