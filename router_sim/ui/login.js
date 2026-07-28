const API_URL = window.API_BASE || (window.location.port === "3000" ? "http://127.0.0.1:8080" : window.location.origin);

document.addEventListener("DOMContentLoaded", () => {
  const loginForm = document.getElementById("loginForm");
  initializePasswordToggles();

  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      const username = document.getElementById("username").value.trim();
      const password = document.getElementById("password").value.trim();

      if (!username || !password) {
        showToast("Please fill in all fields", "error");
        return;
      }

      try {
        const response = await fetch(`${API_URL}/auth/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: new URLSearchParams({
            username: username,
            password: password,
          }),
        });

        if (!response.ok) {
          if (response.status === 401) {
          showToast("Invalid credentials", "error");
        } else {
          showToast(`Error ${response.status}`, "error");
        }
        return;
        }

        const data = await response.json();

        // Save token and user info locally
        localStorage.setItem("token", data.access_token);
        localStorage.setItem("username", data.username);
        localStorage.setItem("role", data.role);

        showToast("Login successful!", "success");

        // Redirect based on role
        if (data.role === "admin") {
          window.location.href = "index.html";
        } else {
          window.location.href = "technician_dashboard.html";
        }

      } catch (err) {
        console.error("Login failed:", err);
        showToast("Connection error or invalid credentials", "error");
      }
    });
  }
});

function initializePasswordToggles() {
  document.querySelectorAll(".password-toggle").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const targetId = toggle.dataset.target;
      const input = document.getElementById(targetId);
      if (!input) return;

      const isPassword = input.type === "password";
      input.type = isPassword ? "text" : "password";
      toggle.setAttribute("aria-label", isPassword ? "Hide password" : "Show password");
      toggle.setAttribute("title", isPassword ? "Hide password" : "Show password");

      const eyeOpen = toggle.querySelector(".eye-open");
      const eyeClosed = toggle.querySelector(".eye-closed");
      if (eyeOpen && eyeClosed) {
        eyeOpen.style.display = isPassword ? "none" : "block";
        eyeClosed.style.display = isPassword ? "block" : "none";
      }
    });
  });
}

// Simple Toast Notification
function showToast(message, type) {
  const toast = document.createElement("div");
  toast.textContent = message;
  toast.className = `toast ${type}`;
  document.body.appendChild(toast);
  setTimeout(() => {
    toast.remove();
  }, 3000);
}

