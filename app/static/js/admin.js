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
