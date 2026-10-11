(function () {
  const $ = id => document.getElementById(id);
  const KEY = "air_api_base";
  const saved = () => { try { return localStorage.getItem(KEY); } catch (e) { return null; } };
  $("api").value = saved() || (window.AIR_CONFIG && window.AIR_CONFIG.API_BASE) || "";

  // Safe DOM builder: all API text goes in as text nodes (never innerHTML).
  const h = (t, a, ...k) => { const e = document.createElement(t);
    for (const [n, v] of Object.entries(a || {})) n === "class" ? e.className = v : e.setAttribute(n, v);
    for (const c of k.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
    return e; };
  const s = v => v == null || v === "" ? "-" : typeof v === "object" ? JSON.stringify(v) : String(v);
  const zname = z => z && typeof z === "object" ? (z.name || z.zone_id || z.id || JSON.stringify(z)) : s(z);
  const raw = (o, label) => h("details", {}, h("summary", {}, label || "Raw JSON"), h("pre", {}, JSON.stringify(o, null, 2)));
  const badge = st => h("span", { class: "badge " + (st === "NORMAL" ? "ok" : "") }, st || "-");
  const table = (cols, rows) => h("table", {}, h("tr", {}, cols.map(c => h("th", {}, c[0]))),
    rows.map(r => h("tr", {}, cols.map(c => h("td", {}, c[1](r))))));
  const kv = pairs => h("div", {}, pairs.map(p => h("div", {}, h("b", {}, p[0] + ": "), p[1])));

  async function get(path) {
    const base = $("api").value.trim().replace(/\/+$/, "");
    if (!base) throw new Error("Enter the API base URL first.");
    try { localStorage.setItem(KEY, base); } catch (e) {}
    const c = new AbortController(), t = setTimeout(() => c.abort(), 28000);
    try {
      const r = await fetch(base + path, { signal: c.signal });
      let j = null; try { j = await r.json(); } catch (e) {}
      if (!r.ok) throw new Error("HTTP " + r.status + (j && j.error ? ": " + j.error : ""));
      if (j === null) throw new Error("Response was not JSON");
      return j;
    } catch (e) {
      if (e.name === "AbortError") throw new Error("Timed out after 28s (Lambda may be cold or slow).");
      if (e instanceof TypeError) throw new Error("Network/CORS error or wrong URL (" + e.message + ")");
      throw e;
    } finally { clearTimeout(t); }
  }
  const fail = (ids, path, e) => ids.forEach(i => $(i).replaceChildren(h("p", { class: "err" }, "Could not load " + path + ": " + e.message)));
  const busy = ids => ids.forEach(i => $(i).replaceChildren(h("p", { class: "muted" }, "Loading...")));
  async function run(ids, path, render) {
    busy(ids);
    try { render(await get(path)); } catch (e) { fail(ids, path, e); }
  }

  function renderStatus(d) {
    const dec = d.decision;
    $("risk").replaceChildren(dec ? kv([
      ["State", badge(d.state)], ["Label", d.state_label], ["As of", d.as_of],
      ["Reason", dec.reason], ["Confidence", dec.confidence], ["Coverage", dec.coverage],
      ["Data sufficient", s(dec.data_sufficient)], ["Reason codes", (dec.reason_codes || []).join(", ")],
      ["Data label", d.data_label], ["Policy version", d.policy_version]]) :
      h("div", {}, kv([["State", badge(d.state)], ["Policy version", d.policy_version]]),
        h("p", { class: "muted" }, "No evaluation cycle has been processed yet, so there is no decision to show.")));
    if (dec) $("risk").append(raw(dec, "Full decision"));
    const a = d.affected_area;
    $("area").replaceChildren(a ? h("div", {}, kv([["Zones", (a.zones || []).length ? a.zones.map(zname).join(", ") : "none identified"],
      ["Confidence", a.confidence]]), raw(a, "Full area record")) : h("p", { class: "muted" }, "No affected area recorded."));
    const rd = d.readings || [];
    $("readings").replaceChildren(rd.length ? table([["Station", r => r.name || r.station_id], ["Zone", r => s(r.zone)],
      ["AQI", r => r.missing ? "missing" : s(r.aqi)], ["Note", r => r.carried_forward ? "carried forward" : ""]], rd)
      : h("p", { class: "muted" }, "No readings (no cycle processed yet)."));
  }

  function renderAlerts(list) {
    $("alerts").replaceChildren(Array.isArray(list) && list.length ? table([
      ["Alert", a => a.alert_id], ["Type (verify field)", a => s(a.alert_type)],
      ["Authorization", a => s(a.authorization_status)], ["Delivery", a => s(a.delivery_status)],
      ["Decision", a => s(a.decision_id)], ["", a => h("button", { class: "alt", onclick: "void 0" }, "Trace")]], list)
      : h("p", { class: "muted" }, "No alerts recorded."));
    $("alerts").querySelectorAll("tr").forEach((tr, i) => { if (i > 0) tr.querySelector("button").onclick = () => loadTrace(list[i - 1].alert_id); });
  }

  function renderTrace(t) {
    const msgs = t.messages || [];
    const last = msgs.slice().sort((x, y) => (x.version || 0) - (y.version || 0)).pop();
    $("trace").replaceChildren(h("div", {},
      kv([["Alert", t.alert && t.alert.alert_id], ["Trace complete", s(t.complete)],
        ["Authorization", t.alert && t.alert.authorization_status], ["Delivery", t.alert && t.alert.delivery_status],
        ["Reason", t.decision && t.decision.reason], ["Affected zones", ((t.affected_area && t.affected_area.zones) || []).map(zname).join(", ") || "-"],
        ["Observations / quality records", (t.observations || []).length + " / " + (t.data_quality || []).length]]),
      h("h3", {}, "Safety guidance"),
      last ? h("div", {}, h("div", { class: "msg" }, last.text), h("small", { class: "muted" }, "Message " + s(last.message_id) + ", method: " + s(last.method) + (last.fallback_reason ? ", fallback: " + last.fallback_reason : "")))
        : h("p", { class: "muted" }, "No message generated yet. Messages appear only after an operator approves the alert."),
      t.alert && t.alert.facts ? raw(t.alert.facts, "Alert facts used for the message") : null,
      h("h3", {}, "Audit chain"),
      (t.authorizations || []).length ? table([["Authorization", a => s(a.authorization_id)], ["To", a => s(a.to)], ["At", a => s(a.at)]], t.authorizations) : h("p", { class: "muted" }, "No authorization recorded."),
      (t.deliveries || []).length ? table([["Delivery", d => s(d.delivery_id)], ["Status", d => s(d.status)], ["Attempts", d => s(d.attempts)]], t.deliveries) : h("p", { class: "muted" }, "No (simulated) delivery recorded."),
      raw(t, "Full trace JSON")));
  }
  function loadTrace(id) { run(["trace"], "/alerts/" + encodeURIComponent(id) + "/trace", renderTrace); $("trace").scrollIntoView({ behavior: "smooth" }); }

  function renderScen(list) {
    $("scen").replaceChildren(Array.isArray(list) && list.length ? table([["Scenario", x => x.name], ["Description", x => s(x.description)], ["Cycles", x => s(x.cycles)]], list)
      : h("p", { class: "muted" }, "No scenarios returned."));
  }

  $("load").onclick = async () => {
    $("load").disabled = true;
    await run(["risk", "area", "readings"], "/status", renderStatus);   // sequential on purpose:
    await run(["alerts"], "/alerts", renderAlerts);                      // avoids parallel cold starts
    await run(["scen"], "/scenarios", renderScen);
    $("load").disabled = false;
  };
  $("more-btn").onclick = async () => {
    const box = $("more"); busy(["more"]);
    try {
      const hist = await get("/history"), ev = await get("/events");
      box.replaceChildren(h("h3", {}, "Decisions"), hist.length ? table([["Decision", d => d.decision_id], ["As of", d => s(d.as_of)],
        ["Change", d => s(d.previous_state) + " -> " + s(d.new_state)], ["Reason", d => s(d.reason)]], hist) : h("p", { class: "muted" }, "No decisions yet."),
        h("h3", {}, "Events"), ev.length ? table([["Event", e => e.event_id], ["Details", e => raw(e, "JSON")]], ev) : h("p", { class: "muted" }, "No events yet."));
    } catch (e) { fail(["more"], "/history or /events", e); }
    };

  $("load").click();
})();
