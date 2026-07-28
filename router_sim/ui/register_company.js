document.addEventListener("DOMContentLoaded", () => {
  initializePasswordToggles();
  const form = document.getElementById("registerCompanyForm");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    const companyName = document.getElementById("companyName").value.trim();
    const location = document.getElementById("companyLocation").value.trim();
    const username = document.getElementById("adminUsername").value.trim();
    const email = document.getElementById("adminEmail").value.trim();
    const phone = document.getElementById("adminPhone").value.trim();
    const password = document.getElementById("password").value;
    const confirmPassword = document.getElementById("confirmPassword").value;

    if (password !== confirmPassword) {
      showToast("Passwords do not match", "error");
      return;
    }

    const btn = document.getElementById("registerBtn");
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Registering...";

    try {
      const res = await apiFetch("/auth/register-company", {
        method: "POST",
        body: JSON.stringify({
          company_name: companyName,
          location: location,
          username: username,
          email: email,
          password: password,
          phone_number: phone
        })
      });

      if (res.ok) {
        showToast("Company registered successfully!", "success");
        setTimeout(() => window.location.href = "login.html", 1500);
      } else {
        const err = await res.json();
        showToast(err.detail || "Registration failed", "error");
        btn.disabled = false;
        btn.textContent = originalText;
      }
    } catch (err) {
      console.error(err);
      showToast("Connection error", "error");
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
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

function showToast(msg, type = "info") {
  // Reuse existing toast logic if available or simple fallback
  if (window.UI && window.UI.toaster) { window.UI.toaster.push(type, msg); return; }
  
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.textContent = msg;
  toast.className = `toast ${type}`;
  toast.style.display = "block";
  setTimeout(() => {
    toast.style.display = "none";
  }, 3000);
}