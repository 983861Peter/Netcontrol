/**
 * settings.js - Logic for Controller Configuration
 */

let currentTemplateType = 'router';

document.addEventListener("DOMContentLoaded", () => {
    loadSettings();
    // Default to loading the router template
    loadTemplate('router');

    // General Save Button
    document.getElementById('saveSettings')?.addEventListener('click', saveGeneralSettings);
    
    // Controller Actions
    document.getElementById('factoryResetController')?.addEventListener('click', handleFactoryReset);
    document.getElementById('clearBackups')?.addEventListener('click', handleClearBackups);
    document.getElementById('exportConfig')?.addEventListener('click', () => {
        window.location.href = `${API_URL}/settings/export`;
    });

    // Logout
    document.getElementById('btnLogout4')?.addEventListener('click', () => {
        localStorage.removeItem('token');
        location.href = 'login.html';
    });
});

async function loadSettings() {
    try {
        const res = await apiFetch('/settings/config');
        if (!res.ok) return;
        const cfg = await res.json();

        // Populate General
        document.getElementById('ctrlName').value = cfg.controller_name || '';
        document.getElementById('scanInterval').value = cfg.scan_interval || 60;

        // Populate Company Defaults
        document.getElementById('set_dns1').value = cfg.dns_primary || '';
        document.getElementById('set_dns2').value = cfg.dns_secondary || '';
        document.getElementById('set_ntp').value = cfg.ntp_server || '';
        document.getElementById('set_syslog').value = cfg.syslog_server || '';
        document.getElementById('set_snmp').value = cfg.snmp_community || '';
        document.getElementById('set_domain').value = cfg.domain_name || '';
        document.getElementById('set_admin').value = cfg.admin_user || '';
        document.getElementById('set_acl').value = cfg.management_acl || '';

        // Populate New Device Defaults
        document.getElementById('defSsid').value = cfg.default_ssid || '';
        document.getElementById('defPass').value = cfg.default_wifi_password || '';

        // Security & VPN
        document.getElementById('enableFirewall').checked = !!cfg.firewall_enabled;
        document.getElementById('blockedPorts').value = cfg.blocked_ports || '';
        document.getElementById('securityPolicies').value = cfg.security_policies || '';
        document.getElementById('enableVpn').checked = !!cfg.vpn_enabled;
        document.getElementById('vpnServer').value = cfg.vpn_server || '';
        document.getElementById('vpnPort').value = cfg.vpn_port || 1194;
        document.getElementById('vpnProtocol').value = cfg.vpn_protocol || 'openvpn';

        // System
        document.getElementById('enableDebug').checked = !!cfg.debug_enabled;
        document.getElementById('smtpServer').value = cfg.smtp_server || '';
        document.getElementById('smtpUser').value = cfg.smtp_user || '';
    } catch (err) {
        console.error("Failed to load settings:", err);
    }
}

async function saveGeneralSettings() {
    const payload = {
        controller_name: document.getElementById('ctrlName').value,
        scan_interval: parseInt(document.getElementById('scanInterval').value),
        default_ssid: document.getElementById('defSsid').value,
        default_wifi_password: document.getElementById('defPass').value,
        firewall_enabled: document.getElementById('enableFirewall').checked,
        blocked_ports: document.getElementById('blockedPorts').value,
        security_policies: document.getElementById('securityPolicies').value,
        vpn_enabled: document.getElementById('enableVpn').checked,
        vpn_server: document.getElementById('vpnServer').value,
        vpn_port: parseInt(document.getElementById('vpnPort').value),
        vpn_protocol: document.getElementById('vpnProtocol').value,
        debug_enabled: document.getElementById('enableDebug').checked,
        smtp_server: document.getElementById('smtpServer').value,
        smtp_port: parseInt(document.getElementById('smtpPort').value),
        smtp_user: document.getElementById('smtpUser').value,
        smtp_pass: document.getElementById('smtpPass').value
    };

    try {
        const res = await apiFetch('/settings/config', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        if (res.ok) UI.toaster.push("success", "General settings saved.");
    } catch (err) {
        UI.toaster.push("error", "Failed to save general settings.");
    }
}

async function saveCompanyDefaults() {
    const payload = {
        dns_primary: document.getElementById('set_dns1').value,
        dns_secondary: document.getElementById('set_dns2').value,
        ntp_server: document.getElementById('set_ntp').value,
        syslog_server: document.getElementById('set_syslog').value,
        snmp_community: document.getElementById('set_snmp').value,
        domain_name: document.getElementById('set_domain').value,
        admin_user: document.getElementById('set_admin').value,
        management_acl: document.getElementById('set_acl').value
    };

    try {
        const res = await apiFetch('/settings/company-defaults', {
            method: 'POST',
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            UI.toaster.push("success", "Company defaults updated. These will apply to all future adoptions.");
        } else {
            UI.toaster.push("error", "Failed to save settings.");
        }
    } catch (err) {
        console.error("Save failed:", err);
    }
}

/** Template Management **/
async function loadTemplate(type) {
    currentTemplateType = type;
    
    // Update UI Tabs
    document.querySelectorAll('.tabs .btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`btn-tpl-${type}`)?.classList.add('active');
    document.getElementById('tpl_label').innerText = `${type.charAt(0).toUpperCase() + type.slice(1)} Configuration Template`;

    try {
        const res = await apiFetch(`/settings/templates/${type}`);
        const data = await res.json();
        document.getElementById('tpl_content').value = data.content || '';
    } catch (err) {
        document.getElementById('tpl_content').value = '';
    }
}

async function saveTemplate() {
    const content = document.getElementById('tpl_content').value;
    try {
        const res = await apiFetch(`/settings/templates/${currentTemplateType}`, {
            method: 'POST',
            body: JSON.stringify({ content })
        });
        if (res.ok) UI.toaster.push("success", `${currentTemplateType} template updated.`);
    } catch (err) {
        UI.toaster.push("error", "Failed to save template.");
    }
}

async function resetTemplate() {
    if (!confirm("Are you sure you want to revert this template to system defaults?")) return;
    try {
        const res = await apiFetch(`/settings/templates/${currentTemplateType}/reset`, { method: 'POST' });
        if (res.ok) {
            UI.toaster.push("info", "Template reset to default.");
            loadTemplate(currentTemplateType);
        }
    } catch (err) {}
}

/** Maintenance Actions **/
function handleFactoryReset() {
    UI.modal({
        html: `<h3>Factory Reset Controller</h3>
               <p class="danger-text">This will wipe all managed devices, clients, and configuration logs. This action cannot be undone.</p>
               <p>Type <b>CONFIRM</b> to proceed.</p>
               <input id="reset_confirm" class="input" />`,
        buttons: [
            { label: "Cancel", className: "btn ghost" },
            { label: "Wipe Everything", className: "btn danger", onClick: async () => {
                if (document.getElementById('reset_confirm').value === 'CONFIRM') {
                    await apiFetch('/controller/factory-reset', { method: 'POST' });
                    location.href = 'login.html';
                } else {
                    UI.toaster.push("error", "Reset cancelled: Confirmation text incorrect.");
                }
            }}
        ]
    });
}

async function handleClearBackups() {
    if (confirm("Delete all stored device backups?")) {
        const res = await apiFetch('/controller/backups/clear', { method: 'POST' });
        if (res.ok) UI.toaster.push("success", "Backup storage cleared.");
    }
}

window.loadTemplate = loadTemplate;
window.saveTemplate = saveTemplate;
window.resetTemplate = resetTemplate;