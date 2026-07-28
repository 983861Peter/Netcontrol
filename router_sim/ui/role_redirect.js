// role_redirect.js

document.addEventListener("DOMContentLoaded", () => {
    const role = localStorage.getItem("user_role");

    if (!role) {
        window.location.href = "login.html";
        return;
    }

    switch (role) {
        case "admin":
            window.location.href = "dashboard_admin.html";
            break;
        case "engineer":
            window.location.href = "dashboard_engineer.html";
            break;
        case "support":
            window.location.href = "dashboard_support.html";
            break;
        case "stakeholder":
            window.location.href = "dashboard_stakeholder.html";
            break;
        default:
            alert("Unknown role: " + role);
            window.location.href = "login.html";
    }
});
