
/* ui/js/devices.js */
const discoveredTBody = document.querySelector("#discoveredTable tbody");
const deviceTBody = document.querySelector("#deviceTable tbody");
const scanStatus = document.getElementById("scanStatus");
const filterInput = document.getElementById("filterDevice");
const ifacePollers = new Map();
const _simulatedIps = new Map();
let _deviceCache = [];
let currentSort = { column: 'id', dir: 'asc' };

// Auto-inject missing UI buttons for Discovery and Site Survey features
document.addEventListener("DOMContentLoaded", () => {
  const actionHeader = document.querySelector(".page-header .actions") || document.querySelector(".header-actions");
  if (actionHeader) {
    if (!document.getElementById("btnScanUI")) {
      const btn = document.createElement("button");
      btn.id = "btnScanUI";
      btn.className = "btn";
      btn.innerHTML = "🔍 Network Discovery";
      actionHeader.prepend(btn);
    }
    if (!document.getElementById("btnSiteSurvey")) {
      const btn = document.createElement("button");
      btn.id = "btnSiteSurvey";
      btn.className = "btn ghost";
      btn.innerHTML = "📡 Site Survey";
      actionHeader.prepend(btn);
    }
  }
});

function escapeHtml(text) {
  if (!text && text !== 0) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

window.sortDevices = function(column) {
  if (currentSort.column === column) {
    currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    currentSort.column = column;
    currentSort.dir = 'asc';
  }
  updateSortIndicators();
  renderDeviceTable();
}

function updateSortIndicators() {
  const headers = {
    'id': 'th-id',
    'ssid': 'th-ssid',
    'ip': 'th-ip',
    'mac': 'th-mac',
    'model': 'th-model'
  };
  
  for (const [col, id] of Object.entries(headers)) {
    const el = document.getElementById(id);
    if (!el) continue;
    // Preserve the label text (remove existing arrow)
    const label = el.innerText.replace(/[↕↑↓]/g, '').trim();
    
    if (currentSort.column === col) {
      el.innerText = `${label} ${currentSort.dir === 'asc' ? '↑' : '↓'}`;
      el.style.color = "#fff";
    } else {
      el.innerText = `${label} ↕`;
      el.style.color = "";
    }
  }
}

function ipToNum(ip) {
  if (!ip) return 0;
  const parts = ip.split('.');
  if (parts.length !== 4) return 0;
  return ((+parts[0]) * 16777216) + ((+parts[1]) * 65536) + ((+parts[2]) * 256) + (+parts[3]);
}

function renderDeviceTable() {
  const list = _deviceCache || [];
  if (!list || list.length === 0) {
    deviceTBody.innerHTML = `<tr><td colspan="12" style="text-align:center;color:#888;">No routers available</td></tr>`;
    return;
  }

  const sorted = [...list].sort((a, b) => {
    const dir = currentSort.dir === 'asc' ? 1 : -1;
    let valA, valB;
    
    if (currentSort.column === 'id') {
       valA = (a.device_id || "").toLowerCase();
       valB = (b.device_id || "").toLowerCase();
    } else if (currentSort.column === 'ssid') {
       valA = (a.ssid || a.name || a.device_id || "").toLowerCase();
       valB = (b.ssid || b.name || b.device_id || "").toLowerCase();
    } else if (currentSort.column === 'ip') {
       return (ipToNum(a.ip_address) - ipToNum(b.ip_address)) * dir;
    } else if (currentSort.column === 'mac') {
       valA = (a.mac_address || a.mac || "").toLowerCase();
       valB = (b.mac_address || b.mac || "").toLowerCase();
    } else if (currentSort.column === 'model') {
       valA = (a.model || "").toLowerCase();
       valB = (b.model || "").toLowerCase();
    } else {
       return 0;
    }
    
    if (valA < valB) return -1 * dir;
    if (valA > valB) return 1 * dir;
    return 0;
  });

  deviceTBody.innerHTML = sorted.map((d, i) => {
    const mac = d.mac_address || d.mac || "N/A";
    const clients = d.status_info ? (d.status_info.clients ? d.status_info.clients.length : 0) : '—';
    const rxVal = d.status_info && d.status_info.rx ? d.status_info.rx : 0;
    const txVal = d.status_info && d.status_info.tx ? d.status_info.tx : 0;
    const clientInfo = d.client ? `${escapeHtml(d.client.name)} (${escapeHtml(d.client.location || 'N/A')})` : (d.client_id ? `ID: ${d.client_id}`: '—');
    const ssid = d.ssid || d.name || d.device_id;
    const safeId = (d.device_id || "").replace(/'/g, "\\'");
    const rowClass = d.status === 'offline' ? 'offline-row' : '';
    return `<tr id="row-${d.device_id}" class="${rowClass}" onclick="openDevicePanel('${safeId}')">
      <td>${i + 1}</td>
      <td><img src="${getDeviceIcon(d.model)}" width="28" onerror="this.onerror=null;this.src='${API_URL}/static/icons/default.jpg'"></td>
      <td>${escapeHtml(ssid)}</td>
      <td>${d.ip_address || '-'}</td>
      <td>${mac}</td>
      <td>${d.model || 'Unknown'}</td>
      <td>${d.status}</td>
      <td>${clients}</td>
      <td><span id="listRx-${d.device_id}">${formatBytes(rxVal)}</span></td>
      <td><span id="listTx-${d.device_id}">${formatBytes(txVal)}</span></td>
      <td>${clientInfo}</td>
    </tr>`;
  }).join("");
  
  startInterfacePollingForDevices(sorted);
}

async function refreshLists(){
  try{
    const res = await apiFetch("/devices");
    if (res.status === 401) {
      UI.toaster.push("error", "Session expired. Redirecting to login...", 3000);
      setTimeout(() => location.href = 'login.html', 2000);
      return;
    }
    if (!res.ok) throw new Error("Failed to fetch devices");
    const list = await res.json();
    
    // Exclude devices that belong to a station so they only show under that station
    const stationDevicesFiltered = list.filter(d => !d.station_id);

    // Ensure DHCP devices have IPs (simulated if missing)
    stationDevicesFiltered.forEach(d => {
      if (!d.ip_address || d.ip_address === "0.0.0.0" || d.ip_address === "-") {
        if (!_simulatedIps.has(d.device_id)) {
           _simulatedIps.set(d.device_id, `192.168.1.${Math.floor(Math.random() * 150) + 100}`);
        }
        d.ip_address = _simulatedIps.get(d.device_id);
      }
    });

    _deviceCache = stationDevicesFiltered;
    console.log("Routers fetched:", stationDevicesFiltered);
    
    updateSortIndicators();
    renderDeviceTable();
  }catch(e){ 
    console.error(e); 
    UI.toaster.push("error","Failed to load devices",3000) } 
}

// Poll interfaces for devices and update rx/tx in the table. If no real metrics endpoint exists, this will fall back to client-side simulation.
// Note: This function is currently disabled since rx/tx columns are not displayed in the device table
async function startInterfacePollingForDevices(devices) {
  if (!Array.isArray(devices)) {
    console.warn("startInterfacePollingForDevices: expected devices array, got", devices);
    return;
  }
  // stop pollers for devices no longer present
  const activeDeviceIds = new Set(devices.map(d=>d.device_id));
  for (const [deviceId, intervalId] of ifacePollers.entries()) {
    if (!activeDeviceIds.has(deviceId)) {
      clearInterval(intervalId);
      ifacePollers.delete(deviceId);
    }
  }
  
  // Start simulation for each device
  devices.forEach(d => {
    if(ifacePollers.has(d.device_id)) return;

    let simRx = (d.status_info && d.status_info.rx) || 0;
    let simTx = (d.status_info && d.status_info.tx) || 0;
    const activeClients = (d.status_info && d.status_info.clients) ? d.status_info.clients.length : 0;

    const intervalId = setInterval(() => {
      // simRx += Math.floor(Math.random() * 50000);
      // simTx += Math.floor(Math.random() * 20000);
      let rateRx, rateTx;
      if (activeClients > 0) {
         // Active usage: 50 KB/s - 5 MB/s
         rateRx = Math.floor(Math.random() * (5242880 - 51200) + 51200);
         rateTx = Math.floor(Math.random() * (2097152 - 20480) + 20480);
      } else {
         // Standby: 100 B/s - 2 KB/s
         rateRx = Math.floor(Math.random() * (2048 - 100) + 100);
         rateTx = Math.floor(Math.random() * (1024 - 50) + 50);
      }
      const elRx = document.getElementById(`listRx-${d.device_id}`);
      const elTx = document.getElementById(`listTx-${d.device_id}`);
      if(elRx) elRx.innerText = formatBytes(rateRx) + "/s";
      if(elTx) elTx.innerText = formatBytes(rateTx) + "/s";
    }, 2000);
    ifacePollers.set(d.device_id, intervalId);
  });
}

function formatBytes(n) {
  if (n === null || n === undefined) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024*1024) return `${(n/1024).toFixed(1)} KB`;
  if (n < 1024*1024*1024) return `${(n/1024/1024).toFixed(1)} MB`;
  return `${(n/1024/1024/1024).toFixed(2)} GB`;
}
// function getDeviceIcon(model){
//   if(!model) return "/static/icons/default.jpg";
//   model = model.toLowerCase();
//   if(model.includes("ruijie")) return "router_sim/ui/icons/ruijie.jpg";
//   if(model.includes("d-link")) return "router_sim/ui/icons/dlink.jpg";
//   if(model.includes("tp-link")) return "router_sim/ui/icons/tplink.jpg";
//   return `${API_URL}/static/icons/${file}`
// }

function handleMonitorMessage(msg) {
  if (!msg || !msg.type) return;

  if (msg.type === "devices_snapshot") {
    // msg.devices is an array with device objects
    _deviceCache = msg.devices || [];
    renderDeviceTable();
  } else if (msg.type === "device_reset"){
    const d = msg;
    UI.toaster.push("warning", `Device ${d.device_id} appears to have been reset!`, 5000);
      const row = document.getElementById(`row-${d.device_id}`);
    if (row) {
      row.classList.add("highlight-reset");
      setTimeout(()=> row.classList.remove("highlight-reset"), 15000);
    } else {
      // if row not in DOM, refresh lists
      refreshLists();
    }
    // optionally show modal with details
    console.log("Reset details:", d.details);
  } else if (msg.type === "alert") {
    // legacy alerts
  }
}

function getDeviceIcon(model){
   // ensure API_URL is the API server where static is mounted
  const base = API_URL || (window.location.port === "3000" ? "http://127.0.0.1:8080" : window.location.origin);
  if(!model) return `${base}/static/icons/default.jpg`;

  const m = String(model).toLowerCase();
  if(m.includes("ruijie")) return `${base}/static/icons/ruijie.jpg`;
  if(m.includes("d-link") || m.includes("dlink")) return `${base}/static/icons/dlink.jpg`;
  if(m.includes("tp-link") || m.includes("tplink")) return `${base}/static/icons/tplink.jpg`;
  if(m.includes("tenda")) return `${base}/static/icons/tenda.jpg`;

  // fallback: sanitize model -> filename.jpg
  const file = m.replace(/\s+/g, "_").replace(/[^a-z0-9_.-]/g, "") + ".jpg";
  return `${base}/static/icons/${file}`;
}

/* Add Device Modal */
const btnAddDevice = document.getElementById("openAddModal");
if(btnAddDevice) {
  btnAddDevice.addEventListener("click", () => {
    UI.modal({
      html: `
        <h3>Add Device</h3>

        <label class="muted small">Client (CPE Owner)</label>
        <select id="m_client" class="input">
          <option value="">Infrastructure / Internal</option>
        </select>

        <label class="muted small">Attached To (Parent Device)</label>
        <select id="m_parent" class="input">
          <option value="">No Parent (Root Device)</option>
        </select>

        <label class="muted small">Device ID</label>
        <input id="m_deviceId" class="input" placeholder="router-001" />
        
        <label class="muted small">MAC Address</label>
        <input id="m_mac" class="input" placeholder="AA:BB:CC:DD:EE:FF" />
        
        <label class="muted small">Device Type</label>
        <select id="m_device_type" class="input"></select>

        <label class="muted small">Manufacturer</label>
        <select id="m_model" class="input"></select>
        
        <div id="radioSectorGroup" style="display:none;margin-top:10px">
          <label class="muted small">Sector Attached</label>
          <select id="m_sector" class="input">
            <option value="">Select a sector...</option>
          </select>
        </div>
        
        <label class="muted small">Connection Type</label>
        <select id="m_connType" class="input">
          <option value="dhcp">DHCP (auto)</option>
          <option value="static">Static IP</option>
          <option value="pppoe">PPPoE</option>
        </select>
        
        <div id="connDetails" style="margin-top:8px"></div>
      `,
      buttons: [
        { label: "Cancel", className: "btn ghost" },
        { label: "Add", className: "btn", onClick: async () => {
            const elId = document.getElementById("m_deviceId");
            const elMac = document.getElementById("m_mac");
            const elType = document.getElementById("m_device_type");
            const elModel = document.getElementById("m_model");
            const elConn = document.getElementById("m_connType");
            const elClient = document.getElementById("m_client");
            const elParent = document.getElementById("m_parent");

            if (!elId || !elMac || !elType || !elModel || !elConn || !elClient || !elParent) {
                UI.toaster.push("error", "Modal error: Form elements not found. Please try again.");
                return false;
            }

            const id = elId.value.trim();
            const mac = elMac.value.trim();
            const deviceType = elType.value;
            const model = elModel.value;
            const type = elConn.value;
            const clientId = elClient.value;
            let parentId = elParent.value;

            // If parent is a sector, extract the ID and treat radio as root for the client hierarchy
            let parentSectorId = null;
            if (parentId && parentId.startsWith("SEC-")) {
                parentSectorId = parentId.replace("SEC-", "");
                parentId = ""; // Set parent to null for the DB so dashboard treats it as root radio
            }

            let ip = null;
            if (type === "static") {
                const elIp = document.getElementById("m_ip");
                ip = elIp ? elIp.value.trim() : null;
            }
            
            if (!id) { UI.toaster.push("error", "Device ID is required"); return false; }
            if (!mac) { UI.toaster.push("error", "MAC Address is required"); return false; }

            const normalizedMac = mac.toUpperCase().replace(/-/g, ':').trim();

            // Constraint Validations
            const allDevsRes = await apiFetch("/devices");
            if (allDevsRes.ok) {
              const allDevs = await allDevsRes.json();
              
              // 1. MAC Unique system-wide
              if (allDevs.some(d => (d.mac_address || '').toUpperCase().replace(/-/g, ':') === normalizedMac)) {
                UI.toaster.push("error", "Constraint Error: MAC address already exists in the system");
                return false;
              }
              
              // 2. IP Unique per client
              if (ip && clientId && allDevs.some(d => d.client_id == clientId && d.ip_address === ip)) {
                UI.toaster.push("error", `Constraint Error: IP ${ip} is already assigned to this client`);
                return false;
              }
            }
            
            const payload = {
              device_id: id,
              mac_address: mac,
              device_type: deviceType,
              model: model,
              status: "online",
              client_id: clientId ? parseInt(clientId) : null,
              parent_device_id: (parentId === "" || parentId === "null") ? null : parentId
            };
            
            if (ip) {
              payload.ip_address = ip;
            } else if (type === "pppoe") {
              payload.credentials = {
                username: document.getElementById("m_user").value.trim(),
                password: document.getElementById("m_pass").value.trim()
              };
            }
            
            // Add sector_id for radio devices
            if (deviceType === "Radio") {
              const elSector = document.getElementById("m_sector");
              // Pick sector ID from either the specific dropdown or the Parent selection
              const sectorId = (elSector && elSector.value) ? elSector.value : parentSectorId;

              if (!sectorId) { 
                UI.toaster.push("error", "Sector selection is required for Radio devices. Please select one in either the Sector or Parent dropdown."); 
                return false; 
              }
              payload.sector_id = parseInt(sectorId);
            }
            
            try {
              const res = await apiFetch("/devices", {
                method: "POST",
                body: JSON.stringify(payload)
              });
              if (res.ok) {
                UI.toaster.push("success", "Device added successfully");
                refreshLists();
              } else {
                const err = await res.json();
                UI.toaster.push("error", err.detail || "Failed to add device");
                return false; // Keep modal open
              }
            } catch (e) {
              console.error(e);
              UI.toaster.push("error", "Connection error");
              return false;
            }
          }
        }
      ]
    });

    // Dynamic fields for connection type
    setTimeout(() => {
      const deviceTypeSelect = document.getElementById("m_device_type");
      const modelSelect = document.getElementById("m_model");

      const deviceTypes = {
        "Radio": ["Ubiquiti AirFiber", "Mikrotik SXT", "Cambium ePMP", "NanoStation"],
        "Router": ["TP-Link", "D-Link", "Ruijie", "Tenda", "Netgear", "Linksys","Mikrotik","Huawei"],
        "Switch": ["Cisco", "Juniper", "Arista", "HPE", "Dell"],
        "Access Point": ["Ubiquiti", "Ruckus", "Aruba", "Meraki"],
        "Firewall": ["Palo Alto", "Fortinet", "Check Point", "Sophos"],
        "Other": ["Generic"]
      };

      // Populate device types
      for (const type in deviceTypes) {
        const opt = document.createElement("option");
        opt.value = type;
        opt.textContent = type;
        deviceTypeSelect.appendChild(opt);
      }

      // Update manufacturers based on device type
      const updateManufacturers = async () => {
        const selectedType = deviceTypeSelect.value;
        modelSelect.innerHTML = "";
        deviceTypes[selectedType].forEach(m => {
          const opt = document.createElement("option");
          opt.value = m;
          opt.textContent = m;
          modelSelect.appendChild(opt);
        });
        
        // Show/hide sector selector for radio devices
        const radioSectorGroup = document.getElementById("radioSectorGroup");
        if (selectedType === "Radio") {
          radioSectorGroup.style.display = "block";
          await populateRadioSectors();
        } else {
          radioSectorGroup.style.display = "none";
        }
      };
      
      // Function to populate sectors for radio devices
      window.populateRadioSectors = async () => {
        try {
          const res = await apiFetch('/stations');
          if (!res.ok) return;
          const stations = await res.json();
          const sectorSelect = document.getElementById("m_sector");
          if (!sectorSelect) return;
          
          sectorSelect.innerHTML = '<option value="">Select a sector...</option>';
          stations.forEach(station => {
            (station.sectors || []).forEach(sector => {
              const opt = document.createElement('option');
              opt.value = sector.id;
              opt.textContent = `${sector.name} (${station.name})`;
              sectorSelect.appendChild(opt);
            });
          });
        } catch (e) {
          console.error('Failed to fetch sectors:', e);
        }
      };

      const connSelect = document.getElementById("m_connType");
      const detailsDiv = document.getElementById("connDetails");
      
      const updateDetails = () => {
        const val = connSelect.value;
        if (val === "static") {
          detailsDiv.innerHTML = `<label class="muted small">IP Address</label><input id="m_ip" class="input" placeholder="192.168.1.50" />`;
        } else if (val === "pppoe") {
          detailsDiv.innerHTML = `<label class="muted small">Username</label><input id="m_user" class="input" /><label class="muted small">Password</label><input id="m_pass" class="input" type="password" />`;
        } else {
          detailsDiv.innerHTML = "";
        }
      };

      const clientSelect = document.getElementById("m_client");
      const parentSelect = document.getElementById("m_parent");

      deviceTypeSelect.addEventListener("change", () => {
        updateManufacturers();
        populateParents(clientSelect.value); // Refresh parents to include/exclude sectors
      });

      updateManufacturers(); // Initial population
      connSelect.addEventListener("change", updateDetails);
      
      const populateParents = async (clientId) => {
        const currentSelection = parentSelect.value;
        const res = await apiFetch("/devices");
        if (!res.ok) return;
        const allDevices = await res.json();

        // Filter logic based on request:
        // 1. If clientId is selected: show devices belonging to this client OR station tower infrastructure.
        // 2. If no client is selected: list all devices in the system.
        const filtered = clientId 
          ? allDevices.filter(d => 
              d.client_id == clientId || 
              d.station_id || 
              ['sector', 'infrastructure', 'tower'].includes((d.device_type || "").toLowerCase())
            )
          : allDevices;

        parentSelect.innerHTML = '<option value="">No Parent (Root Device)</option>';
        filtered.forEach(d => {
          const val = d.device_id || d.id;
          const opt = document.createElement("option");
          opt.value = val;
          opt.textContent = `${d.name || d.device_id} (${d.device_type || 'Device'})`;
          if (String(val) === String(currentSelection)) opt.selected = true;
          parentSelect.appendChild(opt);
        });
      };

      // Sync listeners to help the user select the sector in both places
      const sectorSelect = document.getElementById("m_sector");
      sectorSelect.addEventListener("change", (e) => {
        if (deviceTypeSelect.value === "Radio" && e.target.value) {
          parentSelect.value = "SEC-" + e.target.value;
        }
      });

      parentSelect.addEventListener("change", (e) => {
        if (deviceTypeSelect.value === "Radio" && e.target.value.startsWith("SEC-")) {
          sectorSelect.value = e.target.value.replace("SEC-", "");
        }
      });

      apiFetch("/clients").then(res => res.ok ? res.json() : []).then(clients => {
        if(clientSelect) {
          clients.forEach(c => { const opt = document.createElement("option"); opt.value = c.id; opt.textContent = c.name; clientSelect.appendChild(opt); });
          clientSelect.addEventListener("change", (e) => populateParents(e.target.value));
          populateParents(""); // Initial load for infrastructure parents
        }
      });
    }, 50);
  });
}

/* Export CSV */
const btnExport = document.getElementById("btnExport");
if (btnExport) btnExport.addEventListener("click", () => {
  window.location.href = `${API_URL}/export/devices`;
});

// /* Discovery scan */
// document.getElementById("btnScanUI").addEventListener("click", scanNetwork);
// document.getElementById("btnRefresh").addEventListener("click", refreshLists);
// document.getElementById("btnScanUI").addEventListener("click", ()=>UI.toaster.push("info","Starting scan...",2000));

// async function scanNetwork(){
//   const subnet = document.getElementById("subnetRange")/*.value*/  || "192.168.1.0/24";
//   scanStatus.textContent = "Scanning...";
//   try{
//     const res = await apiFetch(`/discovery/scan?subnet=${encodeURIComponent(subnet)}`);
//     const devices = await res.json();
//     scanStatus.textContent = `Found ${devices.length} device(s)`;
//     discoveredTBody.innerHTML = devices.map(d=>`<tr data-state="${d.config_state||'unknown'}">
//       <td>${d.ip}</td><td>${d.mac}</td><td>${d.vendor||d.brand_hint||'Unknown'}</td>
//       <td>${d.http_title||''}</td><td>${d.config_state||'unknown'}</td>
//       <td><button class="btn small" onclick='adoptDevice("${d.ip}","${d.mac}","${d.vendor||d.brand_hint}")'>Adopt</button></td></tr>`).join("");
//   }catch(e){ scanStatus.textContent = "Scan failed"; UI.toaster.push("error","Scan failed",3000) }
// }
/* Discovery scan */
const btnScanUI = document.getElementById("btnScanUI");
if(btnScanUI) {
  btnScanUI.addEventListener("click", () => {
    UI.modal({
      html: `
        <h3>Network Discovery</h3>
        <p class="muted small" style="margin-bottom:12px">Enter the subnet range to scan for new devices.</p>
        <label class="muted small">Subnet (CIDR)</label>
        <input id="scanSubnetInput" class="input" value="192.168.1.0/24" placeholder="e.g. 192.168.1.0/24">
      `,
      buttons: [
        { label: "Cancel", className: "btn ghost" },
        { label: "Start Scan", className: "btn", onClick: () => {
            const subnet = document.getElementById("scanSubnetInput").value.trim();
            if(subnet) scanNetwork(subnet);
          }
        }
      ]
    });
  });
}

/* Wireless Site Survey (Advanced Component) */
const btnSiteSurvey = document.getElementById("btnSiteSurvey");
if(btnSiteSurvey) {
  btnSiteSurvey.addEventListener("click", () => {
    UI.modal({
      html: `
        <h3>Wireless Site Survey</h3>
        <p class="muted small">Scanning for nearby access points, interference, and channel utilization.</p>
        <div id="surveyProgress" style="margin: 15px 0; background: rgba(255,255,255,0.05); border-radius: 4px; padding: 10px;">
           <div style="height: 4px; background: #1e293b; border-radius: 2px; overflow: hidden;">
             <div id="surveyBar" style="width: 0%; height: 100%; background: #6366f1; transition: width 0.3s ease;"></div>
           </div>
           <div id="surveyStatus" class="small muted" style="margin-top:8px">Initializing spectrum analysis...</div>
        </div>
        <div id="surveyResults" style="max-height:300px; overflow-y:auto; display:none;">
          <table class="table small">
            <thead><tr><th>SSID</th><th>BSSID</th><th>Ch</th><th>Signal</th><th>Security</th></tr></thead>
            <tbody id="surveyTableBody"></tbody>
          </table>
        </div>
      `,
      buttons: [{ label: "Close", className: "btn ghost" }]
    });
    runSiteSurvey();
  });
}

async function runSiteSurvey() {
  const bar = document.getElementById("surveyBar");
  const status = document.getElementById("surveyStatus");
  const results = document.getElementById("surveyResults");
  const table = document.getElementById("surveyTableBody");

  try {
    for(let i=0; i<=100; i+=20) {
      if(bar) bar.style.width = i + "%";
      if(status) status.innerText = i < 100 ? `Scanning ${2.4 + (i/100)}GHz Spectrum...` : "Processing signals...";
      await new Promise(r => setTimeout(r, 500));
    }

    const res = await apiFetch("/discovery/site-survey");
    const aps = await res.json();
    
    status.innerText = `Survey complete. Found ${aps.length} nearby networks.`;
    table.innerHTML = aps.map(ap => `
      <tr class="${ap.is_rogue ? 'warning-row' : ''}">
        <td>${escapeHtml(ap.ssid)} ${ap.is_rogue ? '<span title="Rogue AP Detected">⚠️</span>' : ''}</td>
        <td><code>${ap.bssid}</code></td>
        <td>${ap.channel}</td>
        <td><span style="color:${ap.signal > -70 ? '#10b981' : '#f39c12'}">${ap.signal} dBm</span></td>
        <td>${ap.security}</td>
      </tr>
    `).join("");
    results.style.display = "block";
  } catch(e) {
    if(status) status.innerText = "Survey failed to initialize.";
  }
}

document.getElementById("btnRefresh").addEventListener("click", refreshLists);

async function scanNetwork(subnet = "192.168.1.0/24"){
  scanStatus.innerHTML = `<span class="spinner"></span> Scanning ${escapeHtml(subnet)}...`;
  discoveredTBody.innerHTML = `<tr><td colspan="6" style="text-align:center">Initializing network probes...</td></tr>`;
  try{
    const res = await apiFetch(`/discovery/scan?subnet=${encodeURIComponent(subnet)}`);
    let devices = await res.json();
    
    // Deduplicate devices by IP to prevent double display
    const seenIps = new Set();
    devices = devices.filter(d => !seenIps.has(d.ip) && seenIps.add(d.ip));

    scanStatus.textContent = `Found ${devices.length} device(s)`;
    discoveredTBody.innerHTML = devices.map(d=>{
      const isAdoptable = d.is_adoptable === true;
      const vendor = d.vendor || d.brand_hint || 'Unknown';
      // Advanced check: detect if device is already managed
      const isManaged = _deviceCache.some(managed => managed.mac_address === d.mac);
      
      // OS Fingerprinting and VLAN Awareness
      const osHint = d.os_info ? `💻 ${d.os_info.name} ${d.os_info.version}` : 'Identifying OS...';
      const vlanTag = d.vlan_id ? `<span class="tag small" style="background:#475569">VLAN ${d.vlan_id}</span>` : '';
      
      const adoptBtn = isAdoptable 
        ? (isManaged ? `<span class="tag success">Managed</span>` : `<button class="btn small" onclick='adoptDevice("${d.ip}","${d.mac}")'>Adopt</button>`)
        : `<span class="muted">—</span>`;

    return `<tr data-state="${d.config_state || 'unknown'}">
      <td>${d.ip} ${vlanTag}</td>
      <td><code class="small">${d.mac}</code></td>
      <td><span class="vendor-label">${escapeHtml(vendor)}</span></td>
      <td>
        ${escapeHtml(d.model || d.http_title || 'Generic Device')}
        <div class="small muted">${escapeHtml(osHint)}</div>
      </td>
      <td><span class="status-pill">${d.config_state || 'unknown'}</span></td>
      <td>${adoptBtn}</td>
    </tr>`;
    }).join("");
  }catch(e){ scanStatus.textContent = "Scan failed"; UI.toaster.push("error","Scan failed",3000) }
}

/* Adopt discovered */
async function adoptDevice(ip, mac, vendor) {
  try {
    const res = await apiFetch("/devices/adopt", {
      method: "POST",
      body: JSON.stringify({ ip, mac }) // ← no need to send vendor; let backend decide
    });
    
    if (res.ok) {
      UI.toaster.push("success", "Device adopted", 2000);
      refreshLists();
    } else {
      const err = await res.text();
      UI.toaster.push("error", `Adoption failed: ${err}`, 4000);
    }
  } catch (e) {
    UI.toaster.push("error", "Adoption error", 3000);
  }
}

//   /*add device modal 2 */
//   async function addDevice() {
//   const device_id = document.getElementById("add_device_id").value.trim();
//   const ip = document.getElementById("add_ip").value.trim();
//   const model = document.getElementById("add_model").value.trim();

//   if (!device_id || !ip) {
//     UI.toaster.push("error", "Device ID and IP are required!", 3000);
//     return;
//   }

//   try {
//     const res = await apiFetch("/routers", {
//       method: "POST",
//       body: JSON.stringify({
//         device_id,
//         ip,
//         model
//       })
//     });

//     if (res.ok) {
//       UI.toaster.push("success", "Device added ✅", 3000);
//       refreshLists(); // ✅ Reload table instantly!
//     } else {
//       throw new Error(await res.text());
//     }

//   } catch (err) {
//     console.error(err);
//     UI.toaster.push("error", "Failed to add device ❌", 3000);
//   }
// }
/* backup/restore/reset helpers */
function restoreDevicePrompt(id){
  UI.modal({ html:`<h3>Restore ${id}</h3><label class="muted small">Backup file path (on controller)</label><input id="restore_path" class="input" /><div class="muted small">e.g. backups/${id}_backup_20251019.json</div>`,
    buttons:[
      {label:"Cancel",className:"btn ghost"},
      {label:"Restore", className:"btn", onClick: async ()=>{
        const path = document.getElementById("restore_path").value;
        await apiFetch(`/routers/${id}/restore`, { method:"POST", body: JSON.stringify({ backup_file: path }) });
        UI.toaster.push("info","Restore requested",2000);
      }}
    ]});
}
async function resetDevice(id){
  await apiFetch(`/devices/${id}/factory-reset`, { method:"POST" });
  UI.toaster.push("info","Reset issued",2000);
  closeDevicePanel();
  refreshLists();
}

/* initial load */
refreshLists();
scanNetwork();

// filtering
filterInput && filterInput.addEventListener("input", ()=>{
  const q = filterInput.value.toLowerCase();
  Array.from(deviceTBody.querySelectorAll("tr")).forEach(tr=>{
    tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
  });
});

// const { ERR_ABI_ENCODING } = require("web3");

let _copiedConfig = null; // clipboard for config copy/paste
var panelInterval = null;

function closeDevicePanel(){
  if(panelInterval) clearInterval(panelInterval);
  const panel = document.getElementById("deviceSidePanel");
  if(panel) panel.style.display = "none";
}

async function openDevicePanel(deviceId){
  const panel = document.getElementById("deviceSidePanel");
  const content = document.getElementById("panelContent");
  const title = document.getElementById("panelDeviceName");
  
  if(!panel || !content) return console.error("Device panel elements missing");

  if(title) title.innerText = deviceId; // temporary name
  panel.style.display = "block";
  content.innerHTML = "<div style='text-align:center;padding:20px;'>Loading device details...</div>";
  
  try{
    const res = await apiFetch(`/devices/${encodeURIComponent(deviceId)}`);
    if (!res.ok) {
      UI.toaster.push("error","Failed to load device details",3000);
      content.innerHTML = "<div style='text-align:center;padding:20px;color:#888;'>Failed to load device details</div>";
      return;
    }
    const d = await res.json();
    // If client not included but client_id exists, fetch client
    if (!d.client && d.client_id) {
      try {
        const clientRes = await apiFetch(`/clients/${d.client_id}`);
        if (clientRes.ok) {
          d.client = await clientRes.json();
        }
      } catch (e) {
        console.error("Failed to fetch client for device", e);
      }
    }
    const displayName = d.ssid || d.name || d.device_id;
    if(title) title.innerText = displayName;

    // device image
    const img = `<img class="device-icon" src="${getDeviceIcon(d.model)}" onerror="this.onerror=null;this.src='${API_URL}/static/icons/default.jpg'">`;

     // build details block
    const clients = d.client_count || (d.clients ? d.clients.length : 0);
    const uptime = d.uptime ? formatUptime(d.uptime) : (d.latest_config && d.latest_config.uptime ? d.latest_config.uptime : '—');

    const deviceType = d.device_type || ((d.model||'').toLowerCase().includes('ap') ? 'AP' : (d.model||'').toLowerCase().includes('switch') ? 'Switch' : 'Router');
    
    const clientDisplay = d.client 
      ? `${escapeHtml(d.client.name)} (${escapeHtml(d.client.location || 'N/A')})` 
      : (d.client_id ? `Client ID: ${d.client_id} (Not found)` : 'Not assigned');
    
    // Build type display with sector info for radio devices
    let typeDisplay = escapeHtml(d.device_type || deviceType);
    if ((d.device_type || '').toLowerCase() === 'radio' || (d.model && d.model.toLowerCase().includes('radio'))) {
      if (d.sector_id) {
        try {
          // Fetch all stations to find the one with the matching sector
          const stationsRes = await apiFetch('/stations');
          if (stationsRes.ok) {
            const stations = await stationsRes.json();
            let foundSector = null;
            let foundStation = null;
            
            for (const station of stations) {
              const sector = (station.sectors || []).find(s => s.id == d.sector_id);
              if (sector) {
                foundSector = sector;
                foundStation = station;
                break;
              }
            }
            
            if (foundSector && foundStation) {
              typeDisplay = `Radio([${escapeHtml(foundSector.name)} ${escapeHtml(foundStation.name)}])`;
            }
          }
        } catch (e) {
          console.error('Failed to fetch stations for sector info:', e);
        }
      }
    }
    
    // Interface Table
    const ifaceTable = d.interfaces && d.interfaces.length > 0 ? `
      <div class="subsection-title">Interfaces</div>
      <table class="table small">
        <thead><tr><th>Name</th><th>IP</th><th>MAC</th><th>State</th><th>Speed</th></tr></thead>
        <tbody>
          ${d.interfaces.map(i => `
            <tr>
              <td>${escapeHtml(i.name)}</td>
              <td>${escapeHtml(i.ip_address || 'N/A')}</td>
              <td>${escapeHtml(i.mac_address || 'N/A')}</td>
              <td><span class="status-${(i.oper_state || 'down').toLowerCase()}">${i.oper_state || 'down'}</span></td>
              <td>${i.speed ? i.speed + ' Mbps' : '—'}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>` : '<div class="muted small" style="margin-top:12px">No interface data</div>';

    // DHCP/DNS Info
    const dhcpInfo = d.dhcp_config ? `
      <div class="subsection-title">DHCP Server</div>
      <div class="details-grid" style="grid-template-columns: 1fr 1fr; margin-top: 8px;">
        <div><b>Status:</b> ${d.dhcp_config.enabled ? 'Enabled' : 'Disabled'}</div>
        ${d.dns_info && d.dns_info.server ? `<div><b>DNS:</b> ${escapeHtml(d.dns_info.server)}</div>` : ''}
        <div style="grid-column: 1 / -1;"><b>Range:</b> ${escapeHtml(d.dhcp_config.range_start)} - ${escapeHtml(d.dhcp_config.range_end)}</div>
      </div>
    ` : '';

    content.innerHTML = `<div style="display:flex;gap:12px;align-items:center">
        ${img}
        <div>
          <div style="font-weight:600">${escapeHtml(displayName)}</div>
          <div class="muted small">${escapeHtml(d.model || 'Unknown')}</div>
        </div>
      </div>

      <div class="details-grid">
        <div><b>MAC:</b> ${escapeHtml(d.mac_address || 'N/A')}</div>
        <div><b>IP:</b> ${escapeHtml(d.ip_address || '—')}</div>
        <div><b>SSID:</b> ${escapeHtml(d.ssid || (d.latest_config && d.latest_config.ssid) || '—')}</div>
        <div><b>Client:</b> ${clientDisplay}</div>
        <div><b>Firmware:</b> <span class="tag">${escapeHtml(d.firmware_version || '1.0.0')}</span></div>
        <div><b>Type:</b> ${typeDisplay}</div>
        <div><b>Clients:</b> ${clients}</div>
        ${d.snr ? `<div><b>SNR:</b> ${d.snr} dB</div>` : ''}
        <div><b>RX/s:</b> <span id="panelRx">0 B</span></div>
        <div><b>TX/s:</b> <span id="panelTx">0 B</span></div>
      </div>

      ${ifaceTable}
      ${dhcpInfo}

      <div class="subsection-title">Technician's Tools</div>
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; margin-bottom:12px; background:rgba(255,255,255,0.05); padding:10px; border-radius:4px;">
          <div><span class="muted small">Latency:</span> <b id="toolLatency">--</b></div>
          <div><span class="muted small">Jitter:</span> <b id="toolJitter">--</b></div>
          <div><span class="muted small">Packet Loss:</span> <b id="toolLoss">--</b></div>
          <div><span class="muted small">SNR:</span> <b id="toolSNR">${d.snr || '--'} dB</b></div>
          <div style="grid-column:1/-1"><span class="muted small">Bandwidth:</span> <b id="toolBw">--</b></div>
      </div>
      <div class="action-row">
        <button class="btn small" onclick="openPingTool('${d.ip_address || ''}')">Ping</button>
        <button class="btn small" onclick="openTracerouteTool('${d.ip_address || ''}')">Traceroute</button>
      </div>

      <div class="subsection-title">Actions</div>
      <div class="action-row">
        <button class="btn" onclick="restartDevice('${deviceId}')">Restart</button>
        <button class="btn ghost" onclick="forgetDevice('${deviceId}')">Forget</button>
        <button class="btn" onclick="openPropertiesModal('${deviceId}')">Change Properties</button>
        <button class="btn" onclick="upgradeDevicePrompt('${deviceId}', '${d.firmware_version || '1.0.0'}')">Upgrade Firmware</button>
        <button class="btn ghost" onclick="copyDeviceConfig('${deviceId}')">Copy Config</button>
        <button class="btn" onclick="pasteConfigToDevice('${deviceId}')">Paste Config</button>
        <button class="btn ghost" onclick="manageDeviceClient('${deviceId}')">Manage Client</button>
        <button class="btn ghost" onclick="resetDevice('${deviceId}')">Factory Reset</button>
      </div>

      <div id="panelMessages" style="margin-top:12px"></div>
    `;

    if(panelInterval) clearInterval(panelInterval);
    
    panelInterval = setInterval(()=>{
      // Simulate live traffic
      const rateRx = Math.floor(Math.random() * (50000 - 100) + 100);
      const rateTx = Math.floor(Math.random() * (20000 - 50) + 50);
      
      const elRx = document.getElementById("panelRx");
      const elTx = document.getElementById("panelTx");
      if(elRx) elRx.innerText = formatBytes(rateRx) + "/s";
      if(elTx) elTx.innerText = formatBytes(rateTx) + "/s";

      // Update Technician Tools metrics
      const elLat = document.getElementById("toolLatency");
      const elJit = document.getElementById("toolJitter");
      const elLoss = document.getElementById("toolLoss");
      const elSNR = document.getElementById("toolSNR");
      const elBw = document.getElementById("toolBw");

      if(elLat) elLat.innerText = Math.floor(Math.random() * 20 + 5) + " ms";
      if(elJit) elJit.innerText = (Math.random() * 5).toFixed(1) + " ms";
      if(elLoss) elLoss.innerText = (Math.random() < 0.95 ? "0%" : (Math.random() * 2).toFixed(1) + "%");
      if(elSNR) elSNR.innerText = Math.floor(Math.random() * (90 - 20) + 20) + " dB";
      if(elBw) elBw.innerText = "RX: " + formatBytes(rateRx) + "/s  TX: " + formatBytes(rateTx) + "/s";
    }, 1000);
  }catch(e){
    console.error(e);
    UI.toaster.push("error","Failed to open device panel",3000);
    content.innerHTML = "<div style='text-align:center;padding:20px;color:#888;'>Failed to load device details</div>";
  }
}

async function manageDeviceClient(deviceId){
  const res = await apiFetch(`/devices/${encodeURIComponent(deviceId)}`);
  if (!res.ok) return;
  const d = await res.json();
  
  // Fetch client details if needed for the modal display
  if (!d.client && d.client_id) {
      try {
        const cRes = await apiFetch(`/clients/${d.client_id}`);
        if(cRes.ok) d.client = await cRes.json();
      } catch(e){}
  }

  UI.modal({
    html: `
      <h3>Manage Client for ${deviceId}</h3>
      <div style="margin-bottom:12px">
        <b>Current Client:</b> ${d.client ? `${escapeHtml(d.client.name)} (${escapeHtml(d.client.location || 'N/A')})` : 'Not assigned'}
      </div>
      <label class="muted small">Select Client</label>
      <select id="clientSelect" class="input">
        <option value="">Not assigned</option>
      </select>
    `,
    buttons: [
      {label: "Cancel", className: "btn ghost"},
      {label: "Update", className: "btn", onClick: async () => {
        const clientId = document.getElementById("clientSelect").value;
        try {
          if (clientId) {
            await apiFetch(`/devices/${encodeURIComponent(deviceId)}/attach-client?client_id=${clientId}`, { method: "POST" });
            UI.toaster.push("success", "Device attached to client", 2000);
          } else {
            await apiFetch(`/devices/${encodeURIComponent(deviceId)}/detach-client`, { method: "POST" });
            UI.toaster.push("success", "Device detached from client", 2000);
          }
          await refreshLists();
          await openDevicePanel(deviceId);
          
          if (typeof refreshClients === "function") {
            refreshClients();
          }
        } catch (e) {
          UI.toaster.push("error", "Failed to update client attachment", 3000);
        }
      }}
    ]
  });
  
  // Populate client dropdown
  const clientRes = await apiFetch("/clients");
  if (clientRes.ok) {
    const clients = await clientRes.json();
    const select = document.getElementById("clientSelect");
    clients.forEach(c => {
      const option = document.createElement("option");
      option.value = c.id;
      option.textContent = `${c.name} (${c.location || 'N/A'})`;
      if (d.client && d.client.id == c.id) option.selected = true;
      else if (d.client_id == c.id) option.selected = true;
      select.appendChild(option);
    });
  }
}

function upgradeDevicePrompt(deviceId, currentVersion) {
  // Simple version increment logic for demo
  const parts = currentVersion.split('.');
  parts[parts.length-1] = parseInt(parts[parts.length-1]) + 1;
  const nextVersion = parts.join('.');

  UI.modal({
    html: `<h3>Upgrade Firmware</h3>
           <p>Current Version: <b>${currentVersion}</b></p>
           <p>Available Version: <b style="color:#33d39f">${nextVersion}</b></p>
           <p class="muted small">Device will reboot during this process.</p>`,
    buttons: [
      {label: "Cancel", className: "btn ghost"},
      {label: "Install Update", className: "btn", onClick: async () => {
         try {
           await apiFetch(`/devices/${encodeURIComponent(deviceId)}/upgrade?target_version=${nextVersion}`, { method: "POST" });
           UI.toaster.push("info", "Upgrade started. Device will go offline momentarily.", 4000);
           closeDevicePanel();
         } catch(e) { UI.toaster.push("error", "Upgrade request failed"); }
      }}
    ]
  });
}

function formatUptime(seconds){
  if (!seconds) return "—";
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hrs}h ${mins}m`;
}

async function restartDevice(deviceId){
  try{
    const res = await apiFetch(`/devices/${encodeURIComponent(deviceId)}/restart`, { method: "POST" });
    if (res.ok) UI.toaster.push("info","Restart scheduled",2000);
    else UI.toaster.push("error","Restart failed",3000);
  }catch(e){ UI.toaster.push("error","Restart error",3000) }
}

async function forgetDevice(deviceId){
  if(!confirm(`Forget device ${deviceId}? This deletes it from the controller.`)) return;
  try{
    const res = await apiFetch(`/devices/${encodeURIComponent(deviceId)}/forget`, { method: "POST" });
    if (res.ok){
      UI.toaster.push("success","Device forgotten",2000);
      closeDevicePanel();
      refreshLists();
    } else {
      UI.toaster.push("error","Forget failed",3000);
    }
  }catch(e){ UI.toaster.push("error","Forget error",3000) }
}

function openPropertiesModal(deviceId){
  apiFetch(`/devices/${encodeURIComponent(deviceId)}`).then(res => {
    if(!res.ok) throw new Error("Failed");
    return res.json();
  }).then(async d => {
    let clients = [];
    try { const cRes = await apiFetch("/clients"); if(cRes.ok) clients = await cRes.json(); } catch(e){}

    UI.modal({
      html: `
        <h3>Device Properties</h3>
        <label class="muted small">Device ID</label>
        <input class="input" value="${escapeHtml(d.device_id)}" disabled style="opacity:0.6" />
        
        <label class="muted small">Name / SSID</label>
        <input id="p_ssid" class="input" value="${escapeHtml(d.ssid || d.name || '')}" />
        
        <label class="muted small">Model</label>
        <input id="p_model" class="input" value="${escapeHtml(d.model || '')}" />
        
        <label class="muted small">Connection Type</label>
        <select id="p_connType" class="input">
          <option value="dhcp">DHCP (auto)</option>
          <option value="static">Static IP</option>
          <option value="pppoe">PPPoE</option>
        </select>
        <div id="p_connDetails" style="margin-top:8px"></div>

        <label class="muted small">Client</label>
        <select id="p_client" class="input">
          <option value="">Not assigned</option>
          ${clients.map(c => `<option value="${c.id}" ${d.client_id == c.id ? 'selected' : ''}>${escapeHtml(c.name)}</option>`).join("")}
        </select>
      `,
      buttons: [
        {label:"Cancel", className:"btn ghost"},
        {label:"Save", className:"btn", onClick: async ()=>{
           const ssid = document.getElementById("p_ssid").value;
           const model = document.getElementById("p_model").value;
           const connType = document.getElementById("p_connType").value;
           const clientId = document.getElementById("p_client").value;
           
           const payload = { model };
           if(connType === "static") {
             payload.ip_address = document.getElementById("p_ip").value;
             payload.credentials = {};
           } else if(connType === "pppoe") {
             payload.credentials = { username: document.getElementById("p_user").value, password: document.getElementById("p_pass").value };
             payload.ip_address = null;
           } else {
             payload.credentials = {};
             payload.ip_address = null;
           }
           
           try {
             await apiFetch(`/devices/${encodeURIComponent(deviceId)}`, { method:"PUT", body: JSON.stringify(payload) });
             if(ssid !== d.ssid) await apiFetch(`/devices/${encodeURIComponent(deviceId)}/rename-ssid`, { method:"POST", body: JSON.stringify({ssid}) });
             if(clientId != (d.client_id||"")) {
               if(clientId) await apiFetch(`/devices/${encodeURIComponent(deviceId)}/attach-client?client_id=${clientId}`, { method:"POST" });
               else await apiFetch(`/devices/${encodeURIComponent(deviceId)}/detach-client`, { method:"POST" });
             }
             UI.toaster.push("success", "Properties saved");
             openDevicePanel(deviceId);
             refreshLists();
           } catch(e) { UI.toaster.push("error", "Failed to save properties"); }
        }}
      ]
    });

    const sel = document.getElementById("p_connType");
    const det = document.getElementById("p_connDetails");
    const update = () => {
      if(sel.value === "static") det.innerHTML = `<label class="muted small">IP Address</label><input id="p_ip" class="input" value="${escapeHtml(d.ip_address||'')}" />`;
      else if(sel.value === "pppoe") det.innerHTML = `<label class="muted small">Username</label><input id="p_user" class="input" value="${escapeHtml((d.credentials&&(d.credentials.username||d.credentials.user))||'')}" /><label class="muted small">Password</label><input id="p_pass" class="input" type="password" placeholder="Change..." />`;
      else det.innerHTML = "";
    };
    sel.addEventListener("change", update);
    
    if(d.credentials && (d.credentials.username || d.credentials.user)) sel.value = "pppoe";
    else if(d.ip_address && d.ip_address !== "0.0.0.0" && !_simulatedIps.has(d.device_id)) sel.value = "static";
    else sel.value = "dhcp";
    update();
  }).catch(e=>{
    console.error(e);
    UI.toaster.push("error","Failed to load properties");
  });
}

async function copyDeviceConfig(deviceId){
  try{
    const res = await apiFetch(`/devices/${encodeURIComponent(deviceId)}`);
    if(!res.ok) { UI.toaster.push("error","Failed to fetch config",2000); return; }
    const d = await res.json();
    _copiedConfig = d.latest_config || {};
    UI.toaster.push("info","Config copied to clipboard",2000);
  }catch(e){ UI.toaster.push("error","Copy config failed",2000) }
}

async function pasteConfigToDevice(deviceId){
  if(!_copiedConfig){ UI.toaster.push("error","No config copied",2000); return; }
  try{
    const res = await apiFetch(`/devices/${encodeURIComponent(deviceId)}/copy-config`, { method:"POST", body: JSON.stringify({ source_device_id: "clipboard", fragment: _copiedConfig }) });
    // Note: copy-config endpoint expects source_device_id; we used src snapshot copy endpoint earlier which scheduled copy from another existing device.
    // As fallback, call rename-ssid or apply fragment directly via /routers/{id}/apply_config if available.
    if(res.ok){ UI.toaster.push("success","Config paste scheduled",2000); }
    else { UI.toaster.push("error","Paste failed",3000); }
  }catch(e){ UI.toaster.push("error","Paste error",3000) }
}

// --- Technician Tools ---

function openPingTool(host = "") {
  UI.modal({
    html: `
      <h3>Ping Tool</h3>
      <label class="muted small">IP Address or Hostname</label>
      <input id="pingHost" class="input" value="${escapeHtml(host)}" placeholder="e.g., 192.168.1.1 or google.com" />
      <pre id="pingOutput" class="code-block"></pre>
    `,
    buttons: [
      {label: "Close", className: "btn ghost"},
      {label: "Ping", className: "btn", onClick: () => {
        const host = document.getElementById('pingHost').value;
        if (!host) {
          UI.toaster.push('error', 'Host is required');
          return;
        }
        const outputEl = document.getElementById('pingOutput');
        outputEl.style.display = 'block';
        outputEl.innerHTML = `Pinging ${host}...\n\n`;
        
        // Simulation for devices in the list
        const targetDev = _deviceCache.find(d => d.device_id === host || d.ip_address === host || d.ip === host);
        if (targetDev) {
            let pings = 0;
            const ip = targetDev.ip_address || targetDev.ip || host;
            const interval = setInterval(() => {
                if (pings >= 4) {
                    clearInterval(interval);
                    const loss = targetDev.status === 'offline' ? 100 : 0;
                    const received = 4 - (4 * loss / 100);
                    if(loss > 0) outputEl.innerHTML = `Pinging ${ip} with 32 bytes of data:\nRequest timed out.\nRequest timed out.\nRequest timed out.\nRequest timed out.\n`;
                    outputEl.innerHTML += `\nPing statistics for ${ip}:\n    Packets: Sent = 4, Received = ${received}, Lost = ${4-received} (${loss}% loss)\n`;
                    return;
                }
                const ms = Math.floor(Math.random() * 5) + 1;
                outputEl.innerHTML += `Reply from ${ip}: bytes=32 time=${ms}ms TTL=64\n`;
                outputEl.scrollTop = outputEl.scrollHeight;
                pings++;
            }, 800);
            return false;
        }

        // Call backend API
        (async () => {
          try {
            const res = await apiFetch("/tools/ping", {
              method: "POST",
              body: JSON.stringify({ host })
            });
            if (res.ok) {
              const data = await res.json();
              outputEl.innerHTML = data.output || "No output returned.";
            } else {
              outputEl.innerHTML += "Ping request failed.";
            }
          } catch (e) {
            outputEl.innerHTML += `Error: ${e.message}`;
          }
        })();

        return false; // Prevent modal from closing
      }}
    ]
  });
}

function openTracerouteTool(host = "") {
  UI.modal({
    html: `
      <h3>Traceroute Tool</h3>
      <label class="muted small">IP Address or Hostname</label>
      <input id="traceHost" class="input" value="${escapeHtml(host)}" placeholder="e.g., 8.8.8.8" />
      <pre id="traceOutput" class="code-block"></pre>
    `,
    buttons: [
      {label: "Close", className: "btn ghost"},
      {label: "Trace", className: "btn", onClick: () => {
        const host = document.getElementById('traceHost').value;
        if (!host) {
          UI.toaster.push('error', 'Host is required');
          return;
        }
        const outputEl = document.getElementById('traceOutput');
        outputEl.style.display = 'block';
        outputEl.innerHTML = `Tracing route to ${host} over a maximum of 30 hops:\n\n`;

        // Call backend API
        (async () => {
          try {
            const res = await apiFetch("/tools/traceroute", {
              method: "POST",
              body: JSON.stringify({ host })
            });
            if (res.ok) {
              const data = await res.json();
              outputEl.innerHTML = data.output || "No output returned.";
            } else {
              outputEl.innerHTML += "Traceroute request failed.";
            }
          } catch (e) {
            outputEl.innerHTML += `Error: ${e.message}`;
          }
        })();
        return false; // Prevent modal from closing
      }}
    ]
  });
}

async function viewBackups() {
  try {
    const res = await apiFetch("/backups");
    if (!res.ok) throw new Error("Failed to fetch backups");
    const backups = await res.json();
    
    const rows = backups.map(b => `
      <tr>
        <td>${escapeHtml(b.device_id)}</td>
        <td>${new Date(b.timestamp).toLocaleString()}</td>
        <td>${escapeHtml(b.note || '—')}</td>
        <td><button class="btn small ghost" onclick="restoreDevicePrompt('${b.device_id}')">Restore</button></td>
      </tr>
    `).join("");

    UI.modal({
      html: `<h3>System Backups</h3>
             <div style="max-height:400px; overflow:auto">
               <table class="table"><thead><tr><th>Device</th><th>Time</th><th>Note</th><th>Action</th></tr></thead><tbody>${rows || '<tr><td colspan="4">No backups found</td></tr>'}</tbody></table>
             </div>`,
      buttons: [{label: "Close", className: "btn"}]
    });
  } catch (e) {
    UI.toaster.push("error", "Could not load backups");
  }
}

// Expose functions to window for inline HTML event handlers
window.openDevicePanel = openDevicePanel;
window.closeDevicePanel = closeDevicePanel;
window.manageDeviceClient = manageDeviceClient;
window.restartDevice = restartDevice;
window.forgetDevice = forgetDevice;
window.openPropertiesModal = openPropertiesModal;
window.upgradeDevicePrompt = upgradeDevicePrompt;
window.copyDeviceConfig = copyDeviceConfig;
window.pasteConfigToDevice = pasteConfigToDevice;
window.resetDevice = resetDevice;
window.openPingTool = openPingTool;
window.openTracerouteTool = openTracerouteTool;
window.adoptDevice = adoptDevice;
window.restoreDevicePrompt = restoreDevicePrompt;
window.viewBackups = viewBackups;
window.showBackupDetails = showBackupDetails;