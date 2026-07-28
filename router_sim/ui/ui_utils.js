/* ui/js/ui_utils.js
   Toast and Modal utilities used across the UI
*/
(function(){
  const toastRoot = document.getElementById("toasts");
  const modalRoot = document.getElementById("modalRoot");

  function mkToast(type, msg){
    const div = document.createElement("div");
    div.className = `toast ${type}`;
    div.innerHTML = `<div class="msg">${msg}</div><div style="opacity:0.7">×</div>`;
    return div;
  }

  const toaster = {
    push(type, msg, ttl=4000){
      if(!toastRoot) return console.log(type,msg);
      const t = mkToast(type, msg);
      toastRoot.appendChild(t);
      setTimeout(()=> t.style.opacity = 0.99, 20);
      const remover = () => { t.remove(); };
      t.addEventListener("click", remover);
      setTimeout(remover, ttl);
    }
  };

  function escapeHtml(text) {
  if (!text && text !== 0) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
  }
  
  function showModal(opts){
    if(!modalRoot) return;
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";
    const modal = document.createElement("div");
    modal.className = opts.wide ? "modal wide-modal" : "modal";
    if (opts.wide) {
      modal.style.maxWidth = "90vw";
      modal.style.width = "90vw";
      modal.style.maxHeight = "90vh";
    }
    modal.innerHTML = `<div>${opts.html || ""}</div>`;
    const actions = document.createElement("div");
    actions.className = "actions";
    if(opts.buttons && opts.buttons.length){
      opts.buttons.forEach(btn=>{
        const b = document.createElement("button");
        b.className = btn.className || "btn";
        b.textContent = btn.label || "OK";
        if (btn.style) b.style.cssText = btn.style;
        b.onclick = () => { 
          if(btn.onClick && btn.onClick() === false) return; 
          modalRoot.removeChild(backdrop); 
        };
        actions.appendChild(b);
      });
    } else {
      const b = document.createElement("button");
      b.className = "btn";
      b.textContent = "Close";
      b.onclick = () => modalRoot.removeChild(backdrop);
      actions.appendChild(b);
    }
    modal.appendChild(actions);
    backdrop.appendChild(modal);
    modalRoot.appendChild(backdrop);
  }


  window.UI = window.UI || {};
  window.UI.toaster = toaster;
  window.UI.modal = showModal;
  window.UI.confirm = function(message, onConfirm){
    showModal({
      html:`<h3>${message}</h3>`,
      buttons:[
        {label:"Cancel", className:"btn ghost", onClick:()=>{}},
        {label:"Confirm", className:"btn danger", onClick:onConfirm}
      ]
    });
  };
  window.UI.escapeHtml = escapeHtml; // Expose escapeHtml
})();
