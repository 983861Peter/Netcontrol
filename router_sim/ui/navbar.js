// navbar.js
document.addEventListener("DOMContentLoaded", async () => {
  const token = localStorage.getItem("token");
  const role = localStorage.getItem("role");

  if (!token) {
    window.location.href = "login.html";
    return;
  }

  // Load navbar HTML dynamically
  const navbarContainer = document.createElement("div");
  const res = await fetch("navbar.html");
  navbarContainer.innerHTML = await res.text();
  document.body.prepend(navbarContainer);

  // Apply visibility rules
  if (role !== "admin") {
    document.querySelectorAll(".admin-only").forEach(el => el.style.display = "none");
  }

  // Logout
  setTimeout(() => {
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => {
        localStorage.clear();
        window.location.href = "login.html";
      });
    }
  }, 300);
});
