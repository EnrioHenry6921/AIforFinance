/* JE Audit dashboard - reads data/dashboard.json produced by `python -m pipeline.run` */
(() => {
  "use strict";

  // ---------------------------------------------------------------- icons
  const P = (d, extra = "") => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" ${extra}>${d}</svg>`;
  const ICON = {
    home: P('<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>'),
    alert: P('<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>'),
    chart: P('<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>'),
    brain: P('<path d="M12 3v18M7 7a3 3 0 1 1 5-2M17 7a3 3 0 1 0-5-2M6 12a3 3 0 0 0 6 0M18 12a3 3 0 0 1-6 0M7 17a3 3 0 0 0 5 2M17 17a3 3 0 0 1-5 2"/>'),
    spark: P('<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 3v4M17 5h4M5 17v4M3 19h4"/>'),
    book: P('<path d="M4 4h10a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4z"/><path d="M4 16a4 4 0 0 1 4-4h10"/>'),
    check: P('<path d="M5 13l4 4L19 7"/>', 'stroke-width="3"'),
    search: P('<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>'),
    doc: P('<path d="M6 2h9l5 5v15H6z"/><path d="M14 2v6h6"/>'),
    wallet: P('<rect x="2" y="6" width="20" height="14" rx="3"/><path d="M16 13h2M2 10h20"/>'),
    target: P('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>'),
    clock: P('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
    moon: P('<path d="M21 13A9 9 0 1 1 11 3a7 7 0 0 0 10 10z"/>'),
    user: P('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
    hand: P('<path d="M7 11V5a2 2 0 0 1 4 0v6M11 10V4a2 2 0 0 1 4 0v7M15 9a2 2 0 0 1 4 0v5a7 7 0 0 1-14 0v-2a2 2 0 0 1 4 0"/>'),
    download: P('<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>'),
    shield: P('<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>'),
    trend: P('<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>'),
    arrow: P('<path d="M5 12h14M13 6l6 6-6 6"/>'),
  };
  document.querySelectorAll("[data-icon]").forEach(el => (el.innerHTML = ICON[el.dataset.icon] || ""));

  const PAGES = [
    ["dashboard", "Dashboard", "home"], ["alerts", "Alerts & memos", "alert"], ["analytics", "Data & EDA", "chart"],
    ["models", "Models & prediction", "brain"], ["genai", "Gen AI & prompts", "spark"], ["method", "Method", "book"],
  ];
  const P1 = new Set(["Posted on a weekend", "Posted on a public holiday", "Posted in the year-end closing window",
    "Revenue booked at year end", "Entered long after the posting date", "Entered at night", "Entered on a weekend"]);
  const paramOf = r => (P1.has(r) ? "P1 Timing" : "P2 Amount");
  const TYPE_LABEL = {
    weekend_posting: "Weekend posting", holiday_posting: "Holiday posting", year_end_revenue: "Year-end revenue",
    night_entry: "Night entry", late_entry: "Late entry (backdating)", round_amount: "Round amount",
    split_below_threshold: "Split below threshold",
  };

  // ---------------------------------------------------------------- helpers
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const nf = (n, d = 0) => Number(n).toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
  const eur = (n, d = 2) => "€" + nf(n, d);
  const eurShort = n => (n >= 1e6 ? "€" + nf(n / 1e6, 1) + "m" : n >= 1e3 ? "€" + nf(n / 1e3, 0) + "k" : eur(n, 0));
  const pct = (x, d = 0) => (x === null || x === undefined ? "n/a" : nf(x * 100, d) + "%");
  const dmy = s => (s ? s.slice(8, 10) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4) : "");
  const scoreColor = s => (s >= 75 ? "var(--red)" : s >= 50 ? "var(--orange)" : s >= 30 ? "var(--blue)" : "var(--muted)");
  const toast = msg => { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 2600); };
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  };

  let D = null;
  const S = {
    cutoff: 50, minScore: 0, q: "", param: "all", status: "all", source: "all", shown: 50,
    decisions: store.get("je-audit-decisions", {}), memos: store.get("je-audit-memos", {}),
    aiOnline: false, model: store.get("je-audit-model", "llama3:latest"), language: "English",
  };
  const charts = {};
  const mkChart = (id, cfg) => { if (charts[id]) charts[id].destroy(); const el = document.getElementById(id); if (el) charts[id] = new Chart(el, cfg); };

  // Chart.js theme
  Chart.defaults.color = "#a0aec0";
  Chart.defaults.font.family = '"Plus Jakarta Sans", Inter, system-ui, sans-serif';
  Chart.defaults.font.size = 11;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.tooltip.backgroundColor = "#0b1437";
  Chart.defaults.plugins.tooltip.borderColor = "rgba(255,255,255,.12)";
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  const gridC = "rgba(255,255,255,.06)";
  const axes = (extra = {}) => ({
    x: { grid: { display: false }, border: { display: false }, ...extra.x },
    y: { grid: { color: gridC, borderDash: [5, 5] }, border: { display: false }, ...extra.y },
  });
  const grad = (ctx, c1, c2) => { const g = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height || 300); g.addColorStop(0, c1); g.addColorStop(1, c2); return g; };

  // ---------------------------------------------------------------- data access
  const decisionOf = id => S.decisions[id]?.decision || "";
  const alertsAll = () => D.alerts;
  const isAlert = a => a.score >= S.cutoff;
  function filtered() {
    const q = S.q.toLowerCase();
    return D.alerts.filter(a => {
      if (a.score < Math.max(S.minScore, 0)) return false;
      if (S.source !== "all" && a.source !== S.source) return false;
      if (S.param !== "all" && !a.rules.some(r => paramOf(r) === S.param)) return false;
      const dec = decisionOf(a.id);
      if (S.status === "open" && dec) return false;
      if (!["all", "open"].includes(S.status) && dec !== S.status) return false;
      if (q && !`${a.id} ${a.user} ${a.text} ${a.accounts} ${a.rules.join(" ")}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }
  const memoOf = a => S.memos[a.id] || a.memo;

  // ---------------------------------------------------------------- local AI (Ollama, runs on the auditor's computer)
  const OLLAMA = "http://localhost:11434";
  async function checkAI() {
    try {
      const c = new AbortController(); setTimeout(() => c.abort(), 2500);
      const r = await fetch(OLLAMA + "/api/tags", { signal: c.signal });
      const j = await r.json();
      S.aiOnline = true; S.aiModels = (j.models || []).map(m => m.name);
    } catch { S.aiOnline = false; S.aiModels = []; }
    $("#aiDot").className = "dot " + (S.aiOnline ? "on" : "off");
    $("#aiText").textContent = S.aiOnline ? "Local AI online" : "Local AI offline";
  }
  async function aiChat(system, user) {
    const r = await fetch(OLLAMA + "/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: S.model, stream: false, format: "json", options: { temperature: 0.2 },
        messages: [{ role: "system", content: system }, { role: "user", content: user }] }),
    });
    if (!r.ok) throw new Error("Ollama answered " + r.status);
    const j = await r.json();
    return JSON.parse(j.message.content);
  }
  // fills a Python str.format template ({key}, {key:,.2f}, {{ }})
  function fill(tpl, f) {
    return tpl.replace(/\{\{/g, "\u0001").replace(/\}\}/g, "\u0002")
      .replace(/\{(\w+)(?::([^}]*))?\}/g, (m, k, spec) => {
        const v = f[k]; if (v === undefined) return m;
        if (spec && /\.(\d)f/.test(spec)) { const d = +spec.match(/\.(\d)f/)[1]; return Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); }
        return String(v);
      }).replace(/\u0001/g, "{").replace(/\u0002/g, "}");
  }
  const lib = name => D.prompts.library.find(p => p.name.startsWith(name)).text;
  function memoFacts(a) {
    const [code, ...nm] = a.main_account.split(" ");
    const pm = D.settings.performance_materiality[a.posting_date.slice(0, 4)] ?? Object.values(D.settings.performance_materiality)[0];
    const pd = new Date(a.posting_date);
    return {
      entry_id: a.id, source: a.source, nature: a.nature, posting_date: dmy(a.posting_date),
      weekday: pd.toLocaleDateString("en-GB", { weekday: "long" }), entered_at: dmy(a.entered_at) + " " + a.entered_at.slice(11),
      delay: a.delay, hour: a.entered_at.slice(11, 13), text: a.text, accounts: a.accounts, main_account: code,
      main_account_name: nm.join(" "), amount: a.amount, user: a.user, risk_score: a.score,
      rules: a.rules.join(", ") || "none", shap: a.shap.map(s => `${s.feature} (+${s.shap})`).join("; ") || "none",
      threshold: D.settings.approval_threshold, perf_mat: pm,
    };
  }

  // ---------------------------------------------------------------- UI pieces
  const kpi = (lbl, val, delta, icon, cls = "") => `
    <div class="card kpi"><div><div class="lbl">${lbl}</div><div class="val">${val}${delta ? `<small class="${delta.c}">${delta.t}</small>` : ""}</div></div>
    <div class="icon-sq ${cls}">${ICON[icon]}</div></div>`;
  const scoreCell = s => `<div class="score-cell"><span class="n" style="color:${scoreColor(s)}">${nf(s, 0)}</span><span class="muted tiny"> /100</span><div class="bar"><i style="width:${s}%;background:${scoreColor(s)}"></i></div></div>`;
  const ruleTag = r => `<span class="tag ${paramOf(r) === "P1 Timing" ? "blue" : "purple"}">${esc(r)}</span>`;
  const decTag = d => d === "retained" ? '<span class="tag red">Retained</span>' : d === "dismissed" ? '<span class="tag gray">Dismissed</span>'
    : d === "investigate" ? '<span class="tag orange">To investigate</span>' : '<span class="tag blue">Open</span>';

  function semiGauge(value, color1 = "#0075ff", color2 = "#3d8bff") {
    const r = 80, c = Math.PI * r, v = Math.max(0, Math.min(1, value));
    return `<svg width="220" height="130" viewBox="0 0 220 130"><defs><linearGradient id="gg" x1="0" x2="1"><stop offset="0" stop-color="${color1}"/><stop offset="1" stop-color="${color2}"/></linearGradient></defs>
      <path d="M30 115 A80 80 0 0 1 190 115" fill="none" stroke="#22234b" stroke-width="12" stroke-linecap="round"/>
      <path d="M30 115 A80 80 0 0 1 190 115" fill="none" stroke="url(#gg)" stroke-width="12" stroke-linecap="round" stroke-dasharray="${c * v} ${c}"/></svg>`;
  }
  function ringGauge(value, size = 170) {
    const r = size / 2 - 12, c = 2 * Math.PI * r, v = Math.max(0, Math.min(1, value)), arc = 0.75;
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="transform:rotate(135deg)"><defs><linearGradient id="rg" x1="0" x2="1"><stop offset="0" stop-color="#05a57e"/><stop offset="1" stop-color="#05a57e"/></linearGradient></defs>
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="#22234b" stroke-width="11" stroke-linecap="round" stroke-dasharray="${c * arc} ${c}"/>
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="url(#rg)" stroke-width="11" stroke-linecap="round" stroke-dasharray="${c * arc * v} ${c}"/></svg>`;
  }

  // ---------------------------------------------------------------- pages
  function renderDashboard() {
    const k = D.kpis, m = D.metrics, comb = m.models["Risk score (combined)"], demo = k.injected > 0;
    const alerts = alertsAll().filter(isAlert);
    const held = m.by_type.filter(t => t.held_out);
    const heldRecall = held.length ? held.reduce((s, t) => s + t.combined * t.n, 0) / held.reduce((s, t) => s + t.n, 0) : 0;
    const reviewed = alerts.filter(a => decisionOf(a.id)).length;
    const hours = D.charts.hours;
    const night = D.charts.flags_all["Entered at night"] || 0, late = D.charts.flags_all["Entered long after the posting date"] || 0;

    $("#page-dashboard").innerHTML = `
      <div class="grid g4">
        ${kpi("Entries tested", nf(k.entries), { t: "100%", c: "green" }, "doc")}
        ${kpi("Alerts to review", nf(alerts.length), { t: pct(alerts.length / k.entries, 2), c: "orange" }, "alert", "purple")}
        ${demo ? kpi("Demo anomalies found", `${k.found}/${k.injected}`, { t: pct(k.found / Math.max(k.injected, 1)), c: "green" }, "target", "teal") : kpi("Manual entries", nf(k.manual), { t: "real data only", c: "muted" }, "hand", "teal")}
        ${kpi("Amount tested", eurShort(k.amount_tested), { t: "all entries", c: "muted" }, "wallet")}
      </div>
      <div class="grid g-hero">
        <div class="card hero">
          <div><div class="hi">Engagement overview</div><h2>Testing 100% of journal entries</h2>
            <p>Every entry of the ledger was scored by rules, an outlier model and a predictive model. A local AI wrote the memos. You decide.</p></div>
          <div><div class="big">${nf(k.entries)}</div><div class="muted small">entries scored · ${nf(k.manual)} manual · ${D.dataset.datacard.period}</div>
            <button class="link" style="margin-top:14px" onclick="location.hash='alerts'">Start triage ${ICON.arrow}</button></div>
        </div>
        <div class="card">
          <h3>Detection rate</h3><div class="sub">Demo anomalies caught by the risk score</div>
          <div class="gauge-wrap">${semiGauge(demo ? comb.recall : 0)}<div class="gauge-center">${ICON.target}</div></div>
          <div class="gauge-box"><span class="muted small">0%</span><div class="c"><div class="v">${demo ? pct(comb.recall) : "n/a"}</div><div class="muted tiny">${demo ? `${k.found} demo + ${k.real_alerts} real alerts` : "no demo anomalies injected"}</div></div><span class="muted small">100%</span></div>
        </div>
        <div class="card">
          <div class="card-head"><div><h3>Circularity test</h3><div class="sub">Patterns the ML never saw in training</div></div></div>
          <div class="ref">
            <div><div class="mini"><div class="muted small">Real entries flagged</div><div class="v">${nf(k.real_alerts)}</div></div>
              <div class="mini"><div class="muted small">Reviewed so far</div><div class="v">${reviewed} / ${alerts.length}</div></div></div>
            <div class="ring-wrap">${ringGauge(heldRecall)}<div class="ring-label"><div class="muted tiny">Unseen types</div><div class="v">${demo ? pct(heldRecall) : "n/a"}</div><div class="t">caught</div></div></div>
          </div>
        </div>
      </div>
      <div class="grid g-wide">
        <div class="card"><div class="card-head"><div><h3>Entries per month</h3><div class="sub"><span class="green bold">${nf(alerts.length)} alerts</span> across ${D.charts.monthly.length} months</div></div></div>
          <div class="chart-box"><canvas id="cMonthly"></canvas></div></div>
        <div class="card"><div class="bar-panel"><div class="chart-box xs"><canvas id="cHours"></canvas></div></div>
          <h3 style="margin-top:18px">Entry times</h3><div class="sub">When users type entries into the system (hour of day)</div>
          <div class="stats4">
            ${[["Manual", k.manual, "hand", k.manual / k.entries * 20], ["Night", night, "moon", night / k.entries * 50], ["Late", late, "clock", late / k.entries * 50], ["Users", D.dataset.datacard.users, "user", 60]]
              .map(([l, v, i, w]) => `<div class="stat"><div class="lab"><span class="mi">${ICON[i]}</span>${l}</div><div class="v">${nf(v)}</div><div class="prog"><i style="width:${Math.min(100, Math.max(8, w))}%"></i></div></div>`).join("")}
          </div></div>
      </div>
      <div class="grid g-wide">
        <div class="card"><div class="card-head"><div><h3>Priority alerts</h3><div class="sub"><span class="green">●</span> ${reviewed} reviewed · ${alerts.length - reviewed} open</div></div>
          <button class="btn ghost" onclick="location.hash='alerts'">All alerts ${ICON.arrow}</button></div>
          <div class="table-wrap"><table><thead><tr><th>Entry</th><th>User</th><th>Amount</th><th>Red flags</th><th>Risk</th></tr></thead><tbody>
          ${alerts.slice(0, 7).map(a => `<tr class="click" data-id="${esc(a.id)}"><td><div class="bold">${esc(a.text)}</div><div class="muted tiny">${esc(a.id)} · ${dmy(a.posting_date)}</div></td>
            <td>${esc(a.user)}</td><td class="bold">${eur(a.amount)}</td><td><div class="chips">${a.rules.slice(0, 2).map(ruleTag).join("")}</div></td><td>${scoreCell(a.score)}</td></tr>`).join("")}
          </tbody></table></div></div>
        <div class="card"><h3>Alerts by parameter</h3><div class="sub">Which red flags drive the alerts</div>
          <div class="donut-wrap" style="margin-top:14px"><div class="chart-box sm"><canvas id="cParam"></canvas></div><div class="legend" id="paramLegend"></div></div>
          <h3 style="margin-top:22px;font-size:15px">Latest activity</h3>
          <div class="timeline" style="margin-top:14px">${timeline()}</div></div>
      </div>`;

    // charts
    const mo = D.charts.monthly;
    mkChart("cMonthly", {
      type: "line",
      data: { labels: mo.map(x => x.month), datasets: [
        { label: "System entries", data: mo.map(x => x.system), borderColor: "#0075ff", fill: true, tension: .42, pointRadius: 0, borderWidth: 2.5,
          backgroundColor: c => grad(c.chart.ctx, "rgba(0,117,255,.45)", "rgba(0,117,255,0)") },
        { label: "Alerts", data: mo.map(x => x.alerts), borderColor: "#21d4fd", fill: true, tension: .42, pointRadius: 0, borderWidth: 2.5, yAxisID: "y1",
          backgroundColor: c => grad(c.chart.ctx, "rgba(33,212,253,.28)", "rgba(33,212,253,0)") },
      ] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        scales: { ...axes({ x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } } }), y1: { position: "right", grid: { display: false }, border: { display: false } } },
        plugins: { legend: { position: "top", align: "end" } } },
    });
    mkChart("cHours", {
      type: "bar", data: { labels: hours.map(h => h.hour), datasets: [{ data: hours.map(h => h.n), backgroundColor: "#fff", borderRadius: 8, barThickness: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
        scales: { x: { grid: { display: false }, border: { display: false }, ticks: { color: "#fff", maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } },
          y: { grid: { display: false }, border: { display: false }, ticks: { color: "#fff", maxTicksLimit: 5 } } } },
    });
    const byParam = {}; alerts.forEach(a => new Set(a.rules.map(paramOf)).forEach(p => (byParam[p] = (byParam[p] || 0) + 1)));
    const pl = Object.entries(byParam), cols = ["#0075ff", "#9f5bff", "#21d4fd", "#e14eca"];
    mkChart("cParam", { type: "doughnut", data: { labels: pl.map(p => p[0]), datasets: [{ data: pl.map(p => p[1]), backgroundColor: cols, borderWidth: 0, spacing: 4, borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "72%", plugins: { legend: { display: false } } } });
    $("#paramLegend").innerHTML = pl.map((p, i) => `<div class="row"><span class="sw" style="border-color:${cols[i]}"></span><div><div class="bold">${p[1]} alerts</div><div class="muted tiny">${p[0]}</div></div></div>`).join("")
      + `<div class="muted tiny">One alert can carry both.</div>`;
  }

  function timeline() {
    const dec = Object.entries(S.decisions).sort((a, b) => (b[1].ts || "").localeCompare(a[1].ts || "")).slice(0, 4);
    const items = dec.length ? dec.map(([id, d]) => ({ t: `${id} marked ${d.decision}`, d: new Date(d.ts).toLocaleString("en-GB"), c: d.decision === "retained" ? "var(--red)" : d.decision === "dismissed" ? "#56577a" : "var(--orange)" }))
      : alertsAll().slice(0, 4).map(a => ({ t: `${eur(a.amount, 0)}, ${a.text}`, d: `${dmy(a.posting_date)} · score ${nf(a.score)} · memo ready`, c: scoreColor(a.score) }));
    return items.map(i => `<div class="tl"><span class="b" style="background:${i.c}">${ICON.check}</span><div><div class="t">${esc(i.t)}</div><div class="d">${esc(i.d)}</div></div></div>`).join("");
  }

  function renderAlerts() {
    const rows = filtered();
    $("#page-alerts").innerHTML = `
      <div class="card">
        <div class="card-head"><div><h3>Alerts & audit memos</h3><div class="sub">Top ${nf(D.alerts.length)} entries by risk out of ${nf(D.kpis.entries)} scored · click a row to open the memo</div></div>
          <div style="display:flex;gap:8px"><button class="btn ghost" id="expCsv">${ICON.download} CSV</button><button class="btn" id="expXlsx">${ICON.download} Excel</button></div></div>
        <div class="filters">
          <label class="ctl">${ICON.search}<input type="text" id="fq" placeholder="Search…" value="${esc(S.q)}"></label>
          <label class="ctl">Min score <input type="range" id="fmin" min="0" max="100" value="${S.minScore}"><b id="fminv" style="color:#fff">${S.minScore}</b></label>
          <label class="ctl">Alert cut-off <input type="range" id="fcut" min="20" max="90" value="${S.cutoff}"><b id="fcutv" style="color:#fff">${S.cutoff}</b></label>
          <label class="ctl">Parameter <select id="fparam"><option value="all">All</option><option>P1 Timing</option><option>P2 Amount</option></select></label>
          <label class="ctl">Source <select id="fsrc"><option value="all">All</option><option value="manual">Manual</option><option value="system">System</option></select></label>
          <label class="ctl">Status <select id="fstat"><option value="all">All</option><option value="open">Open</option><option value="retained">Retained</option><option value="investigate">To investigate</option><option value="dismissed">Dismissed</option></select></label>
        </div>
        <div class="muted small" style="margin-bottom:8px">${nf(rows.length)} entries match · ${nf(rows.filter(isAlert).length)} above the cut-off</div>
        <div class="table-wrap"><table><thead><tr><th>Risk</th><th>Entry</th><th>Posted</th><th>User</th><th>Amount</th><th>Red flags</th><th>Status</th></tr></thead><tbody>
          ${rows.slice(0, S.shown).map(a => `<tr class="click" data-id="${esc(a.id)}" style="${isAlert(a) ? "" : "opacity:.6"}">
            <td>${scoreCell(a.score)}</td>
            <td><div class="bold">${esc(a.text)}</div><div class="muted tiny">${esc(a.id)} · ${esc(a.source)} · ${esc(a.nature)}${a.injected ? ' · <span class="orange">demo</span>' : ""}</div></td>
            <td>${dmy(a.posting_date)}</td><td>${esc(a.user)}</td><td class="bold">${eur(a.amount)}</td>
            <td><div class="chips">${a.rules.slice(0, 2).map(ruleTag).join("")}${a.rules.length > 2 ? `<span class="tag gray">+${a.rules.length - 2}</span>` : ""}${!a.rules.length ? '<span class="tag gray">ML only</span>' : ""}</div></td>
            <td>${decTag(decisionOf(a.id))}</td></tr>`).join("")}
        </tbody></table></div>
        ${rows.length > S.shown ? `<div style="text-align:center;margin-top:14px"><button class="btn ghost" id="more">Show more</button></div>` : ""}
      </div>`;
    $("#fparam").value = S.param; $("#fsrc").value = S.source; $("#fstat").value = S.status;
    const re = () => { S.shown = 50; renderAlerts(); };
    $("#fq").oninput = e => { S.q = e.target.value; clearTimeout(S._t); S._t = setTimeout(() => { re(); $("#fq").focus(); $("#fq").setSelectionRange(S.q.length, S.q.length); }, 250); };
    $("#fmin").oninput = e => { $("#fminv").textContent = e.target.value; }; $("#fmin").onchange = e => { S.minScore = +e.target.value; re(); };
    $("#fcut").oninput = e => { $("#fcutv").textContent = e.target.value; }; $("#fcut").onchange = e => { S.cutoff = +e.target.value; store.set("je-audit-cutoff", S.cutoff); re(); };
    $("#fparam").onchange = e => { S.param = e.target.value; re(); };
    $("#fsrc").onchange = e => { S.source = e.target.value; re(); };
    $("#fstat").onchange = e => { S.status = e.target.value; re(); };
    if ($("#more")) $("#more").onclick = () => { S.shown += 50; renderAlerts(); };
    $("#expCsv").onclick = () => exportFile("csv"); $("#expXlsx").onclick = () => exportFile("xlsx");
  }

  function renderAnalytics() {
    const c = D.dataset.datacard, b = D.charts.benford;
    $("#page-analytics").innerHTML = `
      <div class="grid g4">
        ${kpi("Ledger lines", nf(c.lines), null, "doc")}${kpi("Entries", nf(c.entries), { t: nf(c.manual_entries) + " manual", c: "muted" }, "book", "purple")}
        ${kpi("Users / accounts", `${c.users} / ${c.accounts}`, null, "user", "teal")}${kpi("Unbalanced · missing", `${c.unbalanced_entries} · ${c.missing_values}`, { t: "clean", c: "green" }, "shield")}
      </div>
      <div class="grid g2">
        <div class="card"><h3>Datacard</h3><div class="sub">${esc(D.dataset.name)} · ${esc(D.dataset.license)} · raw ledger, before the ${D.kpis.injected} demo anomalies</div>
          <div class="table-wrap" style="margin-top:10px"><table><tbody>
            <tr><td class="muted">Source</td><td><a href="${D.dataset.url}" target="_blank" rel="noopener" style="color:#6fb2ff">Zenodo · DOI ${esc(D.dataset.doi)}</a></td></tr>
            <tr><td class="muted">Authors</td><td>${esc(D.dataset.authors)}</td></tr>
            <tr><td class="muted">Format / period</td><td>${esc(c.format)} · ${esc(c.period)}</td></tr>
            <tr><td class="muted">Public holidays</td><td>${esc(D.dataset.holiday_country)} · ${D.dataset.holidays_in_period} days · ${esc(D.dataset.holiday_source)}</td></tr>
            <tr><td class="muted">Consistency checks</td><td>${c.unbalanced_entries} unbalanced entries · ${c.missing_values} missing values · ${c.entered_before_posting} entered before document date</td></tr>
          </tbody></table></div></div>
        <div class="card"><h3>Do we trust the data?</h3><div class="sub">What the EDA tells us before we model</div>
          <ul class="list" style="margin-top:10px">
            <li><b>Clean and balanced:</b> every entry balances, nothing is missing. So we <b>inject labelled anomalies</b> to test the system.</li>
            <li><b>Benford's law fails for the whole ledger</b> (MAD ${b.mad}). The retailer sells products at fixed prices, so the first digits follow the price list, not Benford. That's a known limit of Benford on price-driven data, so we use it <b>per user</b> as context, not as an alarm.</li>
            <li><b>System postings ignore public holidays</b> (${nf(D.charts.flags_all["Posted on a public holiday"])} entries on ${esc(D.dataset.holiday_country)} holidays), another sign the ledger was generated. So timing flags count fully only for <b>manual</b> entries.</li>
            <li><b>A German company</b> (SKR03 accounts, 19% VAT). We apply the French/international audit standard (NEP 240 / ISA 240), and the holiday country is a setting.</li>
            <li><b>No supplier or invoice number:</b> duplicate payments cannot be tested reliably.</li>
          </ul></div>
      </div>
      <div class="grid g2">
        <div class="card"><h3>First digit vs Benford's law</h3><div class="sub">All entry amounts</div><div class="chart-box"><canvas id="cBenford"></canvas></div></div>
        <div class="card"><h3>Users</h3><div class="sub">Volume, manual entries, alerts and Benford conformity per user</div>
          <div class="table-wrap" style="margin-top:8px"><table><thead><tr><th>User</th><th>Entries</th><th>Manual</th><th>Night</th><th>Alerts*</th><th>Benford MAD</th></tr></thead><tbody>
          ${D.charts.users.map(u => { const bu = b.by_user.find(x => x.user === u.user) || {}; return `<tr><td class="bold">${esc(u.user)}</td><td>${nf(u.entries)}</td><td>${nf(u.manual)}</td><td>${nf(u.night)}</td><td>${nf(u.alerts)}</td><td>${bu.mad ?? ""} <span class="tag ${bu.conformity === "close" ? "green" : bu.conformity === "nonconformity" ? "red" : "orange"}">${esc(bu.conformity || "")}</span></td></tr>`; }).join("")}
          </tbody></table></div><div class="muted tiny" style="margin-top:8px">* alerts at the pipeline cut-off (${D.settings.alert_cutoff}), including demo anomalies.</div></div>
      </div>
      <div class="grid g3">
        <div class="card"><h3>Postings by weekday</h3><div class="sub">Weekend postings are rare: a useful red flag</div><div class="chart-box sm"><canvas id="cWeek"></canvas></div></div>
        <div class="card"><h3>Risk score distribution</h3><div class="sub">All ${nf(D.kpis.entries)} entries (log scale)</div><div class="chart-box sm"><canvas id="cHist"></canvas></div></div>
        <div class="card"><h3>Amount posted per month</h3><div class="sub">Total debit of all entries (EUR)</div><div class="chart-box sm"><canvas id="cAmt"></canvas></div></div>
      </div>
      <div class="card"><h3>Red flags in the whole ledger</h3><div class="sub">Number of entries with each flag, before weighting (log scale) · <span style="color:#6fb2ff">P1 Timing</span> · <span style="color:#c8a6ff">P2 Amount</span></div><div class="chart-box"><canvas id="cFlags"></canvas></div></div>`;

    mkChart("cBenford", { type: "bar", data: { labels: b.overall.map(x => x.digit), datasets: [
      { type: "line", label: "Benford expected", data: b.overall.map(x => x.benford * 100), borderColor: "#21d4fd", pointRadius: 3, tension: .3 },
      { label: "Observed", data: b.overall.map(x => x.observed * 100), backgroundColor: "#0075ff", borderRadius: 8, barPercentage: .6 }] },
      options: { responsive: true, maintainAspectRatio: false, scales: axes({ y: { title: { display: true, text: "% of amounts" } } }) } });
    const wk = D.charts.weekday;
    mkChart("cWeek", { type: "bar", data: { labels: wk.map(w => w.day.slice(0, 3)), datasets: [{ data: wk.map(w => w.n), backgroundColor: wk.map((w, i) => i >= 5 ? "#e14eca" : "#0075ff"), borderRadius: 8 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: axes() } });
    const h = D.charts.score_hist;
    mkChart("cHist", { type: "bar", data: { labels: h.map((_, i) => `${i * 5}–${i * 5 + 5}`), datasets: [{ data: h, backgroundColor: h.map((_, i) => i * 5 >= S.cutoff ? "#ff4d6d" : "#9f5bff"), borderRadius: 5 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: axes({ x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 6 } }, y: { type: "logarithmic", ticks: { callback: v => ([1, 10, 100, 1000, 10000, 100000].includes(v) ? nf(v) : "") } } }) } });
    const fl = Object.entries(D.charts.flags_all).sort((a, b) => b[1] - a[1]);
    mkChart("cFlags", { type: "bar", data: { labels: fl.map(f => f[0]), datasets: [{ data: fl.map(f => f[1]), backgroundColor: fl.map(f => paramOf(f[0]) === "P1 Timing" ? "#0075ff" : "#9f5bff"), borderRadius: 6 }] },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { type: "logarithmic", grid: { color: gridC }, border: { display: false }, ticks: { maxRotation: 0, callback: v => ([1, 10, 100, 1000, 10000, 100000].includes(v) ? nf(v) : "") } }, y: { grid: { display: false }, ticks: { font: { size: 12 } } } } } });
    const mo = D.charts.monthly;
    mkChart("cAmt", { type: "bar", data: { labels: mo.map(x => x.month), datasets: [{ data: mo.map(x => x.amount), backgroundColor: c => grad(c.chart.ctx, "#21d4fd", "#0075ff"), borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: axes({ x: { ticks: { maxRotation: 0, maxTicksLimit: 6 } }, y: { ticks: { callback: v => eurShort(v) } } }) } });
  }

  function renderModels() {
    const m = D.metrics, f = D.forecast;
    if (!m.by_type.length) {
      $("#page-models").innerHTML = `<div class="card"><h3>No labelled anomalies in this run</h3><p class="muted" style="margin-top:8px">The data was scored with rules + Isolation Forest only (${esc(m.split)}). Run <code>python -m pipeline.run --inject 42</code> to train and evaluate XGBoost and run the circularity test.</p></div>`;
      return;
    }
    const models = Object.entries(m.models);
    const kk = Object.keys(models[0][1]).find(x => x.startsWith("precision_at_"));
    const heat = v => `background:rgba(${v >= .8 ? "1,181,116" : v >= .4 ? "255,181,71" : "255,77,109"},${.12 + v * .3})`;
    const flagged = (f.months || []).filter(x => x.flag);
    $("#page-models").innerHTML = `
      <div class="grid g-wide">
        <div class="card"><h3>Model comparison</h3><div class="sub">Against the labelled demo anomalies · ${esc(m.split)}</div>
          <div class="table-wrap" style="margin-top:10px"><table><thead><tr><th>Layer</th><th>Alerts</th><th>Precision</th><th>Recall</th><th>F1</th><th>${kk.replace(/_/g, " ")}</th><th>PR-AUC</th></tr></thead><tbody>
          ${models.map(([n, v]) => `<tr><td class="bold">${esc(n)}</td><td>${nf(v.alerts)}</td><td>${pct(v.precision)}</td><td>${pct(v.recall)}</td><td>${v.f1 ?? "-"}</td><td>${pct(v[kk])}</td><td>${v.pr_auc ?? "-"}</td></tr>`).join("")}
          <tr><td class="bold">XGBoost on test set</td><td>${nf(m.xgb_test_2024_and_held_out.alerts)}</td><td>${pct(m.xgb_test_2024_and_held_out.precision)}</td><td>${pct(m.xgb_test_2024_and_held_out.recall)}</td><td>${m.xgb_test_2024_and_held_out.f1 ?? "-"}</td><td>-</td><td>${m.xgb_test_2024_and_held_out.pr_auc}</td></tr>
          </tbody></table></div>
          <div class="note warn" style="margin-top:14px"><b>Why not the rules alone?</b> The rules score high partly because we planted exactly the patterns they look for (circular too). The combined score <b>ranks</b> best (highest PR-AUC and precision in the top ${kk.split("_").pop()}), which is what matters when the auditor works down the list, and it still catches patterns nobody wrote a rule for.</div>
          <div class="note" style="margin-top:10px"><b>Precision</b> counts only the planted anomalies as correct, so real entries worth reviewing (e.g. a December accrual posted on a Sunday and typed in in February) lower it. <b>How to read it:</b> each layer catches something different. The <b>rules</b> catch the red flags auditors already know. <b>XGBoost</b> predicts the probability of an anomaly from what it learned. <b>Isolation Forest</b> finds outliers without labels. The combined score raises an alert when <i>any</i> layer gives a strong signal.</div></div>
        <div class="card"><h3>Circularity test</h3><div class="sub">Recall by anomaly type · <span class="tag orange">held out</span> = never shown to XGBoost</div>
          <div class="table-wrap" style="margin-top:10px"><table class="matrix"><thead><tr><th>Type</th><th>n</th><th>Rules</th><th>IForest</th><th>XGB</th><th>Score</th></tr></thead><tbody>
          ${m.by_type.map(t => `<tr><td>${esc(TYPE_LABEL[t.type] || t.type)} ${t.held_out ? '<span class="tag orange">held out</span>' : ""}</td><td>${t.n}</td>${["rules", "iforest", "xgboost", "combined"].map(k => `<td class="c" style="${heat(t[k])}">${pct(t[k])}</td>`).join("")}</tr>`).join("")}
          </tbody></table></div>
          <div class="note warn" style="margin-top:14px">XGBoost scores 0% on the held-out types: it only finds what it was taught (the circularity risk). The rules and the combined score still catch them. That's why the ML never works alone.</div></div>
      </div>
      <div class="grid g-wide">
        <div class="card"><h3>Predictive analytics: expected vs actual revenue</h3><div class="sub">${esc(f.method || "")} · band ±${f.band_pct}%</div>
          <div class="chart-box lg"><canvas id="cFc"></canvas></div>
          <div style="margin-top:10px">${flagged.length ? flagged.map(x => `<span class="tag red">${x.month}: ${eurShort(x.actual)} vs ${eurShort(x.expected)} expected</span>`).join(" ") : '<span class="tag green">No month outside the band</span>'}</div></div>
        <div class="card"><h3>What drives XGBoost</h3><div class="sub">Feature importance (gain)</div><div class="chart-box lg"><canvas id="cImp"></canvas></div></div>
      </div>
      <div class="card"><h3>Scoring recipe</h3><div class="sub">Transparent and adjustable in <code>pipeline/config.py</code></div>
        <div class="grid g3" style="margin:14px 0 0">
          <div class="inner"><div class="bold">1 · Rules (points)</div><div class="chips" style="margin-top:10px">${Object.entries(m.rules).map(([r, w]) => `<span class="tag gray">${esc(r.replace(/_/g, " "))} ${w}</span>`).join("")}</div>
            <div class="muted small" style="margin-top:10px">Manual entries count 100%, system entries 25%; recurring manual entries (rent, salaries) 30%.</div></div>
          <div class="inner"><div class="bold">2 · Isolation Forest</div><div class="muted small" style="margin-top:8px">300 trees on the ${D.metrics.feature_importance.length} features; only the top 10% of outliers add to the score (max ${m.weights.iforest * 100}%).</div></div>
          <div class="inner"><div class="bold">3 · XGBoost + SHAP</div><div class="muted small" style="margin-top:8px">Predicts P(anomaly); SHAP values explain each entry. <code>is_manual</code> is excluded because it would leak the label.</div></div>
        </div>
        <div class="muted small" style="margin-top:12px">Risk = 100 × [1 − (1 − rules) × (1 − ${m.weights.xgb} × XGB) × (1 − ${m.weights.iforest} × outlier)] · alert at ≥ ${D.settings.alert_cutoff}</div></div>`;

    const labels = [...(f.history || []).map(x => x.month), ...(f.months || []).map(x => x.month)];
    const pad = (f.history || []).map(() => null);
    mkChart("cFc", { type: "line", data: { labels, datasets: [
      { label: "Band high", data: [...pad, ...f.months.map(x => x.high)], borderColor: "transparent", pointRadius: 0, fill: "+1", backgroundColor: "rgba(159,91,255,.15)" },
      { label: "Band low", data: [...pad, ...f.months.map(x => x.low)], borderColor: "transparent", pointRadius: 0, fill: false },
      { label: "Expected", data: [...pad, ...f.months.map(x => x.expected)], borderColor: "#9f5bff", borderDash: [6, 5], pointRadius: 0, tension: .3 },
      { label: "Actual revenue", data: [...f.history.map(x => x.actual), ...f.months.map(x => x.actual)], borderColor: "#21d4fd", tension: .3, borderWidth: 2.5,
        pointRadius: c => (f.months[c.dataIndex - pad.length]?.flag ? 6 : 2), pointBackgroundColor: c => (f.months[c.dataIndex - pad.length]?.flag ? "#ff4d6d" : "#21d4fd") },
    ] }, options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, scales: axes(),
      plugins: { legend: { labels: { filter: i => !i.text.startsWith("Band") } } } } });
    const imp = m.feature_importance.slice(0, 10);
    mkChart("cImp", { type: "bar", data: { labels: imp.map(i => i.feature), datasets: [{ data: imp.map(i => i.importance), backgroundColor: imp.map(i => paramOf(i.feature) === "P1 Timing" ? "#0075ff" : "#9f5bff"), borderRadius: 6 }] },
      options: { indexAxis: "y", responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { color: gridC } }, y: { grid: { display: false }, ticks: { font: { size: 10 } } } } } });
  }

  function renderGenAI() {
    const s = S.liveSummary || D.summary;
    $("#page-genai").innerHTML = `
      <div class="grid g-wide">
        <div class="card"><div class="card-head"><div><h3>Engagement summary</h3><div class="sub">Written from the computed facts only · ${esc(s.source || "")}</div></div>
          <button class="btn purple" id="sumBtn" ${S.aiOnline ? "" : "disabled title='Start Ollama first'"}>${ICON.spark} Rewrite with local AI</button></div>
          <p style="line-height:1.65">${esc(s.overview)}</p>
          <div class="grid g3" style="margin:16px 0 0">
            <div class="inner"><div class="bold">Key themes</div><ul class="list small" style="margin-top:6px">${(s.key_themes || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
            <div class="inner"><div class="bold">Next steps</div><ul class="list small" style="margin-top:6px">${(s.recommended_next_steps || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
            <div class="inner"><div class="bold">Limitations</div><ul class="list small" style="margin-top:6px">${(s.limitations || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
          </div></div>
        <div class="card"><h3>Local AI (sovereignty)</h3><div class="sub">The LLM runs on the auditor's laptop with Ollama: client data never leaves it.</div>
          <div style="margin:14px 0" class="pill"><span class="dot ${S.aiOnline ? "on" : "off"}"></span>${S.aiOnline ? "Ollama is running · " + esc((S.aiModels || []).join(", ") || "no model pulled") : "Ollama not detected on this computer"}</div>
          <label class="ctl" style="margin-bottom:12px">Model <input type="text" id="modelIn" value="${esc(S.model)}"></label>
          <label class="ctl" style="margin-bottom:12px">Memo language <select id="langIn"><option>English</option><option>French</option></select></label>
          <div class="note small"><b>To use it from this page</b>: install Ollama, run <code>ollama pull llama3</code>, then start it allowing this site:<pre>OLLAMA_ORIGINS="*" ollama serve</pre>Memos in the table were pre-written by <code>python -m pipeline.run</code> (local LLM, or a template when no LLM was running).</div></div>
      </div>
      <div class="grid g4">
        ${[["Pure generation", "Write audit memos and the engagement summary", "doc"], ["Data enrichment", "Tag the nature of each entry (accrual, reversal…)", "book"],
           ["Analysis", "Turn rules + SHAP values into plain-language reasons", "brain"], ["Recommendation", "Follow-up audit procedures per alert", "target"]]
          .map(([t, d, i]) => `<div class="card kpi"><div><div class="bold">${t}</div><div class="muted small" style="margin-top:4px">${d}</div></div><div class="icon-sq purple">${ICON[i]}</div></div>`).join("")}
      </div>
      <div class="card"><div class="card-head"><div><h3>Prompt library · ${esc(D.prompts.version)}</h3><div class="sub">System prompt = how the AI behaves · user prompt = context + question. The LLM explains, it never scores.</div></div></div>
        ${D.prompts.library.map(p => `<details><summary>${esc(p.name)} <span class="tag ${p.role === "system" ? "purple" : "blue"}">${p.role} · ${esc(p.used_for)}</span></summary><pre>${esc(p.text)}</pre></details>`).join("")}
        <h4 style="margin:16px 0 8px">Change log</h4><ul class="list small">${D.prompts.log.map(l => `<li>${esc(l)}</li>`).join("")}</ul></div>`;
    $("#langIn").value = S.language;
    $("#modelIn").onchange = e => { S.model = e.target.value.trim(); store.set("je-audit-model", S.model); };
    $("#langIn").onchange = e => { S.language = e.target.value; };
    $("#sumBtn").onclick = async e => {
      const b = e.currentTarget; b.disabled = true; b.innerHTML = '<span class="spin"></span> Writing…';
      try {
        const al = alertsAll().filter(isAlert), byRule = {}, byParam = {};
        al.forEach(a => a.rules.forEach(r => { byRule[r] = (byRule[r] || 0) + 1; byParam[paramOf(r)] = (byParam[paramOf(r)] || 0) + 1; }));
        const facts = { ledger: `${D.dataset.datacard.format}, ${D.dataset.datacard.period}`, n_entries: D.kpis.entries, n_manual: D.kpis.manual, cutoff: S.cutoff,
          n_alerts: al.length, by_param: JSON.stringify(byParam), by_rule: JSON.stringify(byRule), n_injected: D.kpis.injected, found: D.kpis.found,
          forecast_flags: (D.forecast.months || []).filter(x => x.flag).map(x => x.month).join(", ") || "none",
          top5: al.slice(0, 5).map(a => `${a.id} ${a.text} ${nf(a.amount)} EUR score ${a.score}`).join("; ") };
        const res = await aiChat(lib("System").replace("{language}", S.language), fill(lib("Engagement"), facts));
        res.source = S.model + " (local, live)"; S.liveSummary = res; renderGenAI(); toast("Summary rewritten by the local AI");
      } catch (err) { toast("Local AI error: " + err.message); b.disabled = false; b.innerHTML = ICON.spark + " Rewrite with local AI"; }
    };
  }

  function renderMethod() {
    $("#page-method").innerHTML = `
      <div class="grid g2">
        <div class="card"><h3>Business objective</h3><div class="sub">Project 2 · Testing 100% of journal entries</div>
          <p style="margin-top:12px;line-height:1.65">Help an external auditor test <b>every</b> journal entry instead of a sample. NEP 240 / ISA 240 require the auditor to test the appropriateness of journal entries and other adjustments made when preparing the financial statements.</p>
          <div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>Mission</th><th>AI</th><th>KPI</th></tr></thead><tbody>
            <tr><td><b>M1 Detect</b> risky entries</td><td>Rules + Isolation Forest</td><td>Recall ${pct(D.metrics.models["Risk score (combined)"].recall)}</td></tr>
            <tr><td><b>M2 Prioritise</b> (predict)</td><td>XGBoost + SHAP</td><td>${(() => { const c = D.metrics.models["Risk score (combined)"], kk = Object.keys(c).find(x => x.startsWith("precision_at_")); return `Precision in the top ${kk.split("_").pop()}: ${pct(c[kk])}`; })()}</td></tr>
            <tr><td><b>M3 Document</b></td><td>Local LLM (Ollama)</td><td>Memo per alert, auditor decision</td></tr>
          </tbody></table></div></div>
        <div class="card"><h3>Two parameters</h3><div class="sub">We kept the scope narrow on purpose</div>
          <div class="inner" style="margin-top:12px"><span class="tag blue">P1 Timing</span><p class="small" style="margin-top:8px;line-height:1.6">Weekend or public-holiday posting, year-end closing window, revenue booked at year end, entered long after the posting date (backdating), entered at night or on a weekend. <span class="muted">Holidays via the Nager.Date API (${esc(D.dataset.holiday_source)}).</span></p></div>
          <div class="inner" style="margin-top:12px"><span class="tag purple">P2 Amount</span><p class="small" style="margin-top:8px;line-height:1.6">Round amounts, just below the approval threshold (€${nf(D.settings.approval_threshold)}), several near-threshold entries by one user on one day (split), above performance materiality (${Object.entries(D.settings.performance_materiality).map(([y, v]) => `${y}: €${nf(v)}`).join(" · ")}), unusual amount for the account.</p></div></div>
      </div>
      <div class="grid g2">
        <div class="card"><h3>Pipeline</h3><div class="sub">The professor's analysis steps</div>
          <ol class="list" style="margin-top:10px"><li>Collect: DIB general ledger + Nager.Date API</li><li>Datacard and consistency checks</li><li>EDA: Benford, weekday, hour, monthly</li><li>Inject labelled anomalies (the data is clean)</li><li>Features P1 + P2 per entry</li><li>Split: train ${D.metrics.split.match(/\d{4}/)?.[0] || ""}, test later year + held-out types</li><li>Rules → Isolation Forest → XGBoost → combined score</li><li>Evaluate: precision, recall, PR-AUC, circularity</li><li>Gen AI: nature, memos, summary (local)</li><li>Decide: the auditor reviews every alert</li></ol>
          <div class="note small" style="margin-top:12px">Refresh the data: <pre>pip install -r requirements.txt
python -m pipeline.run --country FR --inject 42 --llm-top 40</pre></div></div>
        <div class="card"><h3>Limits & governance</h3><div class="sub">What the reader must know</div>
          <ul class="list" style="margin-top:10px"><li>Demo anomalies are injected: real fraud can look different.</li><li>Thresholds and materiality are our assumptions (adjustable).</li><li>The LLM can sound right and be wrong: it only receives computed facts, uses JSON output and temperature 0.2, and every memo must be reviewed.</li><li>Human accountability: the AI flags and explains; the auditor decides and signs.</li><li>Confidential client data stays local (Ollama); this website only shows the results.</li><li>Decisions made on this page are saved in this browser only. Export them to Excel for the working papers.</li></ul>
          <div class="note small" style="margin-top:12px">Data: ${esc(D.dataset.authors)}, <i>${esc(D.dataset.name)}</i>, Zenodo, DOI ${esc(D.dataset.doi)}, ${esc(D.dataset.license)}.</div></div>
      </div>`;
  }

  // ---------------------------------------------------------------- drawer (entry detail + memo + decision)
  function openEntry(id) {
    const a = D.alerts.find(x => x.id === id); if (!a) return;
    const m = memoOf(a), d = S.decisions[id] || {};
    const maxShap = Math.max(...a.shap.map(s => s.shap), 0.01);
    $("#drawer").innerHTML = `
      <button class="close" id="dClose">×</button>
      <div class="muted small">${esc(a.id)} · ${esc(a.source)} entry · ${esc(a.nature)}</div>
      <h2>${esc(a.text)}</h2>
      <div class="chips" style="margin-top:10px"><span class="tag ${a.score >= 75 ? "red" : a.score >= 50 ? "orange" : "blue"}">Risk ${nf(a.score)}/100</span>${decTag(d.decision)}${a.injected ? `<span class="tag orange">Demo anomaly: ${esc(TYPE_LABEL[a.injected] || a.injected)}</span>` : ""}</div>
      <div class="sect kv">
        <div class="mini"><div class="muted tiny">Amount</div><div class="v">${eur(a.amount)}</div></div>
        <div class="mini"><div class="muted tiny">Posted</div><div class="v">${dmy(a.posting_date)}</div></div>
        <div class="mini"><div class="muted tiny">Entered</div><div class="v">${dmy(a.entered_at)} ${a.entered_at.slice(11)}</div></div>
        <div class="mini"><div class="muted tiny">Delay</div><div class="v">${a.delay} days</div></div>
        <div class="mini"><div class="muted tiny">User</div><div class="v">${esc(a.user)}</div></div>
        <div class="mini"><div class="muted tiny">Model scores</div><div class="v small">Rules ${nf(a.rules_score)} · XGB ${pct(a.xgb)} · Outlier ${pct(a.iforest)}</div></div>
      </div>
      <div class="sect"><h4>Entry lines</h4><table><thead><tr><th>Account</th><th>Name</th><th style="text-align:right">Debit</th><th style="text-align:right">Credit</th></tr></thead><tbody>
        ${a.lines.map(l => `<tr><td>${esc(l.account)}</td><td>${esc(l.name)}</td><td style="text-align:right">${l.debit ? eur(l.debit) : ""}</td><td style="text-align:right">${l.credit ? eur(l.credit) : ""}</td></tr>`).join("")}</tbody></table></div>
      <div class="sect"><h4>Red flags (rules)</h4><div class="chips">${a.rules.map(ruleTag).join("") || '<span class="muted small">No rule triggered: flagged by the ML layers</span>'}</div></div>
      <div class="sect"><h4>Why the model flagged it (SHAP)</h4>${a.shap.map(s => `<div class="shap-row"><span>${esc(s.feature)}</span><span class="track"><i style="width:${s.shap / maxShap * 100}%"></i></span><span class="muted">+${s.shap}</span></div>`).join("") || '<span class="muted small">No positive SHAP driver</span>'}</div>
      <div class="sect memo"><div class="card-head"><h4 style="margin:0">Audit memo</h4><button class="btn purple" id="memoBtn" ${S.aiOnline ? "" : "disabled title='Start Ollama to rewrite'"}>${ICON.spark} Rewrite with local AI</button></div>
        <div class="inner">
          <div class="chips"><span class="tag ${m.risk_level === "High" ? "red" : m.risk_level === "Medium" ? "orange" : "green"}">${esc(m.risk_level)} risk</span><span class="tag blue">Assertion: ${esc(m.assertion_at_risk)}</span></div>
          <p style="margin-top:10px">${esc(m.why_suspicious)}</p>
          <div class="bold small" style="margin-top:12px">Follow-up procedures</div><ul class="small">${(m.follow_up_procedures || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
          <div class="bold small" style="margin-top:12px">Possible legitimate explanations</div><ul class="small">${(m.possible_explanations || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
          <p class="small" style="margin-top:12px"><b>Conclusion:</b> ${esc(m.conclusion)}</p>
          <div class="muted tiny" style="margin-top:10px">Generated by ${esc(m.source)}. Must be reviewed by the auditor.</div></div></div>
      <div class="sect"><h4>Auditor decision</h4>
        <div class="seg" id="seg"><button data-v="retained" class="r">Retained</button><button data-v="investigate" class="i">To investigate</button><button data-v="dismissed" class="d">Dismissed</button></div>
        <textarea id="dCom" placeholder="Comment for the working papers…" style="margin-top:10px">${esc(d.comment || "")}</textarea>
        <div style="display:flex;gap:8px;margin-top:10px"><button class="btn" id="dSave">${ICON.check} Save decision</button>${d.decision ? '<button class="btn ghost" id="dClear">Clear</button>' : ""}</div></div>`;
    let choice = d.decision || "";
    const paint = () => document.querySelectorAll("#seg button").forEach(b => b.classList.toggle("on", b.dataset.v === choice));
    paint();
    document.querySelectorAll("#seg button").forEach(b => (b.onclick = () => { choice = b.dataset.v; paint(); }));
    $("#dSave").onclick = () => {
      if (!choice) return toast("Choose a decision first");
      S.decisions[id] = { decision: choice, comment: $("#dCom").value, ts: new Date().toISOString() };
      store.set("je-audit-decisions", S.decisions); toast("Decision saved in this browser"); closeEntry(); route();
    };
    if ($("#dClear")) $("#dClear").onclick = () => { delete S.decisions[id]; store.set("je-audit-decisions", S.decisions); closeEntry(); route(); };
    $("#memoBtn").onclick = async e => {
      const b = e.currentTarget; b.disabled = true; b.innerHTML = '<span class="spin"></span> Writing…';
      try {
        const res = await aiChat(lib("System").replace("{language}", S.language), fill(lib("Audit memo"), memoFacts(a)));
        res.source = `${S.model} (local, live) · prompts ${D.prompts.version}`;
        S.memos[id] = res; store.set("je-audit-memos", S.memos); toast("Memo rewritten by the local AI"); openEntry(id);
      } catch (err) { toast("Local AI error: " + err.message); b.disabled = false; b.innerHTML = ICON.spark + " Rewrite with local AI"; }
    };
    $("#dClose").onclick = closeEntry;
    $("#overlay").classList.add("open"); $("#drawer").classList.add("open"); $("#drawer").scrollTop = 0;
  }
  function closeEntry() { $("#overlay").classList.remove("open"); $("#drawer").classList.remove("open"); }
  $("#overlay").onclick = closeEntry;
  document.addEventListener("keydown", e => e.key === "Escape" && closeEntry());
  document.addEventListener("click", e => { const tr = e.target.closest("tr.click"); if (tr) openEntry(tr.dataset.id); });

  // ---------------------------------------------------------------- export (working papers)
  function exportFile(kind) {
    const rows = filtered().map(a => {
      const m = memoOf(a), d = S.decisions[a.id] || {};
      return { entry_id: a.id, risk_score: a.score, alert: isAlert(a) ? "yes" : "no", posting_date: a.posting_date, entered_at: a.entered_at, user: a.user,
        source: a.source, nature: a.nature, text: a.text, accounts: a.accounts, amount: a.amount, red_flags: a.rules.join("; "),
        shap_drivers: a.shap.map(s => `${s.feature} (+${s.shap})`).join("; "), risk_level: m.risk_level, why_suspicious: m.why_suspicious,
        assertion: m.assertion_at_risk, follow_up: (m.follow_up_procedures || []).join(" | "), conclusion: m.conclusion, memo_source: m.source,
        demo_anomaly: a.injected || "", auditor_decision: d.decision || "", auditor_comment: d.comment || "", decided_at: d.ts || "" };
    });
    const name = `JE_audit_alerts_${new Date().toISOString().slice(0, 10)}`;
    if (kind === "xlsx" && window.XLSX) {
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(rows), "Alerts");
      const mm = Object.entries(D.metrics.models).map(([k, v]) => ({ layer: k, ...v }));
      XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(mm), "Model metrics");
      XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(D.metrics.by_type), "Recall by type");
      XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(Object.entries(D.dataset.datacard).map(([k, v]) => ({ item: k, value: v }))), "Datacard");
      XLSX.writeFile(wb, name + ".xlsx");
    } else {
      const head = Object.keys(rows[0] || { entry_id: "" });
      const csv = [head.join(","), ...rows.map(r => head.map(h => `"${String(r[h] ?? "").replace(/"/g, '""')}"`).join(","))].join("\n");
      const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv" }));
      const l = document.createElement("a"); l.href = url; l.download = name + ".csv"; l.click(); URL.revokeObjectURL(url);
    }
    toast(`Exported ${rows.length} entries`);
  }

  // ---------------------------------------------------------------- router
  const RENDER = { dashboard: renderDashboard, alerts: renderAlerts, analytics: renderAnalytics, models: renderModels, genai: renderGenAI, method: renderMethod };
  function route() {
    const id = (location.hash || "#dashboard").slice(1).split("?")[0];
    const page = RENDER[id] ? id : "dashboard";
    document.querySelectorAll(".page").forEach(p => p.classList.toggle("active", p.id === "page-" + page));
    document.querySelectorAll("[data-nav]").forEach(n => n.classList.toggle("active", n.dataset.nav === page));
    const label = PAGES.find(p => p[0] === page)[1];
    $("#crumb").textContent = label; $("#title").textContent = label; document.title = `${label} · JE Audit`;
    RENDER[page]();
    window.scrollTo({ top: 0 });
  }
  $("#nav").innerHTML = PAGES.map((p, i) => (i === 4 ? '<div class="nav-title">AI & METHOD</div>' : "") +
    `<a class="nav-item" data-nav="${p[0]}" href="#${p[0]}"><span class="ico">${ICON[p[2]]}</span>${p[1]}</a>`).join("");
  $("#mnav").innerHTML = PAGES.map(p => `<a data-nav="${p[0]}" href="#${p[0]}">${p[1]}</a>`).join("");
  $("#globalSearch").addEventListener("keydown", e => { if (e.key === "Enter") { S.q = e.target.value; S.shown = 50; location.hash === "#alerts" ? renderAlerts() : (location.hash = "alerts"); } });
  window.addEventListener("hashchange", () => { closeEntry(); route(); });

  // ---------------------------------------------------------------- start
  fetch("data/dashboard.json", { cache: "no-cache" }).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(data => {
    D = data;
    S.cutoff = store.get("je-audit-cutoff", D.settings.alert_cutoff);
    $("#foot").innerHTML = `Data generated ${esc(D.generated_at)} · ${esc(D.dataset.name)} (${esc(D.dataset.license)}) · holidays ${esc(D.dataset.holiday_country)} · memos: ${D.settings.llm_used ? esc(D.settings.llm_model) + " (local)" : "template (no local LLM during the run)"}`;
    route();
    checkAI().then(() => { if (["genai"].includes(location.hash.slice(1))) renderGenAI(); });
  }).catch(err => {
    $("#page-dashboard").classList.add("active");
    $("#page-dashboard").innerHTML = `<div class="card"><h3>No data yet</h3><p class="muted" style="margin-top:8px">Could not load <code>data/dashboard.json</code> (${esc(err.message)}). Run <code>python -m pipeline.run</code> first, then serve the <code>web</code> folder (<code>python -m http.server -d web</code>).</p></div>`;
  });
})();
