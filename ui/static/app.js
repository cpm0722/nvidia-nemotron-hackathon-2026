(() => {
  const chat = document.getElementById("chat");
  const welcome = document.getElementById("welcome");
  const suggestGrid = document.getElementById("suggest-grid");
  const form = document.getElementById("input-form");
  const input = document.getElementById("query");
  const sendBtn = document.getElementById("send-btn");
  const modeBadge = document.getElementById("mode-badge");
  const historyList = document.getElementById("history-list");
  const newChatBtn = document.getElementById("new-chat-btn");
  const sidebar = document.getElementById("sidebar");
  const sidebarToggle = document.getElementById("sidebar-toggle");

  const SIDEBAR_STORAGE_KEY = "nemo.sidebar.collapsed";

  function setSidebarCollapsed(collapsed) {
    sidebar.classList.toggle("is-collapsed", collapsed);
    sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "1" : "0");
    } catch {
      // storage unavailable — ignore
    }
  }

  sidebarToggle.addEventListener("click", () => {
    setSidebarCollapsed(!sidebar.classList.contains("is-collapsed"));
  });

  try {
    if (localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1") {
      setSidebarCollapsed(true);
    }
  } catch {
    // ignore
  }

  const POLL_INTERVAL_MS = 1500;

  // Seed cards shown on the empty/initial chat. Click → fills the composer.
  const SUGGESTIONS = [
    {
      name: "exaone 4.5",
      display: "EXAONE 4.5",
      size: "33B",
      company: "LG AI Research",
      logo: {
        kind: "text",
        bg: "#a50034",
        fg: "#ffffff",
        text: "LG",
        fontSize: "13px",
        weight: 800,
      },
    },
    {
      name: "gemma 4",
      display: "Gemma 4",
      size: "31B",
      company: "Google",
      logo: {
        kind: "svg",
        bg: "linear-gradient(135deg, #4285f4 0%, #a142f4 100%)",
        svg: `
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
            <path d="M6 3 L18 3 L22 10 L12 22 L2 10 Z"
                  fill="white" stroke="rgba(255,255,255,0.4)" stroke-width="0.5"/>
            <path d="M6 3 L12 10 L2 10 Z" fill="rgba(255,255,255,0.25)"/>
            <path d="M18 3 L22 10 L12 10 Z" fill="rgba(0,0,0,0.15)"/>
          </svg>`,
      },
    },
    {
      name: "opus 4.7",
      display: "Opus 4.7",
      size: null,
      company: "Anthropic",
      logo: {
        kind: "svg",
        bg: "#cc785c",
        svg: `
          <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
            <path d="M12 2 L13.3 10.7 L22 12 L13.3 13.3 L12 22 L10.7 13.3 L2 12 L10.7 10.7 Z"
                  fill="white"/>
          </svg>`,
      },
    },
    {
      name: "nemotron 3 super",
      display: "Nemotron 3 Super",
      size: "120B",
      company: "NVIDIA",
      logo: {
        kind: "text",
        bg: "#76b900",
        fg: "#0f1115",
        text: "N",
        fontSize: "18px",
        weight: 800,
      },
    },
  ];

  function renderSuggestions() {
    if (!suggestGrid) return;
    SUGGESTIONS.forEach((s, idx) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "suggest-card";
      card.setAttribute(
        "aria-label",
        `${s.display}${s.size ? " " + s.size : ""} (${s.company})`,
      );

      const logo = document.createElement("span");
      logo.className = "suggest-logo";
      logo.style.background = s.logo.bg;
      if (s.logo.kind === "text") {
        logo.textContent = s.logo.text;
        logo.style.color = s.logo.fg;
        logo.style.fontSize = s.logo.fontSize;
        logo.style.fontWeight = String(s.logo.weight);
      } else {
        logo.innerHTML = s.logo.svg;
      }

      const main = document.createElement("span");
      main.className = "suggest-main";
      const name = document.createElement("span");
      name.className = "suggest-name";
      name.textContent = s.display;
      const meta = document.createElement("span");
      meta.className = "suggest-meta";
      meta.textContent = `${s.size ? s.size + " · " : ""}${s.company}`;
      main.appendChild(name);
      main.appendChild(meta);

      card.appendChild(logo);
      card.appendChild(main);
      card.style.animationDelay = `${idx * 60}ms`;
      card.addEventListener("click", () => onPickSuggestion(s));
      suggestGrid.appendChild(card);
    });
  }

  function onPickSuggestion(s) {
    const text = s.size ? `${s.name} ${s.size}` : s.name;
    input.value = text;
    // Fire the form's submit handler so the composer runs the normal
    // path (trim → clear → submitQuery → pill animation).
    form.requestSubmit();
  }

  function hideWelcome() {
    if (welcome && !welcome.classList.contains("is-hidden")) {
      welcome.classList.add("is-hidden");
    }
  }

  marked.setOptions({ gfm: true, breaks: false });

  function render(text) {
    return DOMPurify.sanitize(marked.parse(text ?? ""));
  }

  function scrollToBottom() {
    chat.scrollTop = chat.scrollHeight;
  }

  function addUserMessage(text) {
    const el = document.createElement("div");
    el.className = "msg user";
    el.innerHTML = `<div class="bubble"></div>`;
    el.querySelector(".bubble").textContent = text;
    chat.appendChild(el);
    scrollToBottom();
  }

  function addAssistantPending() {
    const el = document.createElement("div");
    el.className = "msg assistant";
    el.innerHTML = `
      <div class="meta"><span class="spinner"></span>Processing…</div>
      <div class="agents" role="status" aria-label="agent status"></div>
      <div class="bubble markdown hidden">Generating report…</div>
    `;
    chat.appendChild(el);
    scrollToBottom();
    return el;
  }

  const COLLECTOR_SOURCES = [
    { id: "arcalive", label: "ArcaLive" },
    { id: "arxiv", label: "arXiv" },
    { id: "benchmark", label: "Benchmark" },
    { id: "geeknews", label: "GeekNews" },
    { id: "lobsters", label: "Lobsters" },
    { id: "openai", label: "OpenAI Blog" },
    { id: "reddit", label: "Reddit" },
  ];
  const COLLECTOR_STAGES = [
    { id: "collect", label: "collect" },
    { id: "validate", label: "validate" },
  ];

  const PHASES = [
    {
      id: "query-generator",
      num: 1,
      title: "Query Generator",
      description: "Extract model names from query",
      layout: "flat",
      ids: ["query-generator"],
    },
    {
      id: "collectors",
      num: 2,
      title: "Data Collectors",
      description: "Collect and validate 7 sources in parallel",
      layout: "sources",
      sources: COLLECTOR_SOURCES,
      stages: COLLECTOR_STAGES,
      // Flat list of every pill ID inside this phase, used by phaseState().
      ids: COLLECTOR_SOURCES.flatMap((s) =>
        COLLECTOR_STAGES.map((st) => `${s.id}-${st.id}`),
      ),
    },
    {
      id: "reporter",
      num: 3,
      title: "Reporter",
      description: "Compose the final briefing",
      layout: "flat",
      ids: ["reporter"],
    },
  ];

  function phaseState(phase, agentsById) {
    const statuses = phase.ids.map((id) => agentsById[id]?.status || "pending");
    if (statuses.some((s) => s === "error")) return "error";
    if (statuses.every((s) => s === "done")) return "done";
    if (statuses.some((s) => s === "working")) return "working";
    return "pending";
  }

  function escapeAttr(s) {
    return String(s).replace(/"/g, "&quot;");
  }

  function renderAgents(el, agents) {
    const container = el.querySelector(".agents");
    const agentsById = Object.fromEntries(agents.map((a) => [a.id, a]));

    // Build once, then update statuses in-place to avoid layout thrash.
    if (!container.dataset.built) {
      const connectorSvg = `
        <svg viewBox="0 0 14 36" aria-hidden="true">
          <line class="connector-line" x1="7" y1="0" x2="7" y2="26"
                stroke="currentColor" stroke-width="2"
                stroke-dasharray="3 3" stroke-linecap="round"/>
          <polygon points="2,24 12,24 7,34" fill="currentColor"/>
        </svg>`;

      const flatPill = (aid) => `
        <span class="agent-pill" data-id="${aid}" data-status="pending">
          <span class="agent-indicator"></span>
          <span class="agent-label"></span>
        </span>`;

      const stagePill = (aid) => `
        <span class="agent-pill stage-pill" data-id="${aid}" data-status="pending">
          <span class="agent-indicator"></span>
          <span class="agent-label"></span>
        </span>`;

      const sourceCard = (phase, source) => `
        <div class="source-card" data-source="${source.id}">
          <div class="source-name">${escapeAttr(source.label)}</div>
          <div class="source-stages">
            ${phase.stages
              .map(
                (stage, i) => `
                ${i > 0 ? `<span class="stage-arrow" aria-hidden="true">→</span>` : ""}
                ${stagePill(`${source.id}-${stage.id}`)}`,
              )
              .join("")}
          </div>
        </div>`;

      const renderBody = (phase) =>
        phase.layout === "sources"
          ? `<div class="sources-grid">${phase.sources
              .map((s) => sourceCard(phase, s))
              .join("")}</div>`
          : phase.ids.map(flatPill).join("");

      container.innerHTML = PHASES.map(
        (phase, idx) => `
          ${idx > 0 ? `<div class="phase-arrow" data-for="${phase.id}" data-state="inactive">${connectorSvg}</div>` : ""}
          <div class="phase" data-phase="${phase.id}" data-state="pending">
            <div class="phase-header">
              <span class="phase-num">${phase.num}</span>
              <div class="phase-meta">
                <div class="phase-title">${escapeAttr(phase.title)}</div>
                <div class="phase-desc">${escapeAttr(phase.description)}</div>
              </div>
            </div>
            <div class="phase-body">
              ${renderBody(phase)}
            </div>
          </div>`,
      ).join("");

      // Fill pill labels from the server-provided list.
      agents.forEach((a) => {
        const label = container.querySelector(
          `.agent-pill[data-id="${a.id}"] .agent-label`,
        );
        if (label) label.textContent = a.label;
      });

      container.dataset.built = "1";
    }

    // Update pill statuses.
    agents.forEach((a) => {
      const pill = container.querySelector(`.agent-pill[data-id="${a.id}"]`);
      if (pill && pill.dataset.status !== a.status) {
        pill.dataset.status = a.status;
      }
    });

    // Update phase-level + arrow states derived from pill statuses.
    PHASES.forEach((phase, idx) => {
      const phaseEl = container.querySelector(
        `.phase[data-phase="${phase.id}"]`,
      );
      const state = phaseState(phase, agentsById);
      if (phaseEl && phaseEl.dataset.state !== state) {
        phaseEl.dataset.state = state;
      }
      if (idx === 0) return;
      // Arrow leading into this phase is "active" once the previous phase is done.
      const prev = PHASES[idx - 1];
      const prevState = phaseState(prev, agentsById);
      const arrow = container.querySelector(
        `.phase-arrow[data-for="${phase.id}"]`,
      );
      if (arrow) {
        const next =
          prevState === "done" ? "active" : prevState === "error" ? "error" : "inactive";
        if (arrow.dataset.state !== next) arrow.dataset.state = next;
      }
    });
  }

  function updateMeta(el, agents, overallStatus) {
    const meta = el.querySelector(".meta");
    if (overallStatus === "done") return; // setAssistantDone overwrites
    if (overallStatus === "error") return;
    const agentsById = Object.fromEntries(agents.map((a) => [a.id, a]));
    const doneCount = agents.filter((a) => a.status === "done").length;
    let activePhase = PHASES.find(
      (p) => phaseState(p, agentsById) === "working",
    );
    if (!activePhase) {
      activePhase = PHASES.find(
        (p) => phaseState(p, agentsById) === "pending",
      );
    }
    const label = activePhase ? activePhase.title : "Pipeline";
    meta.innerHTML = `<span class="spinner"></span>${label} running… (${doneCount}/${agents.length})`;
  }

  function setAssistantDone(el, markdown, reportName) {
    el.classList.remove("error");
    // Hide internal file extension from the user-facing label.
    const cleanName = reportName
      ? reportName.replace(/\.report\.md$/, "").replace(/^\d+-/, "")
      : null;
    el.querySelector(".meta").textContent = cleanName
      ? `Briefing · ${cleanName}`
      : "Done";
    // Collapse the phase diagram now that the final briefing is ready.
    const agents = el.querySelector(".agents");
    if (agents) agents.classList.add("is-hidden");
    const bubble = el.querySelector(".bubble");
    bubble.classList.remove("hidden");
    bubble.innerHTML = render(markdown);
    scrollToBottom();
  }

  function setAssistantError(el, error) {
    el.classList.add("error");
    el.querySelector(".meta").textContent = "Error";
    const bubble = el.querySelector(".bubble");
    bubble.classList.remove("hidden");
    bubble.textContent = error;
    scrollToBottom();
  }

  // ── history sidebar ────────────────────────────────────────────────

  function runIdToTimeLabel(runId) {
    const m = runId.match(/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/);
    if (!m) return runId.slice(0, 15);
    return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
  }

  function renderHistory(items) {
    historyList.innerHTML = "";
    if (!items || items.length === 0) {
      const empty = document.createElement("li");
      empty.className = "history-empty";
      empty.textContent = "No history yet.";
      historyList.appendChild(empty);
      return;
    }
    items.forEach((item) => {
      const li = document.createElement("li");
      li.className = "history-item";
      li.dataset.runId = item.run_id;

      const query = document.createElement("div");
      query.className = "history-query";
      query.textContent = item.user_query || "(no query)";

      const meta = document.createElement("div");
      meta.className = "history-meta";
      const time = document.createElement("span");
      time.className = "history-time";
      time.textContent = runIdToTimeLabel(item.run_id);
      const products = document.createElement("span");
      products.className = "history-products";
      const ps = Array.isArray(item.products) ? item.products : [];
      products.textContent =
        ps.length === 0
          ? ""
          : ps.length <= 2
            ? ps.join(" · ")
            : `${ps.slice(0, 2).join(" · ")} +${ps.length - 2}`;
      meta.appendChild(time);
      meta.appendChild(products);

      li.appendChild(query);
      li.appendChild(meta);
      li.addEventListener("click", () => openHistoryRun(item));
      historyList.appendChild(li);
    });
  }

  async function fetchHistory() {
    try {
      const res = await fetch("/api/history");
      if (!res.ok) return;
      const items = await res.json();
      renderHistory(items);
    } catch {
      // silent — sidebar just stays empty
    }
  }

  function setActiveHistoryItem(runId) {
    historyList
      .querySelectorAll(".history-item")
      .forEach((el) => el.classList.remove("is-active"));
    if (runId) {
      const el = historyList.querySelector(`.history-item[data-run-id="${runId}"]`);
      if (el) el.classList.add("is-active");
    }
  }

  function clearChat() {
    chat.querySelectorAll(".msg").forEach((m) => m.remove());
  }

  async function openHistoryRun(item) {
    setActiveHistoryItem(item.run_id);
    clearChat();
    hideWelcome();

    addUserMessage(item.user_query || "(no query)");
    const el = addAssistantPending();
    // Historical view — no live pipeline, so hide the phase diagram and
    // show a static meta line referring to this run.
    const agentsEl = el.querySelector(".agents");
    if (agentsEl) agentsEl.classList.add("is-hidden");
    el.querySelector(".meta").textContent = `Briefing · ${runIdToTimeLabel(item.run_id)}`;
    const bubble = el.querySelector(".bubble");

    try {
      const markdown = await fetchReport(item.run_id);
      bubble.classList.remove("hidden");
      bubble.innerHTML = render(markdown);
    } catch (err) {
      el.classList.add("error");
      bubble.classList.remove("hidden");
      bubble.textContent = `Error loading report: ${err.message || err}`;
    }
    scrollToBottom();
  }

  function startNewChat() {
    clearChat();
    setActiveHistoryItem(null);
    if (welcome) welcome.classList.remove("is-hidden");
    input.focus();
  }

  newChatBtn.addEventListener("click", startNewChat);

  // ── config + job ───────────────────────────────────────────────────

  async function fetchConfig() {
    try {
      const res = await fetch("/api/config");
      if (!res.ok) return;
      const cfg = await res.json();
      if (cfg.stub_mode) {
        modeBadge.textContent = "STUB";
        modeBadge.title = "stub mode — set NAT_UI_STUB=0 to use the real e2e agent";
      } else {
        modeBadge.textContent = "LIVE";
        modeBadge.classList.add("live");
        modeBadge.title = `e2e agent: ${cfg.e2e_url}`;
      }
    } catch {
      modeBadge.textContent = "?";
    }
  }

  async function createJob(query) {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) throw new Error(`POST /api/chat failed: ${res.status}`);
    return (await res.json()).job_id;
  }

  async function pollJob(jobId, onTick) {
    while (true) {
      const res = await fetch(`/api/chat/${jobId}`);
      if (!res.ok) throw new Error(`GET /api/chat/${jobId} failed: ${res.status}`);
      const data = await res.json();
      if (onTick) onTick(data);
      if (data.status === "done") return data;
      if (data.status === "error") throw new Error(data.error || "unknown error");
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
    }
  }

  async function fetchReport(name) {
    const res = await fetch(`/api/reports/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error(`GET /api/reports/${name} failed: ${res.status}`);
    return await res.text();
  }

  async function submitQuery(query) {
    hideWelcome();
    addUserMessage(query);
    const pendingEl = addAssistantPending();
    sendBtn.disabled = true;
    try {
      const jobId = await createJob(query);
      const status = await pollJob(jobId, (data) => {
        if (data.agents) {
          renderAgents(pendingEl, data.agents);
          updateMeta(pendingEl, data.agents, data.status);
        }
      });
      const markdown = await fetchReport(status.report_name);
      setAssistantDone(pendingEl, markdown, status.report_name);
      fetchHistory();
    } catch (err) {
      setAssistantError(pendingEl, String(err.message || err));
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    input.style.height = "auto";
    submitQuery(q);
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 200) + "px";
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  renderSuggestions();
  fetchConfig();
  fetchHistory();
  input.focus();
})();
