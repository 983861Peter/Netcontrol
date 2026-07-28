/* ui/js/auth.js */
document.addEventListener("DOMContentLoaded", ()=>{
  const btn = document.getElementById("btnLogin");
  if(!btn) return;
  btn.addEventListener("click", async ()=>{
    const u = document.getElementById("username").value;
    const p = document.getElementById("password").value;
    document.getElementById("loginMsg").textContent = "";
    try {
      const res = await fetch(API_BASE + "/auth/login", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({username:u,password:p})
      });
      if(res.status !== 200){
        const txt = await res.text();
        document.getElementById("loginMsg").textContent = "Login failed";
        UI.toaster.push("error","Login failed: " + txt,4000);
        return;
      }
      const data = await res.json();
      setAuthToken(data.access_token);
      UI.toaster.push("success","Signed in",2000);
      window.location = "index.html";
    } catch(e){
      document.getElementById("loginMsg").textContent = "Error connecting";
      UI.toaster.push("error","Connection error",3000);
    }
  });
});
