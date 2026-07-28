// async function registerCompany() {
//   const payload = {
//     full_name: val("full_name"),
//     email: val("email"),
//     alias: val("alias"),
//     password: val("password"),
//     company_name: val("company_name"),
//     company_email: val("company_email"),
//     company_location: val("company_location")
//   };

document.addEventListener("DOMContentLoaded", () => {
  const registerForm = document.getElementById("registerForm");
  if (!registerForm) return;
// await apiFetch("/auth/register-company", {
//     method: "POST",
//     body: JSON.stringify(payload)
  // Parse token from URL
  const urlParams = new URLSearchParams(window.location.search);
  const token = urlParams.get("token");

  if (!token) {
    showToast("Invalid or missing invitation token.", "error");
    const btn = document.getElementById("registerBtn");
    if(btn) btn.disabled = true;
    return;
  }

  const showPass = document.getElementById("showPass");
  if (showPass) {
    showPass.addEventListener("change", () => {
      const type = showPass.checked ? "text" : "password";
      document.getElementById("password").type = type;
      document.getElementById("confirmPassword").type = type;
    });
  }

  registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    const password = document.getElementById("password").value;
    const confirmPassword = document.getElementById("confirmPassword").value;

    if (password !== confirmPassword) {
      showToast("Passwords do not match.", "error");
      return;
    }

    const btn = document.getElementById("registerBtn");
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Setting Password...";

    try {
      const res = await apiFetch("/auth/complete-registration", { 
        method: "POST", 
        body: JSON.stringify({ token, password }) 
      });

      if (res.ok) {
        showToast("Registration complete! Redirecting...", "success");
        setTimeout(() => { window.location.href = "login.html"; }, 1500);
      } else {
        const err = await res.json();
        showToast(err.detail || "Registration failed.", "error");
        btn.disabled = false;
        btn.textContent = originalText;
      }

    } catch (err) {
      console.error(err);
      showToast("Failed to complete registration.", "error");
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
});
// location.href = "/admin/account.html";

function showToast(msg, type = "info") {
  const toast = document.getElementById("toast");
  if (!toast) return;
  
  toast.textContent = msg;
  toast.className = `toast ${type}`;
  toast.classList.remove("hidden");
  
  setTimeout(() => {
    toast.classList.add("hidden");
  }, 3000);
}
