async function api(path, opts = {}) {
    opts.headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + localStorage.getItem("token")
    };
    return fetch("http://localhost:8080" + path, opts);
}

async function sendInvite() {
    const username = document.getElementById("inv_username").value.trim();
    const role = document.getElementById("inv_role").value;

    const res = await api("/auth/invite", {
        method: "POST",
        body: JSON.stringify({ username, role })
    });

    if (res.ok) {
        alert("Invitation Created");
        loadInvites();
    } else {
        alert("Error sending invite");
    }
}

async function loadInvites() {
    const res = await api("/auth/invite/list");

    if (!res.ok) return;

    const invites = await res.json();
    const body = document.getElementById("inv_body");

    body.innerHTML = invites.map(inv => `
        <tr>
            <td>${inv.username}</td>
            <td>${inv.role}</td>
            <td>${inv.token}</td>
            <td><button onclick="revoke('${inv.token}')">Revoke</button></td>
        </tr>
    `).join("");
}

async function revoke(token) {
    await api("/auth/invite/" + token, { method: "DELETE" });
    loadInvites();
}

document.addEventListener("DOMContentLoaded", loadInvites);
