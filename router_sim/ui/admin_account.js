function openAddTech() {
  UI.modal({
    html: `
      <h3>Add Technical Support</h3>
      <input id="name" class="input" placeholder="Full Name">
      <input id="email" class="input" placeholder="Email">
      <input id="alias" class="input" placeholder="Alias">
    `,
    buttons: [
      { label:"Cancel", className:"btn ghost" },
      {
        label:"Invite",
        className:"btn",
        onClick: async () => {
          await apiFetch("/admin/add-tech", {
            method:"POST",
            body: JSON.stringify({
              full_name: val("name"),
              email: val("email"),
              alias: val("alias")
            })
          });
          UI.toaster.push("success","Staff added");
        }
      }
    ]
  });
}
