function escapeHtml(text) {
  if (!text && text !== 0) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
async function refreshClients(){
  try{
    const res = await apiFetch("/clients");
    const clients = await res.json();
    console.log("Clients fetched:", clients);

    if (!clients || clients.length === 0) {
      document.querySelector("#clientTable tbody").innerHTML = `<tr><td colspan="5" style="text-align:center;color:#888;">No clients available</td></tr>`;
      return;
    }

    document.querySelector("#clientTable tbody").innerHTML = clients.map(c => {
      const deviceCount = c.device_count || 0;
      return `<tr id="client-row-${c.id}" onclick="openClientPanel('${c.id}')" style="cursor:pointer">
        <td>${escapeHtml(c.name)}</td>
        <td>${escapeHtml(c.location || '—')}</td>
        <td>${escapeHtml(c.contact_info || '—')}</td>
        <td>${deviceCount}</td>
        <td onclick="event.stopPropagation()">
          <button class="btn small" onclick="viewClientDevices('${c.id}')">View Devices</button>
          <button class="btn ghost small" onclick="editClient('${c.id}')">Edit</button>
          <button class="btn ghost small" onclick="deleteClient('${c.id}')">Delete</button>
        </td>
      </tr>`;
    }).join("");
  } catch(e){
    console.error(e);
    UI.toaster.push("error","Failed to load clients",3000);
  }
}

async function deleteClient(clientId){
  if(!confirm("Delete this client? This will not affect attached devices.")) return;
  try{
    const res = await apiFetch(`/clients/${clientId}`, { method: "DELETE" });
    if (res.ok){
      UI.toaster.push("success","Client deleted",2000);
      refreshClients();
    } else {
      const err = await res.json();
      UI.toaster.push("error", err.detail || "Delete failed", 3000);
    }
  } catch(e){ 
    UI.toaster.push("error","Delete error",3000);
  }
}

function viewClientDevices(clientId){
  // Redirect to devices page with client filter
  window.location.href = `devices.html?client=${clientId}`;
}

async function editClient(clientId){
  try{
    const res = await apiFetch(`/clients/${clientId}`);
    if (!res.ok) return;
    const c = await res.json();
    
    UI.modal({
      html: `
        <h3>Edit Client</h3>
        <label class="muted small">Name</label>
        <input id="edit_name" class="input" value="${escapeHtml(c.name)}" />
        <label class="muted small">Location</label>
        <input id="edit_location" class="input" value="${escapeHtml(c.location || '')}" />
        <label class="muted small">Contact Info</label>
        <input id="edit_contact" class="input" value="${escapeHtml(c.contact_info || '')}" />
      `,
      buttons: [
        {label: "Cancel", className: "btn ghost"},
        {label: "Save", className: "btn", onClick: async () => {
          const name = document.getElementById("edit_name").value.trim();
          const location = document.getElementById("edit_location").value.trim();
          const contact = document.getElementById("edit_contact").value.trim();
          
          if (!name) {
            UI.toaster.push("error", "Name is required", 3000);
            return;
          }
          
          try {
            const res = await apiFetch(`/clients/${clientId}`, {
              method: "PUT",
              body: JSON.stringify({ name, location, contact_info: contact })
            });
            if (res.ok) {
              UI.toaster.push("success", "Client updated", 2000);
              refreshClients();
            } else {
              UI.toaster.push("error", "Update failed", 3000);
            }
          } catch (e) {
            UI.toaster.push("error", "Update error", 3000);
          }
        }}
      ]
    });
  } catch(e){
    UI.toaster.push("error","Failed to load client",3000);
  }
}

function closeClientPanel(){
  const panel = document.getElementById("clientSidePanel");
  if(panel) panel.style.display = "none";
}

async function openClientPanel(clientId){
  const panel = document.getElementById("clientSidePanel");
  const content = document.getElementById("clientPanelContent");
  
  if(panel) panel.style.display = "block";
  if(content) content.innerHTML = "<div style='text-align:center;padding:20px;'>Loading client details...</div>";

  try{
    const res = await apiFetch(`/clients/${clientId}`);
    if (!res.ok) {
      if(content) content.innerHTML = "<div style='text-align:center;padding:20px;color:#888;'>Failed to load client details</div>";
      return;
    }
    const c = await res.json();
    
    // Fetch devices to show stats in panel
    const devRes = await apiFetch("/devices");
    const devices = devRes.ok ? await devRes.json() : [];
    const clientDevices = devices.filter(d => d.client_id == clientId);
    const onlineCount = clientDevices.filter(d => d.status === 'online').length;

    if(content) {
      content.innerHTML = `
        <div style="display:flex;gap:12px;align-items:center">
          <div style="width:48px;height:48px;background:#eee;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:24px">👤</div>
          <div>
            <div style="font-weight:600">${escapeHtml(c.name)}</div>
            <div class="muted small">${escapeHtml(c.location || '—')}</div>
          </div>
        </div>

        <div style="margin-top:12px">
          <div><b>Contact:</b> ${escapeHtml(c.contact_info || '—')}</div>
          <div><b>Total Devices:</b> ${clientDevices.length}</div>
          <div><b>Online Devices:</b> ${onlineCount}</div>
        </div>

        <div class="action-row" style="margin-top:20px; display:flex; gap:8px; flex-wrap:wrap;">
          <button class="btn" onclick="viewClientDevices('${c.id}')">View Devices</button>
          <button class="btn ghost" onclick="editClient('${c.id}')">Edit</button>
          <button class="btn ghost" onclick="deleteClient('${c.id}')">Delete</button>
          <button class="btn ghost" onclick="closeClientPanel()">Close</button>
        </div>
      `;
    }
  } catch(e){
    console.error(e);
    UI.toaster.push("error","Failed to open client panel",3000);
  }
}

// Add client modal
document.getElementById("openAddClientModal").addEventListener("click", () => {
  UI.modal({
    html: `
      <h3>Add Client</h3>
      <label class="muted small">Name</label>
      <input id="new_name" class="input" placeholder="Client Name" />
      <label class="muted small">Location</label>
      <input id="new_location" class="input" placeholder="Address, City, State" />
      <label class="muted small">Contact Info</label>
      <input id="new_contact" class="input" placeholder="Phone or Email" />
    `,
    buttons: [
      {label: "Cancel", className: "btn ghost"},
      {label: "Add", className: "btn", onClick: async () => {
        const name = document.getElementById("new_name").value.trim();
        const location = document.getElementById("new_location").value.trim();
        const contact = document.getElementById("new_contact").value.trim();
        
        if (!name) {
          UI.toaster.push("error", "Name is required", 3000);
          return;
        }
        
        try {
          const res = await apiFetch("/clients", {
            method: "POST",
            body: JSON.stringify({ name, location, contact_info: contact })
          });
          if (res.ok) {
            UI.toaster.push("success", "Client added", 2000);
            refreshClients();
          } else {
            UI.toaster.push("error", "Add failed", 3000);
          }
        } catch (e) {
          UI.toaster.push("error", "Add error", 3000);
        }
      }}
    ]
  });
});

// Initial load and event listeners
refreshClients();
document.getElementById("btnRefreshClients").addEventListener("click", refreshClients);
document.getElementById("filterClient").addEventListener("input", () => {
  const q = document.getElementById("filterClient").value.toLowerCase();
  Array.from(document.querySelectorAll("#clientTable tr")).forEach(tr => {
    tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
  });
});
