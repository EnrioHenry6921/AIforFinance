/* JE Audit dashboard - reads data/dashboard.json produced by `python -m pipeline.run`.
   Design language adapted from the CapturePoint dashboard: neutral greys carry the data,
   one accent marks the thing each card is about. */
(() => {
  "use strict";

  // ---------------------------------------------------------------- icons (outline, 1.8 stroke)
  const I = d => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
  const ICON = {
    home: I('<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20h14V9.5"/><path d="M10 20v-6h4v6"/>'),
    alert: I('<path d="M12 3 2.5 20h19z"/><path d="M12 10v4.5M12 17.5h.01"/>'),
    chart: I('<path d="M4 20V11M10 20V5M16 20v-8M3 20h18"/>'),
    brain: I('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>'),
    spark: I('<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>'),
    book: I('<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 0 5.5 21H20"/>'),
    check: I('<path d="M5 12.5l4.5 4.5L19 7"/>'),
    search: I('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
    doc: I('<path d="M6 2.5h8.5L19 7v14.5H6z"/><path d="M14 2.5V7h5M9 12h6M9 16h6"/>'),
    wallet: I('<rect x="3" y="6" width="18" height="13" rx="3"/><path d="M16 12.5h2M3 10h18"/>'),
    target: I('<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r=".8"/>'),
    clock: I('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>'),
    coins: I('<ellipse cx="9" cy="7" rx="5.5" ry="2.5"/><path d="M3.5 7v4c0 1.4 2.5 2.5 5.5 2.5s5.5-1.1 5.5-2.5V7"/><path d="M9.5 16.5c.9 1 2.9 1.5 5 1.5 3 0 5.5-1.1 5.5-2.5v-4c0-1.2-1.7-2.1-4-2.4"/>'),
    moon: I('<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>'),
    sun: I('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'),
    user: I('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
    download: I('<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 20h14"/>'),
    shield: I('<path d="M12 3l7.5 3v6c0 4.6-3.2 7.8-7.5 9-4.3-1.2-7.5-4.4-7.5-9V6z"/><path d="M9 12l2 2 4-4"/>'),
    chev: I('<path d="M9 6l6 6-6 6"/>'),
    calendar: I('<rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 10h17M8 3v4M16 3v4"/>'),
    menu: I('<path d="M4 7h16M4 12h16M4 17h16"/>'),
    x: I('<path d="M6 6l12 12M18 6 6 18"/>'),
    layers: I('<path d="M12 3 2.5 8 12 13l9.5-5z"/><path d="M2.5 12.5 12 17.5l9.5-5M2.5 16.5 12 21.5l9.5-5"/>'),
  };
  const icons = root => root.querySelectorAll("[data-icon]").forEach(el => { el.innerHTML = ICON[el.dataset.icon] || ""; el.removeAttribute("data-icon"); });
  icons(document);

  const PAGES = [
    ["dashboard", "Overview", "home"], ["alerts", "Alerts & memos", "alert"],
    ["analytics", "Data & EDA", "chart"], ["models", "Models & prediction", "layers"],
    ["genai", "Gen AI & prompts", "spark"], ["method", "Method", "book"],
  ];
  const paramOf = r => (D && D.flag_params && D.flag_params[r]) || "Context";
  const PCOL = { "P1 Timing": "var(--accent)", "P2 Amount": "var(--p2)", Context: "var(--c2)" };
  const TYPE_LABEL = {
    weekend_posting: "Weekend posting", holiday_posting: "Holiday posting", year_end_revenue: "Year-end revenue",
    night_entry: "Night entry", late_entry: "Late entry (backdating)", round_amount: "Round amount",
    split_below_threshold: "Split below threshold", duplicate_manual: "Duplicate manual entry",
  };
  const typeName = t => TYPE_LABEL[t] || String(t).replace(/^M(\d) /, "M$1 · ");
  const labelWord = () => (D.settings.label_source === "dataset" ? "labelled" : "demo");

  // ---------------------------------------------------------------- helpers
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const nf = (n, d = 0) => Number(n).toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });
  const eur = (n, d = 2) => "€" + nf(n, d);
  const eurShort = n => (n >= 1e6 ? "€" + nf(n / 1e6, 1) + "m" : n >= 1e3 ? "€" + nf(n / 1e3, 0) + "k" : eur(n, 0));
  const pct = (x, d = 0) => (x === null || x === undefined ? "n/a" : nf(x * 100, d) + "%");
  const dmy = s => (s ? s.slice(8, 10) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4) : "");
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const monLabel = m => MON[+m.slice(5, 7) - 1] + " " + m.slice(2, 4);
  const toast = msg => { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 2600); };
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
  };
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const T = () => ({ acc: css("--accent"), p2: css("--p2"), c1: css("--c1"), c2: css("--c2"), c3: css("--c3"), c4: css("--c4"),
    muted: css("--muted"), line: css("--line"), surface: css("--surface"), ink: css("--ink"), bad: css("--bad"), good: css("--good"), warn: css("--warn") });
  const alpha = (hex, a) => { const h = hex.replace("#", ""); const n = parseInt(h.length === 3 ? h.replace(/./g, "$&$&") : h, 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; };

  let D = null;
  const S = {
    cutoff: 50, minScore: 0, q: "", param: "all", status: "all", source: "all", shown: 50, tab: "entries",
    decisions: store.get("je-audit-decisions", {}), memos: store.get("je-audit-memos", {}),
    aiOnline: false, lazyMemos: {}, memoIndex: null, aiModels: [], model: store.get("je-audit-model", "llama3:latest"), language: "English",
  };
  const charts = {};
  const mkChart = (id, cfg) => { if (charts[id]) charts[id].destroy(); const el = document.getElementById(id); if (el) charts[id] = new Chart(el, cfg); };

  function chartTheme() {
    const t = T();
    Chart.defaults.color = t.muted;
    Chart.defaults.font.family = css("--font");
    Chart.defaults.font.size = 12;
    Chart.defaults.borderColor = t.line;
    Chart.defaults.plugins.legend.display = false;
    Object.assign(Chart.defaults.plugins.tooltip, { backgroundColor: t.surface, titleColor: t.ink, bodyColor: t.ink, borderColor: t.line, borderWidth: 1, padding: 10, cornerRadius: 12, boxPadding: 4, usePointStyle: true });
    Chart.defaults.animation.duration = 700;
    return t;
  }
  const axes = (t, extra = {}) => ({
    x: { grid: { display: false }, border: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 }, ...extra.x },
    y: { grid: { color: t.line, drawTicks: false }, border: { display: false, dash: [3, 4] }, ticks: { padding: 8, maxTicksLimit: 5 }, ...extra.y },
  });
  const wash = (ctx, color) => { const h = ctx.chart.chartArea?.bottom || 300; const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, h); g.addColorStop(0, alpha(color, .22)); g.addColorStop(1, alpha(color, 0)); return g; };

  // ---------------------------------------------------------------- data access
  const decisionOf = id => S.decisions[id]?.decision || "";
  const isAlert = a => a.score >= S.cutoff;
  const alertsNow = () => D.alerts.filter(isAlert);
  function filtered() {
    const q = S.q.toLowerCase();
    return D.alerts.filter(a => {
      if (a.score < S.minScore) return false;
      if (S.source !== "all" && a.source !== S.source) return false;
      if (S.param !== "all" && !a.rules.some(r => paramOf(r) === S.param)) return false;
      const dec = decisionOf(a.id);
      if (S.status === "open" && dec) return false;
      if (!["all", "open"].includes(S.status) && dec !== S.status) return false;
      if (q && !`${a.id} ${a.user} ${a.text} ${a.accounts} ${a.rules.join(" ")} ${a.nature}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }
  const memoOf = a => S.memos[a.id] || a.memo || S.lazyMemos[a.id] || null;
  // recommendations: stored for the top alerts, rebuilt from the same flag -> library mapping for compact rows
  const recsOf = a => {
    if (a.recommendations) return a.recommendations;
    const lib = Object.fromEntries((D.recommendation_library || []).map(r => [String(r.marking_code), r]));
    const out = [], seen = new Set();
    [...a.rules, ...a.shap.map(x => x.feature)].forEach(f => {
      const c = (D.flag_codes || {})[f];
      if (c && !seen.has(c) && lib[c]) { seen.add(c); out.push({ code: c, signal: f, ...lib[c] }); }
    });
    return out.length ? out : [{ ...(D.generic_recommendation || {}), signal: "model score" }];
  };
  // memos of the compact alerts live in data/memos/*.json, fetched only when needed
  async function loadMemos(ids) {
    const need = ids.filter(id => !S.lazyMemos[id] && D.alerts.find(a => a.id === id)?.lazy);
    if (!need.length) return;
    if (!S.memoIndex) S.memoIndex = await fetch("data/memos/index.json").then(r => r.json());
    const files = [...new Set(need.map(id => S.memoIndex[id]).filter(Boolean))];
    await Promise.all(files.map(f => fetch("data/memos/" + f).then(r => r.json()).then(o => Object.assign(S.lazyMemos, o))));
  }

  // ---------------------------------------------------------------- local AI (Ollama on the auditor's computer)
  const OLLAMA = "http://localhost:11434";
  async function checkAI() {
    try {
      const c = new AbortController(); setTimeout(() => c.abort(), 2500);
      const r = await fetch(OLLAMA + "/api/tags", { signal: c.signal });
      const j = await r.json();
      S.aiOnline = true; S.aiModels = (j.models || []).map(m => m.name);
    } catch { S.aiOnline = false; S.aiModels = []; }
    for (const [d, t] of [["#aiDot", "#aiText"], ["#aiDot2", "#aiText2"]]) {
      $(d).className = "dot " + (S.aiOnline ? "on" : "off");
      $(t).textContent = S.aiOnline ? "Local AI online" : "Local AI offline";
    }
  }
  async function aiChat(system, user) {
    const r = await fetch(OLLAMA + "/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: S.model, stream: false, format: "json", options: { temperature: 0.2 },
        messages: [{ role: "system", content: system }, { role: "user", content: user }] }),
    });
    if (!r.ok) throw new Error("Ollama answered " + r.status);
    return JSON.parse((await r.json()).message.content);
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
    const pmAll = D.settings.performance_materiality;
    const pm = pmAll[a.posting_date.slice(0, 4)] ?? Object.values(pmAll)[0];
    return {
      entry_id: a.id, source: a.source, nature: a.nature, posting_date: dmy(a.posting_date),
      weekday: new Date(a.posting_date).toLocaleDateString("en-GB", { weekday: "long" }), entered_at: dmy(a.entered_at) + " " + a.entered_at.slice(11),
      delay: a.delay, hour: a.entered_at.slice(11, 13), text: a.text, accounts: a.accounts, main_account: code,
      main_account_name: nm.join(" "), amount: a.amount, user: a.user, risk_score: a.score,
      rules: a.rules.join(", ") || "none", shap: a.shap.map(s => `${s.feature} (+${s.shap})`).join("; ") || "none",
      threshold: D.settings.approval_threshold, perf_mat: pm, risk_level: a.level,
      hour_text: D.settings.has_entry_time ? `, at ${a.entered_at.slice(11, 13)}:00` : "",
      p2: a.p2 === null || a.p2 === undefined ? "not applicable" : `${a.p2}/100`,
      library: recsOf(a).map(r => `- [${r.code}] ${r.anomaly} (signal: ${r.signal}): risk: ${r.potential_risk} | evidence: ${r.evidence_to_request} | procedure: ${r.audit_procedure}`).join("\n"),
    };
  }

  // ---------------------------------------------------------------- UI pieces
  const stat = (title, val, foot, icon, tile = false, i = 0) => `
    <div class="card stat${tile ? " tile" : ""}" style="--i:${i}"><div class="top-row"><span class="card-t">${title}</span><span class="ico">${ICON[icon]}</span></div>
    ${val === "" ? "" : `<div class="val">${val}</div>`}<div class="foot2">${foot}</div></div>`;
  const scoreColor = s => (s >= 75 ? "var(--bad)" : s >= 50 ? "var(--warn)" : "var(--c3)");
  const scoreCell = s => `<div class="score-cell"><span class="n" style="color:${s >= 50 ? scoreColor(s) : "var(--ink-2)"}">${nf(s, 0)}</span><span class="muted tiny"> /100</span><div class="bar"><i style="width:${s}%;background:${scoreColor(s)}"></i></div></div>`;
  const ruleTag = r => `<span class="tag ${{ "P1 Timing": "blue", "P2 Amount": "purple" }[paramOf(r)] || "gray"}">${esc(r)}</span>`;
  const decTag = d => d === "retained" ? '<span class="badge bad">Retained</span>' : d === "dismissed" ? '<span class="badge">Dismissed</span>'
    : d === "investigate" ? '<span class="badge warn">To investigate</span>' : '<span class="badge acc">Open</span>';
  const markFor = a => { const p = a.rules.length ? paramOf(a.rules[0]) : "Context"; return `<span class="mark ${p === "P1 Timing" ? "acc" : p === "P2 Amount" ? "p2" : ""}">${ICON[p === "P1 Timing" ? "clock" : p === "P2 Amount" ? "coins" : "layers"]}</span>`; };
  const totalAlerts = () => (S.cutoff === D.settings.alert_cutoff ? D.kpis.alerts : alertsNow().length);
  const head = (title, sub, actions = "") => { $("#title").textContent = title; $("#subtitle").innerHTML = sub; $("#headActions").innerHTML = actions; icons($("#headActions")); };

  // ---------------------------------------------------------------- Overview
  function renderDashboard() {
    const k = D.kpis, m = D.metrics, comb = m.models["Risk score (combined)"] || {}, demo = k.labelled > 0;
    const alerts = alertsNow(), open = alerts.filter(a => !decisionOf(a.id));
    head("Overview", `${esc(D.dataset.datacard.period)} · <b style="color:var(--ink)">${nf(totalAlerts())}</b> alerts at cut-off ${S.cutoff}`,
      `<a class="link" href="#alerts"><span data-icon="alert"></span>Start triage</a>`);
    const types = m.by_type || [];
    const heldN = types.filter(t => t.held_out).reduce((s, t) => s + t.n, 0);
    const heldXgb = heldN ? types.filter(t => t.held_out).reduce((s, t) => s + t.xgboost * t.n, 0) / heldN : 0;
    const tabVal = { entries: [nf(k.entries), "entries scored, 100% of the ledger"], alerts: [nf(k.alerts), `alerts at cut-off ${D.settings.alert_cutoff}`], amount: [eurShort(k.amount_tested), "posted in the period"] }[S.tab];
    const hours = D.charts.hours, night = D.charts.flags_all["Entered outside working hours"] || 0;
    const wh = D.settings.working_hours;

    $("#page-dashboard").innerHTML = `
      <div class="grid g-wide">
        <div class="card" style="--i:0">
          <div class="card-head"><div><div class="card-t">Needs review</div><div class="card-v">${nf(open.length)}</div><div class="card-s">Highest-risk alerts still open. Open one to read the memo and record your decision.</div></div>
            <span class="badge ${open.length ? "warn" : "good"}">${open.length ? nf(alerts.length - open.length) + " reviewed" : "All reviewed"}</span></div>
          <div class="list-r">${open.slice(0, 6).map(a => `
            <button class="li" data-id="${esc(a.id)}">${markFor(a)}
              <div><div class="lt">${esc(a.text)}</div><div class="ls">${esc(a.id)} · ${esc(a.user)} · ${esc(a.rules[0] || "flagged by the models")}${a.rules.length > 1 ? ` +${a.rules.length - 1}` : ""}</div></div>
              <div class="lr">${eur(a.amount, 0)}${ICON.chev}</div></button>`).join("") || '<div class="empty">Nothing left to review at this cut-off.</div>'}
          </div>
          ${open.length > 6 ? `<div class="more"><a class="link" href="#alerts">${nf(open.length - 6)} more ${ICON.chev}</a></div>` : ""}
        </div>
        <div class="card" style="--i:1">
          <div class="card-t">Detection rate</div>
          <div class="big-n" style="margin-top:6px">${demo && comb.recall != null ? pct(comb.recall) : "n/a"}</div>
          <div class="card-s">${demo ? `on the unseen test period · ${nf(k.found)} of ${nf(k.labelled)} ${labelWord()} anomalies alerted overall` : "No labelled anomalies in this run"}</div>
          <div class="hb" style="margin-top:20px">${types.map(t => `
            <div class="r"><span>${esc(typeName(t.type))}${t.held_out ? ' <span class="badge acc" style="height:20px;font-size:11px;margin-left:4px">unseen by ML</span>' : ""}</span><b>${pct(t.combined)}<small>${t.n}</small></b>
              <div class="t"><i class="${t.held_out ? "acc" : ""}" style="width:${t.combined * 100}%"></i></div></div>`).join("")}
          </div>
          ${demo && heldN ? `<div class="note" style="margin-top:18px">XGBoost alone catches <b>${pct(heldXgb)}</b> of the types it never saw: it only finds what it was taught.${m.recall_seen_types ? ` On the types it was taught, the combined score catches <b>${pct(m.recall_seen_types["Risk score (combined)"])}</b>.` : ""}</div>` : ""}
        </div>
      </div>

      <div class="grid g4">
        ${stat("Entries tested", nf(k.entries), `100% of the ledger · ${nf(k.manual)} manual`, "doc", true, 2)}
        ${stat("Alerts to review", nf(totalAlerts()), `<span class="badge warn">${pct(totalAlerts() / k.entries, 2)}</span> of all entries · ${nf(k.high)} high`, "alert", false, 3)}
        ${stat(demo ? "Unlabelled entries flagged" : "Entries flagged", nf(S.cutoff === D.settings.alert_cutoff ? k.real_alerts : alerts.filter(a => !a.injected).length), demo ? "not in the labels, worth a look" : "worth a look", "target", false, 4)}
        ${stat("Amount tested", eurShort(k.amount_tested), `${D.charts.monthly.length} months · ${D.dataset.datacard.users} users`, "wallet", false, 5)}
      </div>

      <div class="grid g-wide">
        <div class="card" style="--i:6">
          <div class="card-head"><div><div class="card-t">Activity · ${esc(D.dataset.datacard.period)}</div><div class="card-v">${tabVal[0]}</div><div class="card-s">${tabVal[1]}</div></div>
            <div class="segbar" id="tabs">${[["entries", "Entries"], ["alerts", "Alerts"], ["amount", "Amount"]].map(([v, l]) => `<button data-v="${v}" class="${S.tab === v ? "on" : ""}">${l}</button>`).join("")}</div></div>
          <div class="chart-box lg"><canvas id="cMonthly"></canvas></div>
        </div>
        <div class="card" style="--i:7">
          <div class="card-t">Alerts by parameter</div><div class="card-s">Which red flags drive the alerts</div>
          <div class="donut-wrap" style="margin-top:18px"><div class="donut-c"><canvas id="cParam"></canvas><div class="ctr"><div><b>${nf(alerts.length)}</b><small>alerts</small></div></div></div><div class="dleg" id="paramLegend"></div></div>
          <div class="lbl2" style="margin-top:22px">Top red flags</div>
          <div class="hb">${topRules(alerts).slice(0, 4).map(([r, n], i) => `<div class="r"><span>${esc(r)}</span><b>${n}</b><div class="t"><i class="${i === 0 ? "acc" : ""}" style="width:${n / Math.max(1, alerts.length) * 100}%"></i></div></div>`).join("")}</div>
        </div>
      </div>

      <div class="grid g-wide even">
        <div class="card" style="--i:8">
          <div class="card-head"><div><div class="card-t">Entry times</div><div class="card-v">${nf(night)}</div><div class="card-s">${wh ? `entered outside the ledger's working day (${String(wh[0]).padStart(2, "0")}:00–${String(wh[1]).padStart(2, "0")}:59)` : "no entry time in this file"} · log scale</div></div>
            <div class="legend" style="margin:0"><span><i style="background:var(--c3)"></i>Working hours</span><span><i style="background:var(--accent)"></i>Outside</span></div></div>
          <div class="chart-box"><canvas id="cHours"></canvas></div>
        </div>
        <div class="card" style="--i:9">
          <div class="card-head"><div><div class="card-t">Latest activity</div><div class="card-s">${Object.keys(S.decisions).length ? "Your most recent decisions" : "Highest-risk entries, by posting date"}</div></div><a class="link" href="#alerts">All alerts</a></div>
          <div class="list-r">${activity()}</div>
        </div>
      </div>`;
    icons($("#page-dashboard"));
    $("#tabs").onclick = e => { const b = e.target.closest("button"); if (b) { S.tab = b.dataset.v; renderDashboard(); } };

    const t = chartTheme(), mo = D.charts.monthly;
    const series = { entries: mo.map(x => x.system + x.manual), alerts: mo.map(x => x.alerts), amount: mo.map(x => x.amount) }[S.tab];
    mkChart("cMonthly", { type: "line",
      data: { labels: mo.map(x => monLabel(x.month)), datasets: [{ data: series, borderColor: t.acc, borderWidth: 2.5, tension: .4, fill: true, backgroundColor: c => wash(c, t.acc),
        pointRadius: 3.5, pointBackgroundColor: t.surface, pointBorderColor: t.acc, pointBorderWidth: 2, pointHoverRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        plugins: { tooltip: { callbacks: { label: c => " " + (S.tab === "amount" ? eur(c.raw, 0) : nf(c.raw)) } } },
        scales: axes(t, { y: { ticks: { maxTicksLimit: 5, callback: v => (S.tab === "amount" ? eurShort(v) : nf(v)) } } }) } });
    const byParam = {}; alerts.forEach(a => new Set(a.rules.length ? a.rules.map(paramOf) : ["ML only"]).forEach(p => (byParam[p] = (byParam[p] || 0) + 1)));
    const order = ["P1 Timing", "P2 Amount", "Context", "ML only"].filter(p => byParam[p]);
    const cols = { "P1 Timing": t.acc, "P2 Amount": t.p2, Context: t.c2, "ML only": t.c3 };
    mkChart("cParam", { type: "doughnut", data: { labels: order, datasets: [{ data: order.map(p => byParam[p]), backgroundColor: order.map(p => cols[p]), borderWidth: 0, spacing: 3, borderRadius: 6 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "74%" } });
    $("#paramLegend").innerHTML = order.map(p => `<div><i style="background:${cols[p]}"></i><span>${p}</span><b>${byParam[p]}</b></div>`).join("") + `<div class="tiny muted" style="display:block">An alert can carry several.</div>`;
    const outside = h => (wh ? h < wh[0] || h > wh[1] : false);
    mkChart("cHours", { type: "bar", data: { labels: hours.map(h => String(h.hour).padStart(2, "0")), datasets: [{ data: hours.map(h => h.n),
      backgroundColor: hours.map(h => (outside(h.hour) ? t.acc : t.c3)), borderRadius: 6, borderSkipped: false, maxBarThickness: 18 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { tooltip: { callbacks: { title: c => c[0].label + ":00", label: c => " " + nf(c.raw) + " entries" } } },
        scales: axes(t, { x: { ticks: { maxTicksLimit: 12 } }, y: { type: "logarithmic", ticks: { callback: v => ([1, 10, 100, 1000, 10000].includes(v) ? nf(v) : "") } } }) } });
  }
  function topRules(alerts) { const c = {}; alerts.forEach(a => a.rules.forEach(r => (c[r] = (c[r] || 0) + 1))); return Object.entries(c).sort((a, b) => b[1] - a[1]); }
  function activity() {
    const dec = Object.entries(S.decisions).sort((a, b) => (b[1].ts || "").localeCompare(a[1].ts || "")).slice(0, 5);
    const rows = dec.length
      ? dec.map(([id, d]) => { const a = D.alerts.find(x => x.id === id) || { text: id }; const dt = new Date(d.ts);
          return { day: dt.getDate(), mon: MON[dt.getMonth()], t: a.text, s: `${id} · marked ${d.decision === "investigate" ? "to investigate" : d.decision}`, r: decTag(d.decision), id, soon: true }; })
      : [...alertsNow()].sort((a, b) => b.posting_date.localeCompare(a.posting_date)).slice(0, 5)
          .map(a => ({ day: +a.posting_date.slice(8, 10), mon: MON[+a.posting_date.slice(5, 7) - 1], t: a.text, s: `${a.id} · ${a.user} · score ${nf(a.score)}`, r: eur(a.amount, 0), id: a.id, soon: a.score >= 75 }));
    return rows.map(x => `<button class="li" data-id="${esc(x.id)}"><span class="date${x.soon ? " soon" : ""}"><small>${x.mon}</small><b>${x.day}</b></span>
      <div><div class="lt">${esc(x.t)}</div><div class="ls">${esc(x.s)}</div></div><div class="lr">${x.r}</div></button>`).join("");
  }

  // ---------------------------------------------------------------- Alerts
  function renderAlerts() {
    const rows = filtered();
    const wr = D.web_rows || { min_score: 0 };
    head("Alerts & memos", `${nf(D.alerts.length)} entries scoring ${wr.min_score}+ (of ${nf(D.kpis.entries)} scored) · ${nf(D.kpis.alerts)} alerts at the pipeline's cut-off ${D.settings.alert_cutoff} · every entry is in <code>data/output/entries_scored.csv</code>`,
      `<div style="display:flex;gap:8px;flex-wrap:wrap"><button class="link" id="expCsv"><span data-icon="download"></span>CSV</button><button class="btn acc" id="expXlsx"><span data-icon="download"></span>Excel</button></div>`);
    $("#page-alerts").innerHTML = `
      <div class="card flush">
        <div class="card-head"><div><div class="card-t">${nf(rows.length)} entries match</div><div class="card-s">${nf(rows.filter(isAlert).length)} at or above the alert cut-off · faded rows are below it</div></div></div>
        <div class="filters">
          <label class="ctl">${ICON.search}<input type="text" id="fq" placeholder="Search…" value="${esc(S.q)}"></label>
          <label class="ctl">Min score <input type="range" id="fmin" min="${wr.min_score}" max="100" value="${Math.max(S.minScore, wr.min_score)}"><b id="fminv">${Math.max(S.minScore, wr.min_score)}</b></label>
          <label class="ctl">Alert cut-off <input type="range" id="fcut" min="${wr.min_score}" max="99" value="${S.cutoff}"><b id="fcutv">${S.cutoff}</b></label>
          <label class="ctl">Parameter <select id="fparam"><option value="all">All</option><option>P1 Timing</option><option>P2 Amount</option><option>Context</option></select></label>
          <label class="ctl">Source <select id="fsrc"><option value="all">All</option><option value="manual">Manual</option><option value="system">System</option></select></label>
          <label class="ctl">Status <select id="fstat"><option value="all">All</option><option value="open">Open</option><option value="retained">Retained</option><option value="investigate">To investigate</option><option value="dismissed">Dismissed</option></select></label>
        </div>
        <div class="table-wrap"><table><thead><tr><th>Risk</th><th>Entry</th><th>Posted</th><th>User</th><th class="r">Amount</th><th>Red flags</th><th>Status</th></tr></thead><tbody>
          ${rows.slice(0, S.shown).map(a => `<tr class="click" data-id="${esc(a.id)}" style="${isAlert(a) ? "" : "opacity:.55"}">
            <td>${scoreCell(a.score)}</td>
            <td><div class="lt">${esc(a.text)}</div><div class="ls">${esc(a.id)} · ${esc(a.source)} · ${esc(a.nature)}${a.injected ? ` · <span class="orange">${labelWord()}</span>` : ""}</div></td>
            <td>${dmy(a.posting_date)}</td><td>${esc(a.user)}</td><td class="r bold">${eur(a.amount)}</td>
            <td><div class="chips">${a.rules.slice(0, 2).map(ruleTag).join("")}${a.rules.length > 2 ? `<span class="tag gray">+${a.rules.length - 2}</span>` : ""}${!a.rules.length ? '<span class="tag gray">Models only</span>' : ""}</div></td>
            <td>${decTag(decisionOf(a.id))}</td></tr>`).join("") || `<tr><td colspan="7" class="empty">No entry matches these filters.</td></tr>`}
        </tbody></table></div>
        ${rows.length > S.shown ? `<div class="more" style="padding:0 0 20px"><button class="link" id="more">Show 50 more</button></div>` : ""}
      </div>`;
    $("#fparam").value = S.param; $("#fsrc").value = S.source; $("#fstat").value = S.status;
    const re = () => {                                   // re-draw, then give focus back to the control in use
      const f = document.activeElement && document.activeElement.id;
      S.shown = 50; renderAlerts();
      if (f && $("#" + f) && f !== "fq") $("#" + f).focus();
    };
    $("#fq").oninput = e => { S.q = e.target.value; clearTimeout(S._t); S._t = setTimeout(() => { re(); const f = $("#fq"); f.focus(); f.setSelectionRange(S.q.length, S.q.length); }, 250); };
    $("#fmin").oninput = e => { $("#fminv").textContent = e.target.value; }; $("#fmin").onchange = e => { S.minScore = +e.target.value; re(); };
    $("#fcut").oninput = e => { $("#fcutv").textContent = e.target.value; }; $("#fcut").onchange = e => { S.cutoff = +e.target.value; store.set("je-audit-cutoff", S.cutoff); updateNavCount(); re(); };
    $("#fparam").onchange = e => { S.param = e.target.value; re(); };
    $("#fsrc").onchange = e => { S.source = e.target.value; re(); };
    $("#fstat").onchange = e => { S.status = e.target.value; re(); };
    if ($("#more")) $("#more").onclick = () => { S.shown += 50; renderAlerts(); };
    $("#expCsv").onclick = () => exportFile("csv"); $("#expXlsx").onclick = () => exportFile("xlsx");
  }

  // ---------------------------------------------------------------- Data & EDA
  function renderAnalytics() {
    const c = D.dataset.datacard, b = D.charts.benford;
    head("Data & EDA", `${esc(D.dataset.name)} · ${esc(c.format)} · ${esc(c.period)}`);
    const conf = x => (x === "close" ? "good" : x === "nonconformity" ? "bad" : "warn");
    const fl = D.charts.flags_all, flMax = Math.max(...Object.values(fl));
    $("#page-analytics").innerHTML = `
      <div class="grid g4">
        ${stat("Ledger lines", nf(c.lines), `${esc(c.file || "")}`, "doc", true, 0)}
        ${stat("Entries", nf(c.entries), `${nf(c.manual_entries)} manual entries`, "layers", false, 1)}
        ${stat("Users · accounts", `${c.users} · ${c.accounts}`, `${esc(c.chart_of_accounts)} chart of accounts`, "user", false, 2)}
        ${stat("Unbalanced · missing", `${c.unbalanced_entries} · ${c.missing_values}`, '<span class="badge good">clean</span> consistency checks', "shield", false, 3)}
      </div>
      <div class="grid g2">
        <div class="card flush" style="--i:4"><div class="card-head"><div><div class="card-t">Datacard</div><div class="card-s">${esc(D.dataset.license)} · open data</div></div></div>
          <div class="table-wrap"><table><tbody>
            <tr><td class="muted">Source</td><td><a href="${esc(D.dataset.url)}" target="_blank" rel="noopener" style="color:var(--accent-text)">Zenodo · DOI ${esc(D.dataset.doi)}</a></td></tr>
            <tr><td class="muted">Authors</td><td>${esc(D.dataset.authors)}</td></tr>
            <tr><td class="muted">Period</td><td>${esc(c.period)}</td></tr>
            <tr><td class="muted">Public holidays</td><td>${esc(D.dataset.holiday_country)} · ${D.dataset.holidays_in_period} days · ${esc(D.dataset.holiday_source)}</td></tr>
            <tr><td class="muted">Checks</td><td>${c.unbalanced_entries} unbalanced · ${c.missing_values} missing · ${c.entered_before_posting} entered before document date</td></tr>
          </tbody></table></div></div>
        <div class="card" style="--i:5"><div class="card-t">Do we trust the data?</div><div class="card-s">What the EDA tells us before we model</div>
          <div class="list-r" style="margin-top:14px">
            ${[[c.unbalanced_entries ? "warn" : "good", "check", c.unbalanced_entries ? "Some entries do not balance" : "Clean and balanced",
                 c.labelled_entries ? `${nf(c.labelled_entries)} entries carry the dataset's own anomaly labels (${pct(c.labelled_entries / c.entries, 2)}). The generator's helper columns are dropped so the models cannot cheat.`
                   : "Every entry balances. The file has no labels, so we inject labelled demo anomalies to test the system."],
               ["p2", "coins", "Benford fails for the whole ledger", `MAD ${b.mad}. Fixed product prices drive the first digits, so Benford is context per user, not an alarm.`],
               ["acc", "calendar", "Weekends and holidays are normal here", `${nf(fl["Entered on a weekend"] || 0)} entries were typed in on a weekend and ${nf(fl["Posted on a public holiday"] || 0)} posted on ${esc(D.dataset.holiday_country)} holidays. A timing flag alone is weak evidence; timing flags count fully only for manual entries.`],
               ["", "doc", c.chart_of_accounts === "PCG" ? "A French company" : "A German company", `${esc(c.chart_of_accounts)} accounts. We apply NEP 240 / ISA 240; the holiday country follows the chart (${esc(D.dataset.holiday_country)}).`],
               [c.has_entry_time ? "good" : "bad", "clock", c.has_entry_time ? "Entry times are available" : "No entry time", c.has_entry_time ? `The working day is learned from the data (${(D.settings.working_hours || []).join("–")}h); off-hours and per-user hour checks are on.` : "Off-hours and per-user hour checks are switched off for this file."]]
              .map(([cl, ic, t, s]) => `<div class="li"><span class="mark ${cl}">${ICON[ic]}</span><div><div class="lt">${t}</div><div class="ls">${s}</div></div><span></span></div>`).join("")}
          </div></div>
      </div>
      <div class="grid g2 tables">
        <div class="card" style="--i:6"><div class="card-head"><div><div class="card-t">First digit vs Benford's law</div><div class="card-s">All entry amounts</div></div>
          <div class="legend" style="margin:0"><span><i style="background:var(--c3)"></i>Observed</span><span><i style="background:var(--accent)"></i>Benford</span></div></div>
          <div class="chart-box"><canvas id="cBenford"></canvas></div></div>
        <div class="card flush" style="--i:7"><div class="card-head"><div><div class="card-t">Users</div><div class="card-s">Volume, manual entries, alerts and Benford conformity</div></div></div>
          <div class="table-wrap"><table><thead><tr><th>User</th><th class="r">Entries</th><th class="r">Manual</th><th class="r">Night</th><th class="r">Alerts</th><th>Benford</th></tr></thead><tbody>
          ${D.charts.users.map(u => { const bu = b.by_user.find(x => x.user === u.user) || {}; return `<tr><td><div style="display:flex;align-items:center;gap:10px"><span class="av">${esc(u.user.slice(0, 2).toUpperCase())}</span><b>${esc(u.user)}</b></div></td><td class="r">${nf(u.entries)}</td><td class="r">${nf(u.manual)}</td><td class="r">${nf(u.night)}</td><td class="r">${nf(u.alerts)}</td><td><span class="badge ${conf(bu.conformity)}">${esc(bu.conformity || "")}</span> <span class="muted tiny">${bu.mad ?? ""}</span></td></tr>`; }).join("")}
          </tbody></table></div></div>
      </div>
      <div class="grid g3">
        <div class="card" style="--i:8"><div class="card-t">Postings by weekday</div><div class="card-s">By posting date</div><div class="chart-box sm" style="margin-top:12px"><canvas id="cWeek"></canvas></div></div>
        <div class="card" style="--i:9"><div class="card-t">Risk score distribution</div><div class="card-s">All ${nf(D.kpis.entries)} entries · log scale</div><div class="chart-box sm" style="margin-top:12px"><canvas id="cHist"></canvas></div></div>
        <div class="card" style="--i:10"><div class="card-t">Amount posted per month</div><div class="card-s">Total debit of all entries · December highlighted</div><div class="chart-box sm" style="margin-top:12px"><canvas id="cAmt"></canvas></div></div>
      </div>
      <div class="card" style="--i:11"><div class="card-head"><div><div class="card-t">Red flags in the whole ledger</div><div class="card-s">Entries with each flag before weighting</div></div>
        <div class="legend" style="margin:0"><span><i style="background:var(--accent)"></i>P1 Timing</span><span><i style="background:var(--p2)"></i>P2 Amount</span><span><i style="background:var(--c2)"></i>Context</span></div></div>
        <div class="hb">${Object.entries(fl).sort((x, y) => y[1] - x[1]).map(([f, n]) => `<div class="r"><span>${esc(f)}</span><b>${nf(n)}</b><div class="t"><i style="width:${Math.max(1.5, Math.log10(n + 1) / Math.log10(flMax + 1) * 100)}%;background:${PCOL[paramOf(f)]}"></i></div></div>`).join("")}</div>
        <div class="tiny muted" style="margin-top:12px">Bar length on a log scale so rare flags stay visible.</div></div>`;
    const t = chartTheme();
    mkChart("cBenford", { type: "bar", data: { labels: b.overall.map(x => x.digit), datasets: [
      { type: "line", data: b.overall.map(x => x.benford * 100), borderColor: t.acc, borderWidth: 2.5, pointRadius: 3.5, pointBackgroundColor: t.surface, pointBorderColor: t.acc, pointBorderWidth: 2, tension: .35 },
      { data: b.overall.map(x => x.observed * 100), backgroundColor: t.c3, borderRadius: 8, borderSkipped: false, maxBarThickness: 34 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { tooltip: { callbacks: { label: c => ` ${c.datasetIndex ? "Observed" : "Benford"} ${nf(c.raw, 1)}%` } } }, scales: axes(t, { y: { ticks: { callback: v => v + "%" } } }) } });
    const wk = D.charts.weekday;
    mkChart("cWeek", { type: "bar", data: { labels: wk.map(w => w.day.slice(0, 3)), datasets: [{ data: wk.map(w => w.n), backgroundColor: wk.map((w, i) => (i >= 5 ? t.acc : t.c3)), borderRadius: 8, borderSkipped: false, maxBarThickness: 30 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { tooltip: { callbacks: { label: c => " " + nf(c.raw) + " postings" } } }, scales: axes(t, { y: { type: "logarithmic", ticks: { callback: v => ([1, 10, 100, 1000, 10000].includes(v) ? nf(v) : "") } } }) } });
    const h = D.charts.score_hist;
    mkChart("cHist", { type: "bar", data: { labels: h.map((_, i) => `${i * 5}`), datasets: [{ data: h, backgroundColor: h.map((_, i) => (i * 5 >= S.cutoff ? t.acc : t.c3)), borderRadius: 4, borderSkipped: false }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { tooltip: { callbacks: { title: c => `Score ${c[0].label}–${+c[0].label + 5}`, label: c => " " + nf(c.raw) + " entries" } } },
        scales: axes(t, { x: { ticks: { maxTicksLimit: 6 } }, y: { type: "logarithmic", ticks: { callback: v => ([1, 10, 100, 1000, 10000, 100000].includes(v) ? nf(v) : "") } } }) } });
    const mo = D.charts.monthly;
    mkChart("cAmt", { type: "bar", data: { labels: mo.map(x => monLabel(x.month)), datasets: [{ data: mo.map(x => x.amount), backgroundColor: mo.map(x => (x.month.endsWith("-12") ? t.acc : t.c3)), borderRadius: 5, borderSkipped: false }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { tooltip: { callbacks: { label: c => " " + eur(c.raw, 0) } } }, scales: axes(t, { x: { ticks: { maxTicksLimit: 5 } }, y: { ticks: { callback: v => eurShort(v) } } }) } });
  }

  // ---------------------------------------------------------------- Models & prediction
  function renderModels() {
    const m = D.metrics, f = D.forecast, p2r = m.person2_reported;
    head("Models & prediction", esc(m.split));
    const fcCard = () => {
      const flagged = (f.months || []).filter(x => x.flag);
      return `<div class="card" style="--i:6"><div class="card-head"><div><div class="card-t">Predictive analytics · expected vs actual revenue</div>
          <div class="card-v">${flagged.length ? `${flagged.length} month${flagged.length > 1 ? "s" : ""} outside the band` : "On expectation"}</div><div class="card-s">${esc(f.method || "")} · band ±${f.band_pct ?? "-"}%</div></div>
          <div class="legend" style="margin:0"><span><i style="background:var(--accent)"></i>Actual</span><span><i style="background:var(--c2)"></i>Expected</span><span><i style="background:var(--bad)"></i>Outside band</span></div></div>
          <div class="chart-box lg"><canvas id="cFc"></canvas></div>
          <div class="chips" style="margin-top:12px">${flagged.map(x => `<span class="badge bad">${monLabel(x.month)}: ${eurShort(x.actual)} vs ${eurShort(x.expected)} expected</span>`).join("")}</div></div>`;
    };
    const recipe = `<div class="card" style="--i:9"><div class="card-t">Scoring recipe</div><div class="card-s">Transparent and adjustable in <code>pipeline/config.py</code> and <code>pipeline/model.py</code></div>
        <div class="grid g4" style="margin:16px 0 0">
          <div class="inner"><div class="lbl2">1 · Rules (points)</div><div class="chips">${Object.entries(m.rules || {}).map(([r, w]) => `<span class="tag gray">${esc(r.replace(/_/g, " "))} · ${w}</span>`).join("")}</div>
            <div class="card-s" style="margin-top:10px">Manual entries count 100%, system entries ${nf((D.settings.system_weight ?? .25) * 100)}%; recurring manual entries (rent, salaries) 30%.</div></div>
          <div class="inner"><div class="lbl2">2 · Unsupervised</div><div class="card-s">Isolation Forest, LOF and an autoencoder, no labels. The autoencoder or LOF replaces Isolation Forest only with a clear gain (+0.02 PR-AUC). Used here: <b>${esc(m.unsupervised_choice)}</b>. Only the top 10% of outliers add to the score.</div></div>
          <div class="inner"><div class="lbl2">3 · XGBoost + SHAP</div><div class="card-s">Predicts P(anomaly) from the red flags, amounts and who entered it; the cut is tuned on validation rows${m.xgb_threshold ? ` (${m.xgb_threshold.final})` : ""}. SHAP explains each entry. Generator columns and <code>is_manual</code> are excluded.</div></div>
          <div class="inner"><div class="lbl2">4 · Person 2's model</div><div class="card-s">${esc(m.person2_note || "not used")}. HistGradientBoosting on Person 2's 12 features, exported to JSON so it runs on any scikit-learn version.</div></div>
        </div>
        <div class="card-s" style="margin-top:14px">Risk = 100 × [1 − (1 − rules) × (1 − ${m.weights.xgb} × XGB) × (1 − ${m.weights.person2} × Person 2) × (1 − ${m.weights.unsupervised} × outlier)] · each model's own cut lands at 54 · alert at ≥ ${D.settings.alert_cutoff}</div></div>`;
    if (!m.by_type || !m.by_type.length) {
      $("#page-models").innerHTML = `<div class="card"><div class="card-t">No labelled anomalies in this run</div><p class="card-s" style="margin-top:8px">Scored with rules, the unsupervised detectors${m.person2_note && !/not|missing|off/.test(m.person2_note) ? " and Person 2's model" : ""}. Run <code>python -m pipeline.run --inject 42</code> to add labelled demo anomalies, train XGBoost and run the circularity test.</p></div><div class="grid g-wide">${fcCard()}<div></div></div>${recipe}`;
      drawForecast(f);
      return;
    }
    const models = Object.entries(m.models);
    const comb = m.models["Risk score (combined)"];
    const heat = v => (v === null || v === undefined ? "" : v >= .8 ? "good" : v >= .4 ? "warn" : "bad");
    const best = models.filter(([n]) => !n.includes("in-sample")).reduce((a, b) => ((b[1].pr_auc || 0) > (a[1].pr_auc || 0) ? b : a))[0];
    const uName = { iforest: "IForest", lof: "LOF", autoencoder: "AE" }[m.unsupervised_choice] || "IForest";
    const cols = [["rules", "Rules"], [m.unsupervised_choice || "iforest", uName], ["xgboost", "XGB"], ["combined", "Score"]];
    if (m.by_type.some(t => t.person2 !== null && t.person2 !== undefined)) cols.splice(3, 0, ["person2", "P2*"]);
    const p2t = p2r && p2r.xgboost_threshold_0_5;
    $("#page-models").innerHTML = `
      <div class="grid g4">
        ${stat("Ranking · PR-AUC", comb.pr_auc ?? "-", "combined score, unseen test period", "target", true, 0)}
        ${stat("Precision · recall", `${pct(comb.precision)} · ${pct(comb.recall)}`, `${nf(comb.alerts)} alerts on ${nf(m.eval_rows)} test entries`, "layers", false, 1)}
        ${stat("Recall on taught types", m.recall_seen_types ? pct(m.recall_seen_types["Risk score (combined)"]) : "n/a", `held-out types excluded: ${esc((m.held_out_types || []).join(", "))}`, "check", false, 2)}
        ${stat("Precision in the top k", pct(comb.precision_at_k), `k = ${nf(m.eval_positives)} (number of test anomalies)`, "brain", false, 3)}
      </div>
      <div class="grid g2 tables">
        <div class="card flush" style="--i:4"><div class="card-head"><div><div class="card-t">Model comparison</div><div class="card-s">${nf(m.eval_rows)} entries the supervised model never trained on · ${nf(m.eval_positives)} ${labelWord()} anomalies</div></div></div>
          <div class="table-wrap"><table class="matrix"><thead><tr><th>Layer</th><th class="r">Alerts</th><th class="r">Precision</th><th class="r">Recall</th><th class="r">F1</th><th class="r" title="Precision in the top k">Top k</th><th class="r">PR-AUC</th></tr></thead><tbody>
          ${models.map(([n, v]) => `<tr><td><b>${esc(n.replace(" (combined)", ""))}</b>${n === best ? '<div><span class="badge acc" style="height:20px;margin-top:4px">best ranking</span></div>' : ""}</td><td class="r">${nf(v.alerts)}</td><td class="r">${pct(v.precision)}</td><td class="r">${pct(v.recall)}</td><td class="r">${v.f1 ?? "-"}</td><td class="r">${pct(v.precision_at_k)}</td><td class="r">${v.pr_auc ?? "-"}</td></tr>`).join("")}
          ${p2t ? `<tr><td><b>Person 2 model, own temporal test</b><div class="tiny muted">from model_metrics.json · test after ${esc(p2r.temporal_train_cutoff)}</div></td><td class="r">${nf(p2t.predicted_anomalies)}</td><td class="r">${pct(p2t.precision)}</td><td class="r">${pct(p2t.recall)}</td><td class="r">${nf(p2t.f1_score, 3)}</td><td class="r">-</td><td class="r">${nf(p2t.average_precision, 3)}</td></tr>` : ""}
          </tbody></table></div>
          <div style="padding:16px 22px 22px;display:grid;gap:10px">
            ${models.some(([n]) => n.includes("in-sample")) ? `<div class="note warn"><b>Person 2's model is in-sample here:</b> it was trained on every label of this ledger, so its row above flatters it. Its own temporal test is the fair comparison, and the combined score is evaluated without it.</div>` : ""}
            <div class="note"><b>Why are the rules weak here?</b> In the DIB ledger ${nf(D.kpis.labelled)} entries are labelled, but thousands of normal entries share the same pattern (late, weekend, off-hours). The labels are a sample, so a rule alone cannot be precise; the models learn which ones were picked.</div></div></div>
        <div class="card flush" style="--i:5"><div class="card-head"><div><div class="card-t">Circularity test</div><div class="card-s">Recall by anomaly type · <span class="badge acc" style="height:20px">unseen</span> = never shown to XGBoost</div></div></div>
          <div class="table-wrap"><table class="matrix"><thead><tr><th>Type</th><th class="r">n</th>${cols.map(([, l]) => `<th>${l}</th>`).join("")}</tr></thead><tbody>
          ${m.by_type.map(t => `<tr><td>${esc(typeName(t.type))}${t.held_out ? ' <span class="badge acc" style="height:20px">unseen</span>' : ""}</td><td class="r">${t.n}</td>${cols.map(([k]) => `<td class="c"><span class="badge ${heat(t[k])}">${pct(t[k])}</span></td>`).join("")}</tr>`).join("")}
          </tbody></table></div>
          <div style="padding:16px 22px 22px;display:grid;gap:10px"><div class="note warn">XGBoost misses the types it never saw: it only finds what it was taught. That is why it never works alone, and why new patterns need new rules.</div>${cols.some(c => c[0] === "person2") ? '<div class="tiny muted">* Person 2, in-sample (saw every type in training).</div>' : ""}</div></div>
      </div>
      <div class="grid g-wide">
        ${fcCard()}
        <div class="card" style="--i:7"><div class="card-t">What drives XGBoost</div><div class="card-s">Feature importance (gain)</div>
          <div class="hb" style="margin-top:16px">${m.feature_importance.slice(0, 9).map((x, i) => `<div class="r"><span>${esc(x.feature)}</span><b>${nf(x.importance * 100, 1)}%</b><div class="t"><i class="${i === 0 ? "acc" : ""}" style="width:${x.importance / m.feature_importance[0].importance * 100}%"></i></div></div>`).join("")}</div></div>
      </div>
      ${recipe}`;
    drawForecast(f);
  }
  function drawForecast(f) {
    const t = chartTheme();
    const hist = f.history || [], mon = f.months || [], pad = hist.map(() => null);
    mkChart("cFc", { type: "line", data: { labels: [...hist, ...mon].map(x => monLabel(x.month)), datasets: [
      { data: [...pad, ...mon.map(x => x.high)], borderColor: "transparent", pointRadius: 0, fill: "+1", backgroundColor: alpha(t.c3, .18) },
      { data: [...pad, ...mon.map(x => x.low)], borderColor: "transparent", pointRadius: 0, fill: false },
      { label: "Expected", data: [...pad, ...mon.map(x => x.expected)], borderColor: t.c2, borderDash: [5, 5], borderWidth: 2, pointRadius: 0, tension: .35 },
      { label: "Actual", data: [...hist.map(x => x.actual), ...mon.map(x => x.actual)], borderColor: t.acc, borderWidth: 2.5, tension: .35,
        pointRadius: c => (mon[c.dataIndex - pad.length]?.flag ? 6 : 3), pointBackgroundColor: c => (mon[c.dataIndex - pad.length]?.flag ? t.bad : t.surface),
        pointBorderColor: c => (mon[c.dataIndex - pad.length]?.flag ? t.bad : t.acc), pointBorderWidth: 2 },
    ] }, options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { tooltip: { filter: i => i.datasetIndex >= 2, callbacks: { label: c => ` ${c.dataset.label} ${eur(c.raw, 0)}` } } },
      scales: axes(t, { y: { ticks: { callback: v => eurShort(v) } } }) } });
  }

  // ---------------------------------------------------------------- Gen AI
  function renderGenAI() {
    const s = S.liveSummary || D.summary;
    head("Gen AI & prompts", "A local LLM explains and documents; it never scores");
    $("#page-genai").innerHTML = `
      <div class="grid g-wide">
        <div class="card" style="--i:0"><div class="card-head"><div><div class="card-t">Engagement summary</div><div class="card-s">Written from the computed facts only · ${esc(s.source || "")}</div></div>
          <button class="btn acc" id="sumBtn" ${S.aiOnline ? "" : "disabled title='Start Ollama first'"}>${ICON.spark}Rewrite with local AI</button></div>
          <p style="line-height:1.65;font-size:15px">${esc(s.overview)}</p>
          <div class="grid g3" style="margin:18px 0 0">
            ${[["Key themes", s.key_themes], ["Next steps", s.recommended_next_steps], ["Limitations", s.limitations]].map(([t, l]) => `<div class="inner"><div class="lbl2">${t}</div><ul class="list small">${(l || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`).join("")}
          </div></div>
        <div class="card" style="--i:1"><div class="card-t">Local AI · sovereignty</div><div class="card-s">The LLM runs on the auditor's laptop with Ollama: client data never leaves it.</div>
          <div class="biz" style="margin:16px 0"><span class="mark ${S.aiOnline ? "good" : "bad"}">${ICON.spark}</span><div><div class="nm">${S.aiOnline ? "Ollama is running" : "Ollama not detected"}</div><div class="st">${S.aiOnline ? esc(S.aiModels.join(", ") || "no model pulled") : "Memos below are pre-written"}</div></div></div>
          <div style="display:grid;gap:10px">
            <label class="ctl">Model <input type="text" id="modelIn" value="${esc(S.model)}"></label>
            <label class="ctl">Memo language <select id="langIn"><option>English</option><option>French</option></select></label></div>
          <div class="note" style="margin-top:14px">To use it from this page: install Ollama, run <code>ollama pull llama3</code>, then <code>OLLAMA_ORIGINS="*" ollama serve</code>.</div></div>
      </div>
      <div class="grid g2">
        <div class="card" style="--i:2"><div class="card-t">Alerts by theme</div><div class="card-s">All ${nf(D.kpis.alerts)} alerts, grouped by their main red flag</div>
          <div class="hb" style="margin-top:16px">${Object.entries(D.themes || {}).map(([k, n], i) => `<div class="r"><span>${esc(k)}</span><b>${nf(n)}</b><div class="t"><i class="${i === 0 ? "acc" : ""}" style="width:${n / Math.max(1, D.kpis.alerts) * 100}%"></i></div></div>`).join("")}</div></div>
        <div class="card" style="--i:3"><div class="card-t">Ask the alerts</div><div class="card-s">Question in plain language; the local AI answers from the top alerts only</div>
          <div style="display:flex;gap:8px;margin-top:14px"><label class="ctl" style="flex:1">${ICON.search}<input type="text" id="askIn" placeholder="e.g. Which users have the most off-hours alerts?"></label><button class="btn acc" id="askBtn" ${S.aiOnline ? "" : "disabled title='Start Ollama first'"}>Ask</button></div>
          <div id="askOut" class="small" style="margin-top:12px;line-height:1.6">${S.aiOnline ? "" : '<span class="muted">Offline: run <code>python -m pipeline.ask "your question"</code> on the auditor\'s laptop, or start Ollama.</span>'}</div></div>
      </div>
      <div class="grid g4">
        ${[["Generation", "Audit memos and the engagement summary", "doc"], ["Data enrichment", "Nature of each entry: accrual, reversal…", "layers"],
           ["Analysis", "Rules + SHAP turned into plain-language reasons", "brain"], ["Recommendation", "Follow-up audit procedures per alert", "target"]]
          .map(([t, d, i], n) => stat(t, "", d, i, n === 0, n + 2)).join("")}
      </div>
      <div class="card" style="--i:6"><div class="card-head"><div><div class="card-t">Prompt library · ${esc(D.prompts.version)}</div><div class="card-s">System prompt = how the AI behaves · user prompt = context + question</div></div></div>
        ${D.prompts.library.map(p => `<details><summary><span>${esc(p.name)}</span><span class="badge ${p.role === "system" ? "acc" : ""}">${p.role} · ${esc(p.used_for)}</span></summary><pre>${esc(p.text)}</pre></details>`).join("")}
        <div class="lbl2" style="margin-top:18px">Change log</div><ul class="list small">${D.prompts.log.map(l => `<li>${esc(l)}</li>`).join("")}</ul></div>`;
    $("#langIn").value = S.language;
    $("#askBtn").onclick = async e => {
      const q = $("#askIn").value.trim(); if (!q) return;
      const b = e.currentTarget; b.disabled = true; b.innerHTML = '<span class="spin"></span>';
      try {
        const table = alertsNow().slice(0, 60).map(a => `${a.id} | ${a.posting_date} | ${a.user} | ${a.source} | ${nf(a.amount)} EUR | score ${a.score} | ${a.rules.join("; ") || "models only"} | ${a.text}`).join("\n");
        const res = await aiChat(lib("System").replace("{language}", S.language), fill(lib("Ask"), { question: q, table }));
        $("#askOut").innerHTML = `<p>${esc(res.answer || JSON.stringify(res))}</p>${(res.entries || res.entry_ids || []).length ? `<div class="chips">${(res.entries || res.entry_ids).map(id => `<button class="tag gray li" data-id="${esc(id)}" style="cursor:pointer">${esc(id)}</button>`).join("")}</div>` : ""}<div class="tiny muted" style="margin-top:6px">${esc(S.model)} · answer from the alert table only · check before use</div>`;
      } catch (err) { toast("Local AI error: " + err.message); }
      b.disabled = !S.aiOnline; b.textContent = "Ask";
    };
    $("#modelIn").onchange = e => { S.model = e.target.value.trim(); store.set("je-audit-model", S.model); };
    $("#langIn").onchange = e => { S.language = e.target.value; };
    $("#sumBtn").onclick = async e => {
      const b = e.currentTarget; b.disabled = true; b.innerHTML = '<span class="spin"></span> Writing…';
      try {
        const al = alertsNow(), byRule = {}, byParam = {};
        al.forEach(a => a.rules.forEach(r => { byRule[r] = (byRule[r] || 0) + 1; byParam[paramOf(r)] = (byParam[paramOf(r)] || 0) + 1; }));
        const facts = { ledger: `${D.dataset.datacard.format}, ${D.dataset.datacard.period}`, n_entries: D.kpis.entries, n_manual: D.kpis.manual, cutoff: S.cutoff,
          n_alerts: totalAlerts(), themes: JSON.stringify(D.themes), value_under_review: nf(D.kpis.value_under_review),
          ground_truth: D.kpis.labelled ? `${D.kpis.found} of ${D.kpis.labelled} ${labelWord()} entries are alerted` : "no labels",
          forecast_flags: (D.forecast.months || []).filter(x => x.flag).map(x => x.month).join(", ") || "none",
          top5: al.slice(0, 5).map(a => `${a.id} ${a.text} ${nf(a.amount)} EUR score ${a.score}`).join("; ") };
        const res = await aiChat(lib("System").replace("{language}", S.language), fill(lib("Engagement"), facts));
        res.source = S.model + " (local, live)"; S.liveSummary = res; renderGenAI(); toast("Summary rewritten by the local AI");
      } catch (err) { toast("Local AI error: " + err.message); b.disabled = false; b.innerHTML = ICON.spark + "Rewrite with local AI"; }
    };
  }

  // ---------------------------------------------------------------- Method
  function renderMethod() {
    head("Method", "Project 2 · Testing 100% of journal entries · AI & Finance, Team 9");
    const comb = D.metrics.models["Risk score (combined)"] || {};
    $("#page-method").innerHTML = `
      <div class="grid g2">
        <div class="card" style="--i:0"><div class="card-t">Business objective</div>
          <p style="margin-top:10px;line-height:1.65">Help an external auditor test <b>every</b> journal entry instead of a sample. NEP 240 / ISA 240 require the auditor to test the appropriateness of journal entries and other adjustments made when preparing the financial statements.</p>
          <div class="list-r" style="margin-top:14px">
            ${[["acc", "target", "M1 · Detect", "Rules + Isolation Forest / LOF / autoencoder", `Recall ${pct(comb.recall)}`],
               ["p2", "layers", "M2 · Prioritise (predict)", "XGBoost + SHAP, Person 2's model", `PR-AUC ${comb.pr_auc ?? "n/a"}`],
               ["good", "doc", "M3 · Document", "Person 3's library + local LLM memo per alert", "Auditor decides"]]
              .map(([c, i, t, s, r]) => `<div class="li"><span class="mark ${c}">${ICON[i]}</span><div><div class="lt">${t}</div><div class="ls">${s}</div></div><div class="lr">${r}</div></div>`).join("")}
          </div></div>
        <div class="card" style="--i:1"><div class="card-t">Two parameters + context</div><div class="card-s">Timing and amount; context flags (rare account pairs, new accounts, unusual hour for the user, duplicates) support them</div>
          <div class="inner" style="margin-top:14px"><span class="tag blue">P1 Timing</span><p class="small" style="margin-top:8px;line-height:1.6">Weekend or public-holiday posting, year-end closing window, revenue booked at year end, entered 10–29 days or 30+ days after the posting date, entered outside the ledger's working day or on a weekend. Holidays via the Nager.Date API (${esc(D.dataset.holiday_source)}).</p></div>
          <div class="inner" style="margin-top:12px"><span class="tag purple">P2 Amount</span><p class="small" style="margin-top:8px;line-height:1.6">Round amounts, high cash disbursements, just below the approval threshold (€${nf(D.settings.approval_threshold)}), several near-threshold entries by one user on one day, above performance materiality (${Object.entries(D.settings.performance_materiality).map(([y, v]) => `${y}: €${nf(v)}`).join(" · ")}), unusual amount for the account.</p></div></div>
      </div>
      <div class="grid g2">
        <div class="card" style="--i:2"><div class="card-t">Pipeline</div><div class="card-s">The professor's analysis steps</div>
          <ol class="list" style="margin-top:12px"><li>Collect: DIB general ledger (Person 1) + Nager.Date API; FEC and mapped CSV also read</li><li>Datacard and consistency checks; generator columns dropped</li><li>EDA: Benford, weekday, hour, monthly</li><li>Labels: the dataset's own (850) or injected demo anomalies</li><li>Features: P1 timing, P2 amount, context</li><li>Split: temporal (last 25% of the period) + held-out types</li><li>Rules → unsupervised → XGBoost → Person 2's model → combined score</li><li>Evaluate: precision, recall, F1, PR-AUC, circularity</li><li>Gen AI: nature, themes, memos from Person 3's library, summary (local)</li><li>Decide: the auditor reviews every alert</li></ol>
          <div class="note" style="margin-top:14px">Refresh the data:<pre>pip install -r requirements.txt
python -m pipeline.run                       # original DIB file, own labels
python -m pipeline.run --input my_FEC.txt    # a French FEC
python -m pytest -q                          # tests</pre></div></div>
        <div class="card" style="--i:3"><div class="card-t">Limits &amp; governance</div><div class="card-s">What the reader must know</div>
          <ul class="list" style="margin-top:12px"><li>The ledger and its labels are synthetic: real fraud can look different, and a score is not a probability of fraud.</li><li>Labels are a sample of entries matching each pattern, so precision has a ceiling; held-out types show what the ML cannot see.</li><li>Thresholds and materiality are our assumptions (adjustable).</li><li>The LLM can sound right and be wrong: it only receives computed facts, uses JSON output and temperature 0.2, and every memo must be reviewed.</li><li>Human accountability: the AI flags and explains; the auditor decides and signs.</li><li>Confidential client data stays local (Ollama); this website only shows results.</li><li>Decisions made here are saved in this browser only. Export them to Excel for the working papers.</li></ul>
          <div class="note" style="margin-top:14px">Data: ${esc(D.dataset.authors)}, <i>${esc(D.dataset.name)}</i>, Zenodo, DOI ${esc(D.dataset.doi)}, ${esc(D.dataset.license)}.</div></div>
      </div>`;
  }

  // ---------------------------------------------------------------- drawer
  async function openEntry(id) {
    const a = D.alerts.find(x => x.id === id); if (!a) return;
    if (a.lazy && !memoOf(a)) { try { await loadMemos([id]); } catch (e) { toast("Could not load the memo: " + e.message); } }
    const m = memoOf(a) || { none: true }, d = S.decisions[id] || {};
    const maxShap = Math.max(...a.shap.map(s => s.shap), 0.01);
    const lvl = m.risk_level === "High" ? "bad" : m.risk_level === "Medium" ? "warn" : "good";
    $("#drawer").innerHTML = `
      <button class="icon-btn close" id="dClose" aria-label="Close">${ICON.x}</button>
      <div class="card-s">${esc(a.id)} · ${esc(a.source)} entry · ${esc(a.nature)}</div>
      <h2>${esc(a.text)}</h2>
      <div class="chips" style="margin-top:12px"><span class="badge ${a.score >= 75 ? "bad" : a.score >= 50 ? "warn" : ""}">Risk ${nf(a.score)}/100</span>${decTag(d.decision)}${a.injected ? `<span class="badge warn">${labelWord() === "labelled" ? "Labelled" : "Demo"} anomaly · ${esc(typeName(a.injected))}</span>` : ""}<span class="badge">${esc(a.theme || "")}</span></div>
      <div class="sect kv">
        ${[["Amount", eur(a.amount)], ["Posted", dmy(a.posting_date)], ["Entered", dmy(a.entered_at) + " " + a.entered_at.slice(11)], ["Delay", a.delay + " days"], ["User", esc(a.user)], ["Model scores", `Rules ${nf(a.rules_score)} · XGB ${pct(a.xgb)} · Outlier ${pct(a.iforest)}${a.p2 !== null && a.p2 !== undefined ? ` · Person 2 ${nf(a.p2, 1)}` : ""}`]]
          .map(([l, v]) => `<div><div class="tiny muted">${l}</div><div class="v">${v}</div></div>`).join("")}
      </div>
      <div class="sect"><h4>Entry lines</h4><div class="card flush" style="animation:none"><table><thead><tr><th>Account</th><th>Name</th><th class="r">Debit</th><th class="r">Credit</th></tr></thead><tbody>
        ${a.lines.map(l => `<tr><td>${esc(l.account)}</td><td>${esc(l.name)}</td><td class="r">${l.debit ? eur(l.debit) : ""}</td><td class="r">${l.credit ? eur(l.credit) : ""}</td></tr>`).join("")}</tbody></table></div></div>
      <div class="sect"><h4>Red flags (rules)</h4><div class="chips">${a.rules.map(ruleTag).join("") || '<span class="card-s">No rule triggered: flagged by the models</span>'}</div></div>
      <div class="sect"><h4>Why the model flagged it · SHAP</h4>${a.shap.map(s => `<div class="shap-row"><span>${esc(s.feature)}</span><span class="track"><i style="width:${s.shap / maxShap * 100}%"></i></span><span class="muted r">+${s.shap}</span></div>`).join("") || '<span class="card-s">No positive SHAP driver</span>'}</div>
      <div class="sect memo"><div class="card-head" style="margin-bottom:10px"><h4 style="margin:0">Audit memo</h4><button class="btn acc" id="memoBtn" ${S.aiOnline ? "" : "disabled title='Start Ollama to rewrite'"}>${ICON.spark}Rewrite with local AI</button></div>
        ${m.none ? `<div class="card" style="animation:none"><p class="small">No memo yet: this entry scored ${nf(a.score)}, below the alert cut-off of ${D.settings.alert_cutoff} when the pipeline ran, so no memo was written. ${S.aiOnline ? "Use “Rewrite with local AI” to draft one." : "Start the local AI to draft one, or run the pipeline with a lower cut-off."}</p>
          <div class="lbl2" style="margin-top:12px">Library guidance for its red flags</div><ul class="small">${recsOf(a).map(r => `<li><b>${esc(r.code)} ${esc(r.anomaly)}:</b> ${esc(r.audit_procedure)}</li>`).join("")}</ul></div>` : `<div class="card" style="animation:none">
          <div class="chips"><span class="badge ${lvl}">${esc(m.risk_level)} risk</span><span class="badge acc">Assertion · ${esc(m.assertion_at_risk)}</span>${(m.library_codes || []).map(c => `<span class="tag gray">Library ${esc(c)}</span>`).join("")}</div>
          <p style="margin-top:12px">${esc(m.why_suspicious)}</p>
          <div class="lbl2" style="margin-top:16px">Evidence to obtain</div><ul class="small">${(m.evidence_to_obtain || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
          <div class="lbl2" style="margin-top:16px">Follow-up procedures</div><ul class="small">${(m.follow_up_procedures || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
          <div class="lbl2" style="margin-top:16px">Possible legitimate explanations</div><ul class="small">${(m.possible_explanations || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
          <p class="small" style="margin-top:14px"><b>Conclusion:</b> ${esc(m.auditor_conclusion || m.conclusion || "")}</p>
          <div class="tiny muted" style="margin-top:10px">Generated by ${esc(m.source)}. Must be reviewed by the auditor.</div></div>`}</div>
      <div class="sect"><h4>Auditor decision</h4>
        <div class="dec" id="seg"><button data-v="retained" class="r">Retained</button><button data-v="investigate" class="i">To investigate</button><button data-v="dismissed" class="d">Dismissed</button></div>
        <textarea id="dCom" placeholder="Comment for the working papers…" style="margin-top:12px">${esc(d.comment || "")}</textarea>
        <div style="display:flex;gap:8px;margin-top:12px"><button class="btn" id="dSave">${ICON.check}Save decision</button>${d.decision ? '<button class="link" id="dClear">Clear</button>' : ""}</div></div>`;
    let choice = d.decision || "";
    const paint = () => document.querySelectorAll("#seg button").forEach(b => b.classList.toggle("on", b.dataset.v === choice));
    paint();
    document.querySelectorAll("#seg button").forEach(b => (b.onclick = () => { choice = b.dataset.v; paint(); }));
    $("#dSave").onclick = () => {
      if (!choice) return toast("Choose a decision first");
      S.decisions[id] = { decision: choice, comment: $("#dCom").value, ts: new Date().toISOString() };
      store.set("je-audit-decisions", S.decisions); toast("Decision saved in this browser"); closeEntry(); updateNavCount(); route(true);
    };
    if ($("#dClear")) $("#dClear").onclick = () => { delete S.decisions[id]; store.set("je-audit-decisions", S.decisions); closeEntry(); updateNavCount(); route(true); };
    $("#memoBtn").onclick = async e => {
      const b = e.currentTarget; b.disabled = true; b.innerHTML = '<span class="spin"></span> Writing…';
      try {
        const res = await aiChat(lib("System").replace("{language}", S.language), fill(lib("Audit memo"), memoFacts(a)));
        res.source = `${S.model} (local, live) · prompts ${D.prompts.version}`;
        S.memos[id] = res; store.set("je-audit-memos", S.memos); toast("Memo rewritten by the local AI"); openEntry(id);
      } catch (err) { toast("Local AI error: " + err.message); b.disabled = false; b.innerHTML = ICON.spark + "Rewrite with local AI"; }
    };
    $("#dClose").onclick = closeEntry;
    $("#overlay").classList.add("open"); $("#drawer").classList.add("open"); $("#drawer").setAttribute("aria-hidden", "false"); $("#drawer").scrollTop = 0;
  }
  function closeEntry() { $("#overlay").classList.remove("open"); $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); }
  $("#overlay").onclick = closeEntry;
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { closeEntry(); $("#app").classList.remove("menu"); }
    if (e.key === "/" && !/input|textarea|select/i.test(document.activeElement.tagName)) { e.preventDefault(); $("#globalSearch").focus(); }
  });
  document.addEventListener("click", e => { const el = e.target.closest("tr.click, button.li"); if (el && el.dataset.id) openEntry(el.dataset.id); });

  // ---------------------------------------------------------------- export
  async function exportFile(kind) {
    const list = filtered();
    try { await loadMemos(list.map(a => a.id)); } catch (e) { toast("Some memos could not be loaded: " + e.message); }
    const rows = list.map(a => {
      const m = memoOf(a) || {}, d = S.decisions[a.id] || {};
      return { entry_id: a.id, risk_score: a.score, alert: isAlert(a) ? "yes" : "no", posting_date: a.posting_date, entered_at: a.entered_at, user: a.user,
        source: a.source, nature: a.nature, text: a.text, accounts: a.accounts, amount: a.amount, red_flags: a.rules.join("; "),
        shap_drivers: a.shap.map(s => `${s.feature} (+${s.shap})`).join("; "), risk_level: m.risk_level, why_suspicious: m.why_suspicious,
        assertion: m.assertion_at_risk, evidence: (m.evidence_to_obtain || []).join(" | "), follow_up: (m.follow_up_procedures || []).join(" | "),
        library_codes: (m.library_codes || []).join(", "), conclusion: m.auditor_conclusion || m.conclusion || "", memo_source: m.source, theme: a.theme,
        person2_score: a.p2 ?? "", labelled_anomaly: a.injected || "", auditor_decision: d.decision || "", auditor_comment: d.comment || "", decided_at: d.ts || "" };
    });
    const name = `JE_audit_alerts_${new Date().toISOString().slice(0, 10)}`;
    if (kind === "xlsx" && window.XLSX) {
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(rows), "Alerts");
      XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(Object.entries(D.metrics.models).map(([k, v]) => ({ layer: k, ...v }))), "Model metrics");
      if (D.metrics.by_type.length) XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(D.metrics.by_type), "Recall by type");
      XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(Object.entries(D.dataset.datacard).map(([k, v]) => ({ item: k, value: v }))), "Datacard");
      XLSX.writeFile(wb, name + ".xlsx");
    } else {
      const headRow = Object.keys(rows[0] || { entry_id: "" });
      const csv = [headRow.join(","), ...rows.map(r => headRow.map(h => `"${String(r[h] ?? "").replace(/"/g, '""')}"`).join(","))].join("\n");
      const url = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv" }));
      const l = document.createElement("a"); l.href = url; l.download = name + ".csv"; l.click(); URL.revokeObjectURL(url);
    }
    toast(`Exported ${rows.length} entries`);
  }

  // ---------------------------------------------------------------- theme, nav, router
  function paintThemeBtn() { const dark = document.documentElement.dataset.theme === "dark"; $("#themeBtn").innerHTML = dark ? ICON.sun : ICON.moon; $("#themeBtn").title = dark ? "Light theme" : "Dark theme"; }
  $("#themeBtn").onclick = () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("je-audit-theme", next); } catch { /* ignore */ }
    paintThemeBtn(); if (D) route(true);
  };
  paintThemeBtn();
  $("#menuBtn").onclick = () => $("#app").classList.toggle("menu");
  $("#scrim").onclick = () => $("#app").classList.remove("menu");

  $("#nav").innerHTML = PAGES.map((p, i) => (i === 0 ? '<div class="nav-label">Audit</div>' : i === 2 ? '<div class="nav-label">Analysis</div>' : i === 4 ? '<div class="nav-label">AI &amp; method</div>' : "") +
    `<a class="nav-item" data-nav="${p[0]}" href="#${p[0]}">${ICON[p[2]]}<span>${p[1]}</span>${p[0] === "alerts" ? '<span class="cnt" id="navCnt"></span>' : ""}</a>`).join("");
  function updateNavCount() { if (!D) return; const n = alertsNow().filter(a => !decisionOf(a.id)).length; const c = $("#navCnt"); c.textContent = n; c.style.display = n ? "" : "none"; }

  const RENDER = { dashboard: renderDashboard, alerts: renderAlerts, analytics: renderAnalytics, models: renderModels, genai: renderGenAI, method: renderMethod };
  function route(keepScroll) {
    const id = (location.hash || "#dashboard").slice(1).split("?")[0];
    const page = RENDER[id] ? id : "dashboard";
    document.querySelectorAll(".page").forEach(p => p.classList.toggle("active", p.id === "page-" + page));
    document.querySelectorAll("[data-nav]").forEach(n => n.classList.toggle("on", n.dataset.nav === page));
    document.title = `${PAGES.find(p => p[0] === page)[1]} · JournalGuard AI`;
    $("#app").classList.remove("menu");
    RENDER[page]();
    if (keepScroll !== true) window.scrollTo({ top: 0 });
  }
  $("#globalSearch").addEventListener("keydown", e => { if (e.key === "Enter") { S.q = e.target.value; S.shown = 50; location.hash === "#alerts" ? renderAlerts() : (location.hash = "alerts"); } });
  window.addEventListener("hashchange", () => { closeEntry(); route(); });

  // ---------------------------------------------------------------- start
  fetch("data/dashboard.json", { cache: "no-cache" }).then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); }).then(data => {
    D = data;
    S.cutoff = Math.max(store.get("je-audit-cutoff", D.settings.alert_cutoff), (D.web_rows || {}).min_score || 0);
    $("#periodText").textContent = D.dataset.datacard.period;
    $("#foot").innerHTML = `Data generated ${esc(D.generated_at)} · ${esc(D.dataset.name)} (${esc(D.dataset.license)}) · holidays ${esc(D.dataset.holiday_country)} · memos: ${D.settings.llm_used ? esc(D.settings.llm_model) + " (local)" : "template (no local LLM during the run)"}`;
    updateNavCount(); route();
    checkAI().then(() => { if (location.hash === "#genai") renderGenAI(); });
  }).catch(err => {
    $("#page-dashboard").classList.add("active");
    head("Overview", "");
    $("#page-dashboard").innerHTML = `<div class="card"><div class="card-t">No data yet</div><p class="card-s" style="margin-top:8px">Could not load <code>data/dashboard.json</code> (${esc(err.message)}). Run <code>python -m pipeline.run</code>, then serve the <code>web</code> folder: <code>python -m http.server -d web</code>.</p></div>`;
  });
})();
