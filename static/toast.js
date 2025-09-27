// static/toast.js — toast globale riusabile su ogni pagina
(function () {
  // crea il container se manca
  let host = document.getElementById("toastHost");
  if (!host) {
    host = document.createElement("div");
    host.id = "toastHost";
    host.className = "toast-container position-fixed top-0 end-0 p-3";
    host.style.zIndex = 1080;
    document.body.appendChild(host);
  }

  // inject stile minimo una sola volta
  if (!document.getElementById("toastStyle")) {
    const css = `
      .toast{border-radius:10px}
      .toast .toast-body{font-weight:500}
    `;
    const style = document.createElement("style");
    style.id = "toastStyle";
    style.textContent = css;
    document.head.appendChild(style);
  }

  // API globale
  window.showToast = function (text, type = "success") {
    const map = { success: "bg-success", warning: "bg-warning text-dark", danger: "bg-danger", info: "bg-info text-dark" };
    const bg = map[type] || "bg-secondary";
    const el = document.createElement("div");
    el.className = `toast align-items-center ${bg} text-white show`;
    el.setAttribute("role", "alert");
    el.setAttribute("aria-live", "assertive");
    el.setAttribute("aria-atomic", "true");
    el.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">✔️ ${text}</div>
        <button type="button" class="btn-close ${bg.includes('text-dark')?'':'btn-close-white'} me-2 m-auto" aria-label="Close"></button>
      </div>`;
    el.querySelector(".btn-close").addEventListener("click", () => { el.classList.remove("show"); setTimeout(() => el.remove(), 150); });
    host.appendChild(el);
    setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 200); }, 3200);
  };
})();




//<script>
  // Mostra un toast verde di conferma
//  showToast("Cliente salvato correttamente!", "success");

  // Mostra un toast giallo di avviso
//  showToast("Sei offline: dati salvati solo in locale.", "warning");
//</script>


