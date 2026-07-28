/* ui/dashboard.js */

// Global state
let devices = [];
let stations = [];
let topologyNodes = [];
let topologyLinks = [];
let hoveredNode = null;

document.addEventListener("DOMContentLoaded", () => {
  initDashboard();
});

async function initDashboard() {
  await fetchDevices();
  await updateDashboardStats();
  await loadRecentAlerts();
  await loadTopologyData();
  await loadDeviceInterfaces();
  initTopology();
  
  // Poll for updates
  setInterval(async () => {
    await fetchDevices();
    await updateDashboardStats();
    await loadRecentAlerts();
    await loadTopologyData();
    await loadDeviceInterfaces();
    drawTopology();
  }, 5000);
}

async function loadTopologyData() {
  try {
    const sRes = await apiFetch("/stations");
    if (sRes.ok) {
      stations = await sRes.json();
    } else {
      stations = [];
    }
  } catch (err) {
    console.warn("Topology station fetch failed", err);
    stations = [];
  }
}

async function loadDeviceInterfaces() {
  // Fetch interfaces with neighbor data for all devices to support topology links
  try {
    const res = await apiFetch("/devices");
    if (!res.ok) return;
    const devs = await res.json();
    // For each device, fetch its interfaces (including neighbors) 
    // but only for devices that might have connections (routers, radios, switches)
    const interfacePromises = devs.map(async (dev) => {
      try {
        // Guard: Skip interface fetch for sectors and other virtual devices that don't have physical interfaces
        if (dev.device_id.startsWith('SEC-') || dev.device_type === 'sector') {
          console.log(`Skipping interface fetch for virtual device: ${dev.device_id}`);
          return null;
        }
        const ifaceRes = await apiFetch(`/routers/devices/${encodeURIComponent(dev.device_id)}/interfaces`);
        if (ifaceRes.ok) {
          const ifaces = await ifaceRes.json();
          return { device_id: dev.device_id, interfaces: ifaces };
        }
      } catch (e) {
        // Skip failed interface fetches
      }
      return null;
    });
    const results = (await Promise.all(interfacePromises)).filter(r => r !== null);
    // Merge interface data into devices array
    results.forEach(r => {
      const dev = devices.find(d => d.device_id === r.device_id);
      if (dev) {
        dev.interfaces = r.interfaces;
      }
    });
  } catch (err) {
    console.warn("Device interface fetch failed", err);
  }
}

async function fetchDevices() {
  try {
    const res = await apiFetch("/devices");
    if (res.ok) {
      devices = await res.json();
    }
  } catch (e) {
    console.error("Failed to fetch devices", e);
  }
}

// function updateDashboardStats() {
async function updateDashboardStats() {
  // Update counters
  const total = devices.length;
  const online = devices.filter(d => d.status === 'online').length;
  
  const elTotal = document.getElementById('totalDevices');
  if(elTotal) elTotal.textContent = total;
  
  // Fetch actual client (customer) count from the system
  try {
      const cRes = await apiFetch("/clients");
      if (cRes.ok) {
          const clientsList = await cRes.json();
          if(document.getElementById('totalClients')) document.getElementById('totalClients').textContent = clientsList.length;
      }
  } catch(e) { console.warn("Failed to fetch client count", e); }
  
  // Device Breakdown
  const breakdown = {
    'Router': 0,
    'Switch': 0,
    'Radio': 0,
    'Gateway': 0,
    'Access Point': 0,
    'Camera': 0
  };

  devices.forEach(d => {
    let type = (d.device_type || '').toLowerCase();
    const model = (d.model || '').toLowerCase();

    if (!type || type === 'other') {
        if (model.includes('radio') || model.includes('beam') || model.includes('station') || model.includes('grid') || model.includes('lhg')) type = 'radio';
        else if (model.includes('router')) type = 'router';
        else if (model.includes('switch')) type = 'switch';
        else if (model.includes('gateway')) type = 'gateway';
        else if (model.includes('camera') || model.includes('cctv')) type = 'camera';
        else if (model.includes('ap') || model.includes('access point')) type = 'access point';
    }

    if (type.includes('router')) breakdown['Router']++;
    else if (type.includes('switch')) breakdown['Switch']++;
    else if (type.includes('radio')) breakdown['Radio']++;
    else if (type.includes('gateway')) breakdown['Gateway']++;
    else if (type.includes('camera')) breakdown['Camera']++;
    else if (type.includes('ap') || type.includes('access point')) breakdown['Access Point']++;
  });
  
  const bdGrid = document.getElementById('deviceBreakdown');
  if (bdGrid) {
      bdGrid.innerHTML = `
        <div class="stat-box"><div class="big">${breakdown['Router']}</div><div class="muted small">Routers</div></div>
        <div class="stat-box"><div class="big">${breakdown['Switch']}</div><div class="muted small">Switches</div></div>
        <div class="stat-box"><div class="big">${breakdown['Radio']}</div><div class="muted small">Radios</div></div>
        <div class="stat-box"><div class="big">${breakdown['Gateway']}</div><div class="muted small">Gateways</div></div>
        <div class="stat-box"><div class="big">${breakdown['Access Point']}</div><div class="muted small">APs</div></div>
        <div class="stat-box"><div class="big">${breakdown['Camera']}</div><div class="muted small">Cameras</div></div>
      `;
  }

  // Simulated CPU/Mem (Visual only)
  const cpu = Math.floor(Math.random() * 30 + 10);
  const mem = Math.floor(Math.random() * 40 + 20);
  const elCpu = document.getElementById('cpuValue');
  if(elCpu) elCpu.textContent = cpu + "%";
  const elCpuBar = document.getElementById('cpuBar');
  if(elCpuBar) elCpuBar.style.width = cpu + "%";
  
  const elMem = document.getElementById('memValue');
  if(elMem) elMem.textContent = mem + "%";
  const elMemBar = document.getElementById('memBar');
  if(elMemBar) elMemBar.style.width = mem + "%";
  
   // Real Analytics Sync
    try {
    const aRes = await apiFetch("/analytics");
    if (aRes.ok) {
        const analytics = await aRes.json();
        const usage = analytics.usage || { avg_tx_mbps: 0, avg_rx_mbps: 0, total_data_gb: 0, active_devices_24h: 0 };

        // Add a small frontend jitter (+/- 2%) so the numbers move slightly even between poll intervals
        const jitter = () => (0.98 + Math.random() * 0.04);
        const displayTx = (usage.avg_tx_mbps * jitter()).toFixed(1);
        const displayRx = (usage.avg_rx_mbps * jitter()).toFixed(1);
        
        if(document.getElementById('ana-active')) document.getElementById('ana-active').textContent = usage.active_devices_24h;
        if(document.getElementById('ana-tx')) document.getElementById('ana-tx').textContent = displayTx + " Mbps";
        if(document.getElementById('ana-rx')) document.getElementById('ana-rx').textContent = displayRx + " Mbps";
        // Total Data Usage should not have jitter to ensure it never appears to drop
        if(document.getElementById('ana-data')) document.getElementById('ana-data').textContent = usage.total_data_gb.toFixed(2) + " GB";
    }
    } catch (e) {
    console.warn("Dashboard analytics sync failed", e);
    }
}

const recentAlertsEl = document.getElementById('recentAlerts');

function getRecentAlertIcon(activityType) {
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

async function loadRecentAlerts() {
  if (!recentAlertsEl) return;
  try {
    const res = await apiFetch('/logs');
    if (!res.ok) return;
    const logs = await res.json();
    const latest = (Array.isArray(logs) ? logs : []).slice(0, 5);

    if (latest.length === 0) {
      recentAlertsEl.innerHTML = `<div style="color:#888; padding:10px;">No recent alerts</div>`;
      return;
    }

    recentAlertsEl.innerHTML = latest.map(log => {
      const ts = new Date(log.timestamp || log.ts || Date.now()).toLocaleTimeString();
      const icon = getRecentAlertIcon(log.activity_type || log.type);
      const label = (log.activity_type || log.type || 'event').replace(/_/g, ' ');
      const message = log.message || `${label}${log.device_id ? ` on ${log.device_id}` : ''}`;
      const meta = [log.username && `user: ${log.username}`, log.device_id && `device: ${log.device_id}`].filter(Boolean).join(' • ');

      return `<div><div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;"><span style="font-size:0.95rem;">${icon} <strong>${message}</strong></span><span class="muted small">${ts}</span></div>${meta ? `<div class="muted small" style="margin-top:6px;">${meta}</div>` : ''}</div>`;
    }).join('');
  } catch (err) {
    console.error('Failed to load recent alerts', err);
  }
}

// --- Topology ---

const canvas = document.getElementById('networkMap');
let ctx = null;
let width, height;

function initTopology() {
  if(!canvas) return;
  ctx = canvas.getContext('2d');
  
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);
  
  canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    
    const previousHovered = hoveredNode;
    hoveredNode = null;
    // Iterate in reverse to catch top nodes first
    for (let i = topologyNodes.length - 1; i >= 0; i--) {
      const node = topologyNodes[i];
      const dx = x - node.x;
      const dy = y - node.y;
      const hitRadius = (node.r || 20) + 4;
      if (dx * dx + dy * dy <= hitRadius * hitRadius) {
        hoveredNode = node;
        break;
      }
    }

    if (hoveredNode !== previousHovered) {
      drawTopology();
    }

    // Show tooltip if hovered
    if (hoveredNode) {
        canvas.style.cursor = 'pointer';
        showTooltip(e.clientX, e.clientY, hoveredNode);
    } else {
        canvas.style.cursor = 'default';
        hideTooltip();
    }
  });
  
  drawTopology();
}

function resizeCanvas() {
  if(!canvas) return;
  const parent = canvas.parentElement;
  const rect = parent.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;

  width = rect.width;
  // Height will be set dynamically in drawTopology based on tree depth
  height = 1200;

  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  drawTopology();
}

function isRadio(d) {
    const model = (d.model || '').toLowerCase();
    const type = (d.device_type || '').toLowerCase();
    return (type === 'radio' || model.includes('radio') || model.includes('beam') || model.includes('station') || model.includes('grid') || model.includes('lhg')) && type !== 'sector';
}

function isCPE(d) {
    return !!d.client_id;
}

// --- Tree Layout Engine ---

/**
 * Build a parent-child map from devices using parent_device_id.
 * Returns Map<parentId, Array<childDevice>>
 */
function buildParentMap(allDevices) {
    const map = new Map();
    const addMapping = (key, child) => {
        if (!key || key === "null" || key === "undefined") return;
        let normalized = key.toString().toLowerCase().trim();
        if (!map.has(normalized)) map.set(normalized, []);
        if (!map.get(normalized).includes(child)) map.get(normalized).push(child);

        // MIRROR LOGIC: Ensure physical parents also support the synthetic prefix 
        // currently used by Sectors. This unifies the Radio->Router and Sector->Radio paths.
        if (!normalized.startsWith('sec-') && !normalized.startsWith('stn-')) {
            const synthetic = `sec-${normalized}`;
            if (!map.has(synthetic)) map.set(synthetic, []);
            if (!map.get(synthetic).includes(child)) map.get(synthetic).push(child);
        }
    };

    allDevices.forEach(d => {
        const type = (d.device_type || "").toString().toLowerCase();
        const deviceId = (d.device_id || "").toString().toLowerCase().trim();
        
        if (type === 'sector' || deviceId.startsWith('sec-')) return;

        // HIERARCHICAL PRIORITY: Map only to the most specific parent found.
        // This prevents the "Greedy Station" problem where a tower steals children from a radio.
        const directPid = (d.parent_device_id || d.parentId || "").toString().toLowerCase().trim();
        
        if (directPid && directPid !== "null") {
            addMapping(directPid, d);
        } else if (d.sector_id) {
            addMapping(`sec-${d.sector_id}`, d);
        } else if (d.station_id) {
            addMapping(`stn-${d.station_id}`, d);
        }
    });
    return map;
}

/**
 * Recursively measure subtree width for each node.
 * Leaf nodes get a minimum width. Parent width = sum of children + padding.
 */
function measureSubtree(parentNodeId, parentMap, minLeafWidth = 90, siblingGap = 30, visited = new Set()) {
    const id = parentNodeId.toString().toLowerCase().trim();
    if (visited.has(id)) return minLeafWidth;
    visited.add(id);
    
    // Generate all possible lookup keys for this parent node
    const lookupKeys = new Set([id]);
    // If it's a physical device ID, also check for children linked via 'sec-' prefix
    if (!id.startsWith('sec-') && !id.startsWith('stn-')) {
        lookupKeys.add(`sec-${id}`);
    }

    // Aggregate children from all possible parent ID formats
    const childMap = new Map();
    lookupKeys.forEach(key => { // Iterate over the generated lookup keys
        const found = parentMap.get(key) || [];
        found.forEach(c => { // For each child found under this key
            // Use device_id as the stable unique key for deduplication
            const ck = (c.device_id || Math.random().toString()).toString().toLowerCase().trim();
            if (!childMap.has(ck)) childMap.set(ck, c); // Add to childMap if not already present
        });
    });

    const children = Array.from(childMap.values());

    if (children.length === 0) {
        return minLeafWidth;
    }
    let total = 0;
    children.forEach((child, idx) => {
        const childId = (child.device_id || child.id || "").toString().toLowerCase().trim();
        // Pass the visited set down to deeper levels
        total += measureSubtree(childId, parentMap, minLeafWidth, siblingGap, visited);
        if (idx < children.length - 1) total += siblingGap;
    });
    return total;
}

/**
 * Place children under a parent node using pre-order traversal.
 * Mutates topologyNodes array.
 */
function placeChildren(parentNode, tier, parentMap, allDevices, placedIds, siblingGap = 30, verticalStep = 100) {
    const rawData = parentNode.data;
    if (!rawData) return;

    const lookupKeys = new Set(); // Use a Set to avoid duplicate lookups
    
    // Add all possible ways this parent node might be referenced by its children
    // 1. Synthetic IDs for infrastructure nodes
    if (parentNode.stationId) lookupKeys.add(`stn-${parentNode.stationId.toString().toLowerCase()}`);
    if (parentNode.sectorId) lookupKeys.add(`sec-${parentNode.sectorId.toString().toLowerCase()}`);
    
    // 2. Logical device_id (for physical devices)
    if (rawData.device_id) {
        const dId = rawData.device_id.toString().toLowerCase().trim();
        lookupKeys.add(dId);
        // Also add the 'sec-' prefixed version for physical devices,
        // as children might reference them this way (mirroring Sector->Radio logic).
        lookupKeys.add(`sec-${dId}`);
    }
    
    // 3. Fallback to numeric database ID (if present and relevant)
    if (rawData.id && typeof rawData.id === 'number') lookupKeys.add(rawData.id.toString().toLowerCase());

    if (lookupKeys.size === 0) return;
    
    const childMap = new Map();
    lookupKeys.forEach(key => {
        const found = parentMap.get(key) || [];
        found.forEach(c => {
            // Use device_id as the stable unique key for deduplication
            const cKey = (c.device_id || Math.random().toString()).toString().toLowerCase().trim(); // Fallback to random if device_id is somehow missing
            if (!childMap.has(cKey)) childMap.set(cKey, c);
        });
    });

    const children = Array.from(childMap.values());

    if (children.length === 0) return;

    // Compute total width of this subtree
    let totalWidth = 0;
    const childWidths = children.map(child => {
        const cid = (child.device_id || child.id || "").toString().toLowerCase().trim();
        // Start measurement with a fresh visited set for this subtree
        const w = measureSubtree(cid, parentMap, 90, siblingGap, new Set());
        return w;
    });
    childWidths.forEach((w, idx) => {
        totalWidth += w;
        if (idx < childWidths.length - 1) totalWidth += siblingGap;
    });

    let currentX = parentNode.x - totalWidth / 2;
    children.forEach((child, idx) => {
        const cid = (child.device_id || child.id || "").toString().toLowerCase().trim();
        const childWidth = childWidths[idx];
        const childX = currentX + childWidth / 2;
        
        const nextVerticalStep = tier > 2 ? 100 : verticalStep;
        const childY = parentNode.y + nextVerticalStep;

        const nodeType = isRadio(child) ? 'radio' : (isCPE(child) ? 'cpe' : 'device');
        const cNode = { 
            x: childX, 
            y: childY, 
            r: isCPE(child) ? 9 : 10, 
            type: nodeType, 
            label: child.name || child.device_id, 
            status: child.status, 
            data: child 
        };
        
        if (!placedIds.has(cid)) {
            topologyNodes.push(cNode);
            placedIds.add(cid);
            
            const linkType = isRadio(child) ? 'wireless' : (isCPE(child) ? 'cpe' : 'wired');
            const linkColor = isRadio(child) 
                ? (child.status === 'online' ? '#10b981' : '#ef4444') 
                : (isCPE(child) ? '#0ea5e9' : '#64748b');
                
            topologyLinks.push({ n1: parentNode, n2: cNode, type: linkType, color: linkColor });
            
            // Recurse deeper once with the adjusted vertical step
            placeChildren(cNode, tier + 1, parentMap, allDevices, placedIds, siblingGap, nextVerticalStep);
        }
        
        currentX += childWidth + siblingGap;
    });
}

function normalizeId(id) {
    if (!id) return "";
    return id.toString().toLowerCase().trim()
             .replace(/^sec-/, "")
             .replace(/^stn-/, "");
}

/**
 * Place orphan LLDP devices that are not in the tree yet.
 * These are devices discovered as neighbors but lack station_id/sector_id/parent_device_id.
 */
function placeOrphanLLDPDevices(allDevices, placedIds) {
    const orphanNodes = [];
    
    allDevices.forEach(dev => {
        if (!dev.interfaces) return;
        const devId = (dev.device_id || "").toString().toLowerCase().trim();
        
        dev.interfaces.forEach(iface => {
            if (!iface.neighbors || iface.neighbors.length === 0) return;
            
            iface.neighbors.forEach(nb => {
                const nid = nb.neighbor_id || nb.device_id || nb.mac || nb.remote_mac || '';
                if (!nid) return;
                
                // Find the actual neighbor device object
                const neighborDevice = allDevices.find(d => {
                    if (d.device_id === dev.device_id) return false;
                    if (d.device_id && d.device_id.toLowerCase() === nid.toLowerCase()) return true;
                    if (d.mac_address) {
                        const devMac = d.mac_address.toUpperCase().replace(/-/g, ':');
                        const nbMac = nid.toUpperCase().replace(/-/g, ':');
                        if (devMac === nbMac) return true;
                    }
                    return false;
                });
                
                if (!neighborDevice) return;
                
                const neighborId = (neighborDevice.device_id || "").toString().toLowerCase().trim();
                
                // Skip if already placed in the tree
                if (placedIds.has(neighborId)) return;
                
                // Skip if this device also has a parent_device_id pointing to someone in the tree
                // (it will be drawn via the tree layout instead)
                const neighborParent = (neighborDevice.parent_device_id || "").toString().toLowerCase().trim();
                if (neighborParent && placedIds.has(neighborParent)) return;
                
                // Find the source node in topologyNodes
                const src = topologyNodes.find(n => {
                    const sid = (n.data?.device_id || n.data?.id || "").toString().toLowerCase().trim();
                    return sid === devId;
                });
                
                if (!src) return;
                
                // Place orphan with a radial offset from source
                const angle = (orphanNodes.length * 0.7) + 0.5; // spread them out
                const distance = 140;
                const ox = src.x + Math.cos(angle) * distance;
                const oy = src.y + Math.sin(angle) * distance;
                
                const nodeType = isRadio(neighborDevice) ? 'radio' : (isCPE(neighborDevice) ? 'cpe' : 'device');
                const oNode = {
                    x: ox,
                    y: oy,
                    r: isCPE(neighborDevice) ? 9 : 10,
                    type: nodeType,
                    label: neighborDevice.name || neighborDevice.device_id,
                    status: neighborDevice.status,
                    data: neighborDevice,
                    isOrphan: true
                };
                
                topologyNodes.push(oNode);
                placedIds.add(neighborId);
                orphanNodes.push(oNode);
                
                // Add LLDP link to buffer
                topologyLinks.push({ n1: src, n2: oNode, type: 'lldp', color: '#f59e0b' });
            });
        });
    });
}

/**
 * Draw LLDP/CDP neighbor links between already-placed devices.
 * Skips links where a parent-child relationship already exists.
 */
function drawNeighborLinks(allDevices, placedIds) {
    const drawnLinks = new Set();
    const parentChildPairs = new Set();

    // Build set of existing parent-child pairs
    allDevices.forEach(d => {
        const pid = (d.parent_device_id || "").toString().toLowerCase().trim();
        const did = (d.device_id || "").toString().toLowerCase().trim();
        if (pid && pid !== "null") {
            const ids = [pid, did].sort();
            parentChildPairs.add(ids.join('|'));
        }
    });

    allDevices.forEach(dev => {
        if (!dev.interfaces) return;
        const devId = (dev.device_id || "").toString().toLowerCase().trim();

        dev.interfaces.forEach(iface => {
            if (!iface.neighbors || iface.neighbors.length === 0) return;

            iface.neighbors.forEach(nb => {
                const nid = nb.neighbor_id || nb.device_id || nb.mac || nb.remote_mac || '';
                if (!nid) return;

                const neighborDevice = allDevices.find(d => {
                    if (d.device_id === dev.device_id) return false;
                    if (d.device_id && d.device_id.toLowerCase() === nid.toLowerCase()) return true;
                    if (d.mac_address) {
                        const devMac = d.mac_address.toUpperCase().replace(/-/g, ':');
                        const nbMac = nid.toUpperCase().replace(/-/g, ':');
                        if (devMac === nbMac) return true;
                    }
                    return false;
                });

                if (!neighborDevice) return;
                
                const neighborId = (neighborDevice.device_id || "").toString().toLowerCase().trim();
                
                // Skip if parent-child link already exists
                const pairKey = [devId, neighborId].sort().join('|');
                if (parentChildPairs.has(pairKey)) return;

                const src = topologyNodes.find(n => {
                    const sid = (n.data?.device_id || n.data?.id || "").toString().toLowerCase().trim();
                    return sid === devId;
                });
                const dst = topologyNodes.find(n => {
                    const sid = (n.data?.device_id || n.data?.id || "").toString().toLowerCase().trim();
                    return sid === neighborId;
                });

                if (src && dst) {
                    if (!drawnLinks.has(pairKey)) {
                        drawnLinks.add(pairKey);
                        topologyLinks.push({ n1: src, n2: dst, type: 'lldp', color: '#f59e0b' });
                    }
                }
            });
        });
    });
}

async function drawTopology() {
    if(!ctx) return;
    topologyNodes = [];
    topologyLinks = [];
    
    if (stations.length === 0) {
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#667085";
      ctx.textAlign = "center";
      ctx.font = "14px Inter";
      ctx.fillText("No infrastructure defined. Add a Station to begin.", width / 2, height / 2);
      return;
    }

    const parentMap = buildParentMap(devices);
    const placedIds = new Set();

    const stationSpacing = width / (stations.length + 1);
    
    stations.forEach((station, sIdx) => {
      const stX = stationSpacing * (sIdx + 1);
      const stY = 60;
      const stNode = { x: stX, y: stY, type: 'tower', label: station.name, r: 25, status: 'online', stationId: station.id, data: { ...station, device_id: `STN-${station.id}` } };
      topologyNodes.push(stNode);

      (station.sectors || []).forEach((sec, secIdx) => { // Reduced spacing
        // Offset sectors horizontally to prevent overlap with station main devices
        const secX = stX + (secIdx * 120) - (((station.sectors.length - 1) * 120) / 2);
        const secY = stY + 140; // Increased vertical gap to separate sectors from tower main devices
        const secNode = { x: secX, y: secY, type: 'sector', label: sec.name, r: 15, status: 'online', sectorId: sec.id, data: { ...sec, device_id: `SEC-${sec.id}` } };
        topologyNodes.push(secNode);
        topologyLinks.push({ n1: stNode, n2: secNode, type: 'solid', color: '#8b5cf6' });

        // Start recursive placement for items directly under this sector
        placeChildren(secNode, 2, parentMap, devices, placedIds, 50, 120);
      });

      // Also start recursive placement for devices linked to the station but NOT a sector
      // Use a larger initial vertical step to clear the sector row
      placeChildren(stNode, 1, parentMap, devices, placedIds, 60, 220);
    });

    // Post-Placement: Draw Station Backhaul/Physical links
    // We do this after all nodes (recursive children included) have been placed
    stations.forEach(station => {
        if (station.link_device_id) {
            const stNode = topologyNodes.find(n => n.type === 'tower' && n.stationId === station.id);
            const uplinkDevNode = topologyNodes.find(n => {
                if (!n.data || !n.data.device_id) return false;
                const nId = n.data.device_id.toLowerCase().trim();
                const sLinkId = station.link_device_id.toLowerCase().trim();
                return nId === sLinkId || 
                       nId === `sec-${sLinkId}` || 
                       nId === `stn-${sLinkId}`;
            });

            if (stNode && uplinkDevNode) {
                topologyLinks.push({ n1: uplinkDevNode, n2: stNode, type: 'lldp', color: '#8b5cf6' });
            }
        }
    });

    // Place orphan LLDP devices that weren't caught by the tree
    placeOrphanLLDPDevices(devices, placedIds);
    
    // Draw remaining LLDP links between placed devices (skip parent-child duplicates)
    drawNeighborLinks(devices, placedIds);
    
    // Compute max depth for dynamic canvas height
    let maxY = 200;
    topologyNodes.forEach(n => {
        if (n.y > maxY) maxY = n.y; // Find the maximum Y coordinate among all nodes
    });
    const desiredHeight = Math.max(1200, maxY + 150); // Ensure a minimum height and add padding
    if (desiredHeight !== height) { // Only update if height actually changes
        height = Math.floor(desiredHeight); // Update the global height variable
        const dpr = window.devicePixelRatio || 1; // Get device pixel ratio
        canvas.height = Math.floor(height * dpr); // Set canvas element's height
        canvas.style.height = `${height}px`; // Set canvas style height for correct scaling
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0); // Apply DPR transform
    }

    // Draw Links first
    topologyLinks.forEach(link => drawLink(link.n1, link.n2, link.type, link.color));

    // Draw Nodes on top
    topologyNodes.forEach(node => drawNode(node));
}

function drawLink(n1, n2, type, color) {
    ctx.beginPath();
    ctx.moveTo(n1.x, n1.y);
    ctx.lineTo(n2.x, n2.y);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    
    if (type === 'wireless') {
        ctx.setLineDash([5, 5]);
    } else if (type === 'lldp') {
        ctx.setLineDash([10, 3, 2, 3]); // Dash-dot pattern for physical discovery
        ctx.strokeStyle = color;
    } else if (type === 'broken') {
        ctx.setLineDash([2, 2]);
        ctx.strokeStyle = '#ef4444';
    } else if (type === 'cpe') {
        ctx.setLineDash([]);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2.5;
    } else {
        ctx.setLineDash([]);
    }
    
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.lineWidth = 2;
}

function drawNode(node) {
    ctx.beginPath();
    ctx.arc(node.x, node.y, node.r, 0, 2 * Math.PI);
    
    // Determine fill color based on type and status
    let fillColor;
    if (node.type === 'tower') {
        fillColor = node.status === 'online' ? '#6366f1' : '#a5b4fc'; // Lighter purple for offline tower
    } else if (node.type === 'sector') {
        fillColor = node.status === 'online' ? '#8b5cf6' : '#c4b5fd'; // Lighter purple for offline sector
    } else if (node.type === 'radio') {
        fillColor = node.status === 'online' ? '#10b981' : '#a7f3d0'; // Lighter green for offline radio
    } else if (node.type === 'cpe') {
        fillColor = node.status === 'online' ? '#f59e0b' : '#fed7aa'; // Lighter orange for offline CPE
    } else {
        fillColor = node.status === 'online' ? '#3b82f6' : '#bfdbfe'; // Lighter blue for offline generic device
    }
    ctx.fillStyle = fillColor;
    
    // Highlight if hovered
    if (hoveredNode === node) {
        ctx.shadowBlur = 10;
        ctx.shadowColor = ctx.fillStyle;
    } else {
        ctx.shadowBlur = 0;
    }
    
    ctx.fill();
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Draw CPE indicator (small inner square)
    if (node.type === 'cpe') {
        ctx.fillStyle = '#fff';
        const sqSize = 4;
        ctx.fillRect(node.x - sqSize/2, node.y - sqSize/2, sqSize, sqSize);
    }

    // Draw Label (Only if clearly defined)
    if (node.label) {
        ctx.fillStyle = "#475467";
        ctx.font = node.type === 'tower' ? "bold 11px Inter" : "10px Inter";
        ctx.textAlign = "center";
        const labelY = node.y + node.r + 16;
        ctx.fillText(node.label, node.x, labelY);
    }

    ctx.shadowBlur = 0;
}

// Tooltip
let tooltip = document.getElementById('topoTooltip');
if (!tooltip) {
    tooltip = document.createElement('div');
    tooltip.id = 'topoTooltip';
    tooltip.style.position = 'fixed';
    tooltip.style.background = 'rgba(15, 23, 42, 0.95)';
    tooltip.style.color = '#fff';
    tooltip.style.padding = '10px';
    tooltip.style.borderRadius = '6px';
    tooltip.style.fontSize = '12px';
    tooltip.style.pointerEvents = 'none';
    tooltip.style.display = 'none';
    tooltip.style.zIndex = '1000';
    tooltip.style.border = '1px solid rgba(255,255,255,0.1)';
    tooltip.style.boxShadow = '0 4px 6px -1px rgba(0, 0, 0, 0.1)';
    document.body.appendChild(tooltip);
}

function showTooltip(x, y, node) {
    // Prioritize the actual device type from the system over the topology node category
    let displayType = node.type;
    if (node.data && node.data.device_type) {
        displayType = node.data.device_type;
    }

    let html = `<div style="font-weight:600; margin-bottom:4px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:4px;">${node.label}</div>`;
    
    // Type badge
    let typeBadge = '';
    if (node.type === 'cpe') typeBadge = `<span style="background:#f59e0b; color:#000; padding:1px 6px; border-radius:4px; font-size:10px; font-weight:600; margin-left:6px;">CPE</span>`;
    else if (node.type === 'radio') typeBadge = `<span style="background:#10b981; color:#fff; padding:1px 6px; border-radius:4px; font-size:10px; font-weight:600; margin-left:6px;">RADIO</span>`;
    html += `<div style="color:#94a3b8">Type: ${displayType}${typeBadge}</div>`;
    
    if (node.data) {
        html += `<div>IP: <span style="color:#e2e8f0">${node.data.ip_address || 'N/A'}</span></div>`;
        html += `<div>MAC: <span style="color:#e2e8f0">${node.data.mac_address || 'N/A'}</span></div>`;
        
        const statusColor = node.status === 'online' ? '#34d399' : '#f87171';
        html += `<div>Status: <span style="color:${statusColor}">● ${node.status.toUpperCase()}</span></div>`;
        
        // CPE Client info
        if (node.type === 'cpe' && node.data.client) {
            html += `<div style="margin-top:4px; padding-top:4px; border-top:1px solid rgba(255,255,255,0.1)"><span style="color:#f59e0b; font-weight:600;">CPE Client:</span> ${node.data.client.name}</div>`;
            if (node.data.client.location) {
                html += `<div class="small" style="color:#94a3b8; font-size:10px;">${node.data.client.location}</div>`;
            }
        } else if (node.data.client) {
            html += `<div style="margin-top:4px; padding-top:4px; border-top:1px solid rgba(255,255,255,0.1)">Client: ${node.data.client.name}</div>`;
        }

        // Physical Topology (LLDP/CDP Neighbors)
        if (node.data.neighbors && node.data.neighbors.length > 0) {
            html += `<div style="margin-top:8px; border-top:1px solid rgba(255,255,255,0.1); padding-top:4px; font-weight:600; font-size:11px; color:#8b5cf6">LLDP Discovery:</div>`;
            node.data.neighbors.forEach(nb => {
                html += `<div class="small" style="color:#94a3b8; font-size:10px;">Port ${nb.local_port} ↔ ${nb.neighbor_id} (${nb.neighbor_port})</div>`;
            });
        }
        
        // Orphan indicator
        if (node.isOrphan) {
            html += `<div style="margin-top:4px; color:#f59e0b; font-size:10px;">🔗 Discovered via LLDP</div>`;
        }
    }
    
    tooltip.innerHTML = html;
    
    // Positioning logic to keep inside viewport
    const tRect = tooltip.getBoundingClientRect();
    let left = x + 15;
    let top = y + 15;
    
    if (left + tRect.width > window.innerWidth) left = x - tRect.width - 15;
    if (top + tRect.height > window.innerHeight) top = y - tRect.height - 15;
    
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
    tooltip.style.display = 'block';
}

function hideTooltip() {
    tooltip.style.display = 'none';
}
