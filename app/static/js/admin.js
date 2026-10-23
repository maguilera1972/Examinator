(function () {
  const VALID = new Set(["create", "users", "exams", "pools", "import", "sync", "logs"]);
  const nav = document.querySelector("[data-admin-tabs]");
  if (!nav) return;

  const tabs = Array.from(nav.querySelectorAll(".admin-tab[data-section]"));
  const panels = Array.from(document.querySelectorAll("[data-admin-panel]"));

  function currentFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const section = params.get("section");
    if (section && VALID.has(section)) return section;
    return nav.getAttribute("data-default-section") || "create";
  }

  function showSection(section, { push } = { push: true }) {
    if (!VALID.has(section)) section = "create";

    tabs.forEach((tab) => {
      const active = tab.dataset.section === section;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });

    panels.forEach((panel) => {
      const active = panel.getAttribute("data-admin-panel") === section;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });

    const params = new URLSearchParams(window.location.search);
    params.set("section", section);
    const next = `${window.location.pathname}?${params.toString()}`;
    if (push) {
      history.replaceState(null, "", next);
    }
    try {
      sessionStorage.setItem("examinator_admin_section", section);
    } catch (_) {
      /* ignore */
    }
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => showSection(tab.dataset.section));
  });

  let initial = currentFromUrl();
  if (!new URLSearchParams(window.location.search).get("section")) {
    try {
      const stored = sessionStorage.getItem("examinator_admin_section");
      if (stored && VALID.has(stored)) initial = stored;
    } catch (_) {
      /* ignore */
    }
  }
  showSection(initial, { push: true });

  document.querySelectorAll("[data-admin-filter]").forEach((input) => {
    const key = input.getAttribute("data-admin-filter");
    const list = document.querySelector(`[data-admin-filter-list="${key}"]`);
    if (!list) return;
    const items = () =>
      Array.from(list.querySelectorAll("[data-filter-text]"));

    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      items().forEach((el) => {
        const hay = (el.getAttribute("data-filter-text") || "").toLowerCase();
        el.hidden = Boolean(q) && !hay.includes(q);
      });
    });
  });
})();

(function () {
  const dialog = document.getElementById("mailDialog");
  if (!dialog) return;
  const form = document.getElementById("mailForm");
  const steps = dialog.querySelectorAll("[data-mail-step]");
  const frame = dialog.querySelector("[data-mail-frame]");
  const info = dialog.querySelector("[data-mail-info]");
  const sendBtn = dialog.querySelector("[data-mail-send]");
  let recipientCount = 0;

  function showStep(name) {
    steps.forEach((s) => { s.hidden = s.getAttribute("data-mail-step") !== name; });
  }

  document.querySelectorAll("[data-mail-open]").forEach((btn) =>
    btn.addEventListener("click", () => { showStep("edit"); dialog.showModal(); })
  );
  dialog.querySelectorAll("[data-mail-close]").forEach((btn) =>
    btn.addEventListener("click", () => dialog.close())
  );
  dialog.querySelector("[data-mail-back]").addEventListener("click", () => showStep("edit"));

  dialog.querySelector("[data-mail-preview]").addEventListener("click", async () => {
    if (!form.reportValidity()) return;
    const resp = await fetch("/admin/email/preview", { method: "POST", body: new FormData(form) });
    if (!resp.ok) { alert("Aperçu impossible (session expirée ?)"); return; }
    const data = await resp.json();
    recipientCount = data.count;
    frame.srcdoc = data.html;
    info.textContent = `${data.audience} : ${data.count} destinataire(s), depuis ${data.sender}. ` +
      "Aperçu personnalisé avec votre nom ; chaque destinataire reçoit un e-mail individuel." +
      (data.configured ? "" : " ⚠ Envoi non configuré.");
    sendBtn.textContent = `Envoyer à ${data.count} utilisateur(s)`;
    sendBtn.disabled = !data.configured || !data.count;
    showStep("preview");
  });

  form.addEventListener("submit", (event) => {
    const mode = event.submitter && event.submitter.value;
    if (mode === "all" && !confirm(`Envoyer ce message à ${recipientCount} utilisateur(s) ?`)) {
      event.preventDefault();
      return;
    }
    if (event.submitter) {
      event.submitter.disabled = true;
      event.submitter.textContent = "Envoi en cours…";
      const hidden = document.createElement("input");
      hidden.type = "hidden"; hidden.name = "mode"; hidden.value = mode;
      form.appendChild(hidden);
    }
  });
})();
