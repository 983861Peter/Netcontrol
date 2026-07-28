const API_BASE = (typeof API_URL !== 'undefined' ? API_URL : "http://127.0.0.1:8080");
const token = localStorage.getItem("token");
const role = localStorage.getItem("role");

if (!token || role !== "admin") {
  window.location.href = "login.html";
}
// Load admin info
document.getElementById("adminUsername").innerText = localStorage.getItem("username");
document.getElementById("adminEmail").innerText = localStorage.getItem("email") || "admin@example.com";
document.getElementById("adminRole").innerText = role;

// Initial Load
initReports();

document.getElementById("logoutBtn").onclick = () => {
  localStorage.clear();
  window.location.href = "../login.html";
};

// --- Reports & Analytics Section ---
async function initReports() {
  // Pre-fill email
  const emailInput = document.getElementById("sched_email");
  if(emailInput) emailInput.value = localStorage.getItem("email") || "";

  // Hide PDF buttons if not admin
  if (role !== 'admin') {
    document.querySelectorAll('.admin-only-btn').forEach(el => el.style.display = 'none');
  }

  loadUsageStats();
  loadComplianceStats();
  loadUserStats(); // NEW: Load user stats preview

  // Render chart if analytics.js is loaded
  if(typeof generateRealisticData === 'function' && typeof drawAnalytics === 'function') {
    const data = generateRealisticData();
    drawAnalytics(data, "accountUsageChart");
  }
}

async function loadUsageStats() {
  try {
    const res = await fetch(`${API_BASE}/reports/usage`, { headers: { "Authorization": `Bearer ${token}` } });
    if (!res.ok) throw new Error("Stats fetch failed");
    const json = await res.json();
    const d = json.data;
    
    document.getElementById("usageStats").innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px;">
        <div class="metric-tile">
          <div class="muted small">Total Bandwidth</div>
          <div class="value">${d.total_bandwidth}</div>
        </div>
        <div class="metric-tile">
          <div class="muted small">Active Devices (Avg)</div>
          <div class="value">${d.active_devices_avg}</div>
        </div>
        <div class="metric-tile">
          <div class="muted small">Peak Usage</div>
          <div class="value">${d.peak_usage_time}</div>
        </div>
        <div class="metric-tile">
          <div class="muted small">System Uptime</div>
          <div class="value" style="color:var(--success)">${d.uptime_avg}</div>
        </div>
      </div>
    `;
  } catch (e) { console.error(e); }
}

async function loadComplianceStats() {
  try {
    const res = await fetch(`${API_BASE}/reports/compliance`, { headers: { "Authorization": `Bearer ${token}` } });
    if (!res.ok) throw new Error("Compliance fetch failed");
    const json = await res.json();
    const d = json.data;
    const color = d.compliance_score > 80 ? "#10b981" : d.compliance_score > 50 ? "#f59e0b" : "#ef4444";
    
    document.getElementById("complianceStats").innerHTML = `
      <div class="compliance-header" style="margin-bottom:15px">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px">
          <span class="small muted">Overall Security Compliance</span>
          <span style="font-weight:bold; color:${color}">${d.compliance_score}%</span>
        </div>
        <div style="height:8px; background:rgba(255,255,255,0.1); border-radius:4px; overflow:hidden">
          <div style="width:${d.compliance_score}%; height:100%; background:${color}; transition: width 1s ease;"></div>
        </div>
      </div>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px;">
        <div class="small-stat"><b>${d.compliant_devices}</b> <span class="muted">Compliant</span></div>
        <div class="small-stat"><b>${d.outdated_firmware}</b> <span class="muted" style="color:#f87171">Outdated FW</span></div>
        <div class="small-stat"><b>${d.weak_credentials}</b> <span class="muted" style="color:#f87171">Weak Creds</span></div>
      </div>
    `;
  } catch (e) { console.error(e); }
}

async function loadUserStats() {
  try {
    const res = await fetch(`${API_BASE}/reports/export?report_type=users&format=csv&preview=true`, { headers: { "Authorization": `Bearer ${token}` } });
    if (!res.ok) throw new Error("User stats fetch failed");
    const json = await res.json();
    const content = json.content; // This will be the CSV content

    // Parse CSV to get a count (simple approach, could be more robust)
    const lines = content.trim().split('\n');
    const userCount = lines.length > 2 ? lines.length - 2 : 0; // Subtract header and spacer line

    document.getElementById("userStats").innerHTML = `
      <div style="display: grid; grid-template-columns: 1fr; gap: 12px;">
        <div class="metric-tile">
          <div class="muted small">Total Users</div>
          <div class="value">${userCount}</div>
        </div>
      </div>
    `;
  } catch (e) { 
    console.error("Failed to load user stats:", e);
    document.getElementById("userStats").innerHTML = `<div class="muted small">Failed to load user stats. Admin access required.</div>`;
  }
}

window.exportReport = async function(event, type, format, preview = false) {
  const url = `${API_BASE}/reports/export?report_type=${type}&format=${format}${preview ? '&preview=true' : ''}`;
  const btn = event.currentTarget; // Now 'event' is correctly passed
  const originalContent = btn.innerHTML;
  
  try {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-small"></span> Generating...`;
    showToast(`Preparing ${type.toUpperCase()} ${format.toUpperCase()}...`, "info"); // Uses global showToast

    const res = await fetch(url, {
      headers: { "Authorization": `Bearer ${token}` }
    });
    
    if (!res.ok) throw new Error("Failed to generate report");
    
    if (preview) {
      const data = await res.json();
      const reportContent = data.content;
      const filename = data.filename;

      UI.modal({
        wide: true,
        html: `
          <h3>${type.toUpperCase()} Report Preview (${format.toUpperCase()})</h3>
          <pre style="white-space: pre-wrap; max-height: 400px; overflow-y: auto; background: var(--bg-primary); padding: 10px; border-radius: 8px; border: 1px solid var(--border-light); color: var(--text-primary);">${UI.escapeHtml(reportContent)}</pre>
        `,
        buttons: [
          {label: "Close", className: "btn ghost"},
          {label: `Download ${format.toUpperCase()}`, className: "btn", onClick: () => {
            // Trigger actual download
            const downloadUrl = `${API_BASE}/reports/export?report_type=${type}&format=${format}`;
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            showToast(`Report downloaded successfully`, "success");
          }} // Uses global showToast
        ]
      });
      showToast(`Preview generated`, "success");

    } else {
      const blob = await res.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = `${type}_report_${new Date().toISOString().split('T')[0]}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(downloadUrl);
      showToast(`Report downloaded successfully`, "success");
    } // Uses global showToast
  } catch (err) {
    showToast(`Export failed: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalContent;
  }
}

window.scheduleReport = async function() {
  const type = document.getElementById("sched_type").value;
  const freq = document.getElementById("sched_freq").value;
  const email = document.getElementById("sched_email").value;
  if(!email) return showToast("Email required", "error");

  try {
    const res = await fetch(`${API_BASE}/reports/schedule`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
      body: JSON.stringify({ report_type: type, frequency: freq, email: email })
    });
    if(res.ok) showToast("Report scheduled successfully", "success");
    else showToast("Failed to schedule", "error");
  } catch(e) { showToast("Connection error", "error"); }
}

// const API_USERS = "http://127.0.0.1:8080/auth/users";

// document.addEventListener("DOMContentLoaded", async () => {
//   const token = localStorage.getItem("token");
//   const username = localStorage.getItem("username");
//   const role = localStorage.getItem("role");

//   if (!token) {
//     window.location.href = "login.html";
//     return;
//   }

//   document.getElementById("usernameDisplay").innerText = username;
//   document.getElementById("roleDisplay").innerText = role;
//   document.getElementById("userAvatar").src = `https://ui-avatars.com/api/?background=007CF0&color=fff&name=${username}`;

//   try {
//     const res = await fetch(API_USERS, {
//       headers: { "Authorization": `Bearer ${token}` }
//     });
//     if (!res.ok) throw new Error("Failed to fetch user info");
//     const users = await res.json();
//     const me = users.find(u => u.username === username);

//     if (me) {
//       const perms = [
//         { label: "Add Devices", val: me.can_add_device },
//         { label: "Delete Devices", val: me.can_delete_device },
//         { label: "Restart Devices", val: me.can_restart_device },
//         { label: "Configure Devices", val: me.can_configure_device }
//       ];
//       const list = document.getElementById("permList");
//       list.innerHTML = perms.map(p => `
//         <li>${p.label}: <strong style="color:${p.val ? '#06D6A0' : '#E63946'}">${p.val ? 'Enabled' : 'Disabled'}</strong></li>
//       `).join("");
//     }
//   } catch (err) {
//     console.error(err);
//   }
// });

// document.getElementById("logoutBtn").addEventListener("click", () => {
//   localStorage.clear();
//   window.location.href = "login.html";
// });
