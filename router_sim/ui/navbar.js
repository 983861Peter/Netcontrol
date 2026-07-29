// navbar.js
document.addEventListener("DOMContentLoaded", async () => {
  const token = localStorage.getItem("token");
  const role = localStorage.getItem("role");
  const navbarContainer = document.createElement("div");
  const res = await fetch("navbar.html");
  navbarContainer.innerHTML = await res.text();
  document.body.prepend(navbarContainer);

  // add mobile sidebar overlay
  const overlay = document.createElement("div");
  overlay.className = "sidebar-overlay";
  document.body.appendChild(overlay);

  const toggleButton = document.getElementById("mobileNavToggle");
  const sidebar = document.querySelector(".sidebar");

  const closeSidebar = () => {
    sidebar?.classList.remove("mobile-open");
    overlay?.classList.remove("visible");
  };

  toggleButton?.addEventListener("click", () => {
    sidebar?.classList.toggle("mobile-open");
    overlay?.classList.toggle("visible");
  });

  overlay?.addEventListener("click", closeSidebar);

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
