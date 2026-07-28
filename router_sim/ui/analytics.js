/* ui/js/analytics.js */

// New function to generate realistic simulated data
function generateRealisticData(numPoints = 24, totalDevicesOverride = null, actualTotalDataGB = 0) {
    const data = {
        labels: [],
        rx: [],
        tx: [],
        online_devices: [],
        total_data: []
    };

    let totalDevices = totalDevicesOverride !== null ? totalDevicesOverride : 0;

    if (totalDevices <= 0) {
        // Return zeroed out dataset immediately if no devices exist
        const zeros = new Array(numPoints).fill(0);
        return { labels: new Array(numPoints).fill("").map((_, i) => `${i}:00`), rx: zeros, tx: zeros, online_devices: zeros, total_data: zeros };
    }

    for (let i = 0; i < numPoints; i++) {
        data.labels.push(`${i}:00`);
        
        // Simulate day/night cycle for device activity
        const hour = i;
        // A curve that is low at night, rises in the morning, peaks in the evening, and drops off at night.
        const activityFactor = (Math.sin((hour / 23) * Math.PI - (Math.PI / 2.5)) + 1) / 2;
        
        // Use a semi-deterministic noise based on the hour to prevent wild fluctuations on refresh
        const noise = 0.7 + (((i * 13) % 30) / 100); 
        const onlineCount = Math.floor(activityFactor * totalDevices * noise);
        
        data.online_devices.push(Math.min(totalDevices, onlineCount));
        
        let rxRate = 0;
        let txRate = 0;

        if (onlineCount > 0) {
            // Simulate traffic based on online devices with a wavy pattern
            // Use fixed multipliers for consistency per device
            const baseRx = onlineCount * 0.5; 
            const baseTx = onlineCount * 0.15; 

            // Add a wavy progression to simulate fluctuating usage
            const wave = Math.sin(i / 2) * (baseRx * 0.1) + Math.sin(i) * (baseRx * 0.03);
            
            // Spikes are now deterministic based on index i
            const rxSpike = (i % 7 === 0) ? onlineCount * 0.5 : 0;
            const txSpike = (i % 11 === 0) ? onlineCount * 0.2 : 0;
            
            rxRate = baseRx + wave + rxSpike;
            txRate = baseTx + (wave * 0.4) + txSpike; // TX wave is smaller

            // Ensure RX is always higher than TX
            if (txRate > rxRate) {
                txRate = rxRate * (0.6 + Math.random() * 0.3);
            }
        }

        // Ensure traffic is never zero if devices are online, and never negative.
        data.rx.push(onlineCount > 0 ? Math.max(0.5, Math.round(rxRate * 10) / 10) : 0);
        data.tx.push(onlineCount > 0 ? Math.max(0.5, Math.round(txRate * 10) / 10) : 0);
    }

    // Distribute the actual total_data_gb across the 24 hours proportionally
    // based on the simulated online devices activity
    if (actualTotalDataGB > 0) {
        const totalActivity = data.online_devices.reduce((a, b) => a + b, 0);
        for (let i = 0; i < numPoints; i++) {
            const activityShare = totalActivity > 0 ? (data.online_devices[i] / totalActivity) : (1 / numPoints);
            data.total_data.push(Math.round((actualTotalDataGB * activityShare) * 1000) / 1000);
        }
    } else {
        const zeros = new Array(numPoints).fill(0);
        data.total_data = zeros;
    }

    return data;
}

async function fetchAnalytics(){
  try{
    const res = await apiFetch('/analytics');
    if (!res.ok) return;
    const serverData = await res.json();

    // Extract usage data from server
    const usage = serverData.usage || { 
        avg_tx_mbps: 0, 
        avg_rx_mbps: 0, 
        total_data_gb: 0, 
        active_devices_24h: 0 
    };

    // Generate graph data based on actual device counts and actual total data from server
    const total = serverData.total_devices || 0;
    const simulatedData = generateRealisticData(24, total, usage.total_data_gb);
    
    // Display the actual server data in stat boxes
    if (document.getElementById("ana-tx")) {
        document.getElementById("ana-tx").textContent = usage.avg_tx_mbps + " Mbps";
        document.getElementById("ana-rx").textContent = usage.avg_rx_mbps + " Mbps";
        document.getElementById("ana-data").textContent = usage.total_data_gb + " GB";
        document.getElementById("ana-active").textContent = usage.active_devices_24h;
    }

    // Draw the graph with the corrected data
    drawAnalytics(simulatedData);

  } catch(e){ console.warn("Analytics generation/drawing failed", e) }
}

function drawAnalytics(data, canvasId = "analyticsChart"){
  const canvas = document.getElementById(canvasId);
  if(!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.clientWidth, h = 260;
  canvas.width = w; canvas.height = h;
  ctx.clearRect(0,0,w,h);

  if (!data || !data.labels || !data.labels.length) {
      ctx.fillStyle = "#888";
      ctx.font = "14px Inter";
      ctx.textAlign = "center";
      ctx.fillText("No analytics data to display.", w/2, h/2);
      return;
  }

  const datasets = [
    { label: "RX (Mbps)", data: data.rx, color: "#3498db", yAxis: 'left' },
    { label: "TX (Mbps)", data: data.tx, color: "#f39c12", yAxis: 'left' },
    { label: "Online Devices", data: data.online_devices, color: "#2ecc71", yAxis: 'left' },
    { label: "Total Usage (GB)", data: data.total_data, color: "#9b59b6", yAxis: 'right' }
  ];

  const margin = { top: 20, right: 50, bottom: 50, left: 50 };
  const plotWidth = w - margin.left - margin.right;
  const plotHeight = h - margin.top - margin.bottom;

  const leftDatasets = datasets.filter(ds => ds.yAxis !== 'right');
  const rightDatasets = datasets.filter(ds => ds.yAxis === 'right');

  const maxValLeft = Math.max(10, ...leftDatasets.map(ds => Math.max(...(ds.data.length ? ds.data : [0]))));
  const maxValRight = Math.max(10, ...rightDatasets.map(ds => Math.max(...(ds.data.length ? ds.data : [0]))));

  // Draw Left Y-Axis
  ctx.strokeStyle = "rgba(255,255,255,0.1)";
  ctx.fillStyle = "rgba(255,255,255,0.4)";
  ctx.font = "10px Inter";
  ctx.textAlign = "right";
  
  ctx.beginPath(); ctx.moveTo(margin.left, margin.top); ctx.lineTo(margin.left, h - margin.bottom); ctx.stroke();
  for (let i = 0; i <= 5; i++) {
      const val = (maxValLeft / 5) * i;
      const y = h - margin.bottom - (val / maxValLeft) * plotHeight;
      ctx.fillText(Math.round(val), margin.left - 8, y + 3);
  }

  // Draw Right Y-Axis
  ctx.textAlign = "left";
  ctx.beginPath(); ctx.moveTo(w - margin.right, margin.top); ctx.lineTo(w - margin.right, h - margin.bottom); ctx.stroke();
  for (let i = 0; i <= 5; i++) {
      const val = (maxValRight / 5) * i;
      const y = h - margin.bottom - (val / maxValRight) * plotHeight;
      ctx.fillText(Math.round(val) + " GB", w - margin.right + 8, y + 3);
  }

  // Draw X-Axis
  ctx.textAlign = "center";
  ctx.beginPath(); ctx.moveTo(margin.left, h - margin.bottom); ctx.lineTo(w - margin.right, h - margin.bottom); ctx.stroke();
  const numLabels = data.labels.length;
  const labelStep = Math.ceil(numLabels / (plotWidth / 60));
  for (let i = 0; i < numLabels; i += labelStep) {
      const x = margin.left + (i / (numLabels - 1)) * plotWidth;
      ctx.fillText(data.labels[i], x, h - margin.bottom + 15);
  }

  // Draw lines
  datasets.forEach(ds => {
      const maxVal = ds.yAxis === 'right' ? maxValRight : maxValLeft;
      ctx.strokeStyle = ds.color; ctx.lineWidth = 2; ctx.beginPath();
      ds.data.forEach((val, i) => {
          const x = margin.left + (i / (numLabels - 1)) * plotWidth;
          const y = h - margin.bottom - (val / maxVal) * plotHeight;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
  });
  
  // Draw Legend
  ctx.textAlign = "left";
  let legendX = margin.left;
  datasets.forEach(ds => {
      ctx.fillStyle = ds.color;
      ctx.fillRect(legendX, h - margin.bottom + 30, 10, 10);
      ctx.fillStyle = "#fff";
      ctx.font = "12px Inter";
      ctx.fillText(ds.label, legendX + 15, h - margin.bottom + 39);
      legendX += ctx.measureText(ds.label).width + 45;
  });
}

// Automatic calculation: Refresh analytics every 5 seconds to reflect system changes
if (typeof analyticsInterval === 'undefined') {
    var analyticsInterval = setInterval(fetchAnalytics, 5000);
    console.log("Analytics auto-refresh started (5s interval)");
}
