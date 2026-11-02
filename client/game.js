(() => {
  const TILE = 22;
  const $ = (id) => document.getElementById(id);
  const canvas = $("map");
  const ctx = canvas.getContext("2d");

  const state = {
    ws: null, pid: null, chunkSize: 32, palette: null,
    chunks: new Map(),          // "cx,cy" -> {ground, feature, pois}
    me: null, players: [], npcs: [], tod: "day",
    drawn: new Map(),           // id -> {x, y} smoothed positions
    keys: new Set(), lastMove: "0,0",
    talkingTo: null, renderer: null, renderName: "",
  };

  // ---------------------------------------------------------------- join
  // The name is remembered per browser; the player id per tab, so two windows are two players.
  const store = (area, key, val) => { try { if (val === undefined) return area.getItem(key); area.setItem(key, val); } catch { return null; } };
  const saved = { name: store(localStorage, "everfold-name") || "", pid: store(sessionStorage, "everfold-pid") || undefined };
  $("join-name").value = saved.name || "";
  $("join-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const name = $("join-name").value.trim();
    if (!name) return;
    connect(name);
  });

  function connect(name) {
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
    state.ws = ws;
    ws.onopen = () => ws.send(JSON.stringify({ type: "join", name, pid: saved.pid }));
    ws.onmessage = (m) => handle(JSON.parse(m.data));
    ws.onclose = () => log("Disconnected from the world. Reload to rejoin.", "event big");
    store(localStorage, "everfold-name", name);
  }

  const send = (msg) => state.ws && state.ws.readyState === 1 && state.ws.send(JSON.stringify(msg));

  // -------------------------------------------------------------- messages
  function handle(msg) {
    switch (msg.type) {
      case "welcome":
        state.pid = msg.pid; state.chunkSize = msg.chunk; state.palette = msg.palette; state.me = msg.you;
        store(sessionStorage, "everfold-pid", msg.pid);
        $("join").hidden = true; $("app").hidden = false;
        resize(); renderInventory(msg.you.inventory); renderMe();
        break;
      case "chunk":
        state.chunks.set(`${msg.cx},${msg.cy}`, msg);
        break;
      case "tile": setTile(msg.x, msg.y, msg.code); break;
      case "snapshot":
        state.me = { ...state.me, ...msg.you }; state.players = msg.players; state.npcs = msg.npcs; state.tod = msg.time_of_day;
        renderMe(msg.weather);
        break;
      case "inventory": renderInventory(msg.inventory); break;
      case "quests": renderQuests(msg.quests); break;
      case "event": log(msg.event.text, ["shrine_open", "quest_done"].includes(msg.event.kind) ? "event big" : "event"); break;
      case "chat": log(`<b>${esc(msg.from)}</b> ${esc(msg.text)}`, "chat", true); break;
      case "thinking": showDialog(msg.npc, "…", true); break;
      case "say": showDialog(msg.npc, msg.text, false); break;
      case "offer": showOffer(msg.quest, msg.giver); break;
      case "view": onView(msg); break;
    }
  }

  function setTile(x, y, code) {
    const cs = state.chunkSize, cx = Math.floor(x / cs), cy = Math.floor(y / cs);
    const ch = state.chunks.get(`${cx},${cy}`);
    if (!ch) return;
    const i = (y - cy * cs) * cs + (x - cx * cs);
    ch.feature = ch.feature.slice(0, i) + code + ch.feature.slice(i + 1);
  }

  // ----------------------------------------------------------------- input
  const typing = () => ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName);
  window.addEventListener("keydown", (e) => {
    if (!state.pid) return;
    if (typing()) { if (e.key === "Escape") { document.activeElement.blur(); hideDialog(); } return; }
    const k = e.key.toLowerCase();
    if (["w", "a", "s", "d", "arrowup", "arrowdown", "arrowleft", "arrowright"].includes(k)) {
      const fresh = !state.keys.has(k);
      state.keys.add(k); e.preventDefault();
      if (fresh) state.renderer?.input?.([...state.keys], [k]);
    }
    else if (k === "e") send({ type: "interact" });
    else if (k === "f") send({ type: "campfire" });
    else if (k === "g") send({ type: "give" });
    else if (k === "t") { send({ type: "talk", text: "" }); e.preventDefault(); }
    else if (k === "y" && !$("offer").hidden) answerOffer(true);
    else if (k === "n" && !$("offer").hidden) answerOffer(false);
    else if (k === "enter") { $("chat-input").focus(); e.preventDefault(); }
    else if (k === "escape") hideDialog();
  });
  window.addEventListener("keyup", (e) => {
    if (state.keys.delete(e.key.toLowerCase())) state.renderer?.input?.([...state.keys], []);
  });
  window.addEventListener("blur", () => { state.keys.clear(); state.renderer?.input?.([], []); });

  setInterval(() => {
    const k = state.keys;
    const dx = (k.has("d") || k.has("arrowright") ? 1 : 0) - (k.has("a") || k.has("arrowleft") ? 1 : 0);
    const dy = (k.has("s") || k.has("arrowdown") ? 1 : 0) - (k.has("w") || k.has("arrowup") ? 1 : 0);
    const key = `${dx},${dy}`;
    if (key !== state.lastMove) { state.lastMove = key; send({ type: "move", dx, dy }); }
  }, 50);

  $("chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = $("chat-input").value.trim();
    if (t) send({ type: "chat", text: t });
    $("chat-input").value = ""; $("chat-input").blur();
  });
  $("talk-form").addEventListener("submit", (e) => {
    e.preventDefault();
    send({ type: "talk", npc: state.talkingTo, text: $("talk-input").value.trim() });
    $("talk-input").value = "";
  });
  $("offer-yes").addEventListener("click", () => answerOffer(true));
  $("offer-no").addEventListener("click", () => answerOffer(false));

  // --------------------------------------------------------------------- UI
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function log(html, cls, raw) {
    const li = document.createElement("li");
    li.className = cls;
    li.innerHTML = raw ? html : esc(html);
    $("log").appendChild(li);
    while ($("log").children.length > 60) $("log").firstChild.remove();
    li.scrollIntoView({ block: "end" });
  }

  function renderMe(weather) {
    if (!state.me) return;
    $("me").textContent = `${state.me.name} · ${state.tod}${weather ? " · " + weather : ""}`;
  }

  function renderInventory(inv) {
    const el = $("inventory");
    el.innerHTML = "";
    const entries = Object.entries(inv || {});
    if (!entries.length) { el.innerHTML = '<span class="muted">Empty pack. Press E next to bushes, trees and rocks.</span>'; return; }
    for (const [k, n] of entries) {
      const s = document.createElement("span");
      s.className = "chip"; s.textContent = `${k} × ${n}`;
      el.appendChild(s);
    }
  }

  function renderQuests(qs) {
    const el = $("quests");
    el.innerHTML = "";
    if (!qs.length) { el.innerHTML = '<li class="muted">Talk to villagers to find work.</li>'; return; }
    for (const q of qs) {
      const li = document.createElement("li");
      li.innerHTML = `<div class="qt">${esc(q.title)}</div>` +
        q.steps.map((s, i) => `<div class="qs ${i === q.step ? "now" : ""}">${i < q.step ? "✓ " : ""}${esc(s.text)}</div>`).join("");
      el.appendChild(li);
    }
  }

  function showDialog(npc, text, thinking) {
    if (!npc) { log(text, "event"); return; }
    state.talkingTo = npc.id;
    $("dialog").hidden = false;
    $("dialog-who").textContent = `${npc.name} · ${npc.role}`;
    $("dialog-text").textContent = thinking ? `${npc.name} is thinking…` : text;
    $("dialog-text").classList.toggle("thinking", !!thinking);
    if (!thinking) $("talk-input").focus();
  }
  function hideDialog() { $("dialog").hidden = true; state.talkingTo = null; }

  function showOffer(q, giver) {
    $("offer").hidden = false;
    $("offer-title").textContent = q.title;
    $("offer-summary").textContent = `${giver.name}: “${q.summary}”`;
    $("offer-steps").innerHTML = q.steps.map((s) => `<li>${esc(s.text)}</li>`).join("") +
      `<li class="muted">Reward: ${esc(Object.entries(q.reward).map(([k, n]) => `${k} × ${n}`).join(", "))}</li>`;
  }
  function answerOffer(yes) { send({ type: yes ? "accept" : "decline" }); $("offer").hidden = true; }

  // ------------------------------------------------------- world-model panel
  const sel = $("renderer");
  function listRenderers() {
    const keep = sel.value;
    sel.innerHTML = '<option value="">Prompt only</option>';
    for (const r of window.WorldModelRenderers.list()) {
      const o = document.createElement("option"); o.value = r.name; o.textContent = r.label; sel.appendChild(o);
    }
    sel.value = keep;
  }
  listRenderers();
  window.addEventListener("renderers-changed", listRenderers);
  sel.addEventListener("change", async () => {
    if (state.renderer) { try { await state.renderer.stop(); } catch (e) { console.error(e); } }
    state.renderer = window.WorldModelRenderers.get(sel.value) || null;
    state.renderName = sel.value;
    const frame = $("wm-frame");
    frame.innerHTML = state.renderer ? '<span class="muted">Starting…</span>'
      : '<span class="muted">No renderer connected. The prompt below is what a world model would receive.</span>';
    if (state.renderer) {
      try { await state.renderer.start(frame, $("wm-prompt").textContent); }
      catch (e) { frame.innerHTML = `<span class="muted">Renderer failed to start: ${esc(e.message || e)}</span>`; }
    }
  });
  async function onView(msg) {
    $("wm-prompt").textContent = msg.prompt;
    if (state.renderer && msg.changed) {
      try { await state.renderer.update(msg.prompt); } catch (e) { console.error(e); }
    }
  }

  // ----------------------------------------------------------------- render
  function resize() {
    const r = canvas.getBoundingClientRect();
    canvas.width = Math.max(200, Math.floor(r.width));
    canvas.height = Math.max(200, Math.floor(r.height));
  }
  window.addEventListener("resize", resize);

  const rgb = (c) => `rgb(${c[0]},${c[1]},${c[2]})`;
  const shade = (c, f) => `rgb(${Math.round(c[0] * f)},${Math.round(c[1] * f)},${Math.round(c[2] * f)})`;

  function smooth(id, x, y) {
    const d = state.drawn.get(id);
    if (!d) { state.drawn.set(id, { x, y }); return { x, y }; }
    d.x += (x - d.x) * 0.35; d.y += (y - d.y) * 0.35;
    if (Math.hypot(x - d.x, y - d.y) > 6) { d.x = x; d.y = y; }
    return d;
  }

  function drawTile(ch, lx, ly, sx, sy, t) {
    const pal = state.palette, i = ly * state.chunkSize + lx;
    const g = pal.ground[ch.ground[i]];
    ctx.fillStyle = rgb(g.color);
    ctx.fillRect(sx, sy, TILE + 1, TILE + 1);
    const code = ch.feature[i];
    if (code === "." || !code) return;
    const f = pal.feature[code];
    if (!f) return;
    const c = TILE / 2;
    ctx.fillStyle = rgb(f.color);
    if ("tp".includes(code)) {
      ctx.beginPath(); ctx.arc(sx + c, sy + c, TILE * 0.45, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = shade(f.color, 0.75);
      ctx.beginPath(); ctx.arc(sx + c + 2, sy + c + 2, TILE * 0.25, 0, Math.PI * 2); ctx.fill();
    } else if ("hsw".includes(code)) {
      ctx.fillRect(sx + 1, sy + 1, TILE - 2, TILE - 2);
      ctx.fillStyle = shade(f.color, 0.7); ctx.fillRect(sx + 1, sy + 1, TILE - 2, 5);
    } else if (code === "T") {
      ctx.fillRect(sx + 3, sy - TILE * 1.2, TILE - 6, TILE * 2.2);
      ctx.fillStyle = `rgba(90,180,255,${0.6 + 0.4 * Math.sin(t / 300)})`;
      ctx.beginPath(); ctx.arc(sx + c, sy - TILE * 1.25, 6, 0, Math.PI * 2); ctx.fill();
    } else if (code === "C") {
      ctx.fillStyle = `rgba(255,${120 + Math.floor(60 * Math.sin(t / 90))},40,0.95)`;
      ctx.beginPath(); ctx.arc(sx + c, sy + c, TILE * 0.35, 0, Math.PI * 2); ctx.fill();
    } else if (code === "o") {
      ctx.strokeStyle = rgb(f.color); ctx.lineWidth = 3; ctx.strokeRect(sx + 4, sy + 4, TILE - 8, TILE - 8);
    } else if (code === "O") {
      ctx.fillStyle = `rgba(170,240,255,${0.7 + 0.3 * Math.sin(t / 200)})`;
      ctx.beginPath(); ctx.arc(sx + c, sy + c - 3 * Math.sin(t / 400), TILE * 0.35, 0, Math.PI * 2); ctx.fill();
    } else if (f.blocks) {
      ctx.beginPath(); ctx.roundRect(sx + 3, sy + 3, TILE - 6, TILE - 6, 4); ctx.fill();
    } else {
      ctx.beginPath(); ctx.arc(sx + c, sy + c, TILE * 0.2, 0, Math.PI * 2); ctx.fill();
    }
  }

  function drawPerson(x, y, color, label, isMe) {
    ctx.fillStyle = "rgba(0,0,0,0.25)";
    ctx.beginPath(); ctx.ellipse(x, y + 8, 8, 3, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = color; ctx.strokeStyle = "#111"; ctx.lineWidth = isMe ? 2.5 : 1.5;
    ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.font = "600 12px -apple-system, sans-serif"; ctx.textAlign = "center";
    ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,0.6)"; ctx.strokeText(label, x, y - 13);
    ctx.fillStyle = "#fff"; ctx.fillText(label, x, y - 13);
  }

  function frame(t) {
    requestAnimationFrame(frame);
    if (!state.me || !state.palette) return;
    const me = smooth(state.pid, state.me.x, state.me.y);
    const W = canvas.width, H = canvas.height, cs = state.chunkSize;
    const ox = W / 2 - me.x * TILE, oy = H / 2 - me.y * TILE;
    ctx.fillStyle = "#14181a"; ctx.fillRect(0, 0, W, H);
    const x0 = Math.floor(-ox / TILE) - 1, y0 = Math.floor(-oy / TILE) - 1;
    const x1 = x0 + Math.ceil(W / TILE) + 2, y1 = y0 + Math.ceil(H / TILE) + 3;
    for (let y = y0; y <= y1; y++) {
      for (let x = x0; x <= x1; x++) {
        const cx = Math.floor(x / cs), cy = Math.floor(y / cs);
        const ch = state.chunks.get(`${cx},${cy}`);
        if (!ch) continue;
        drawTile(ch, x - cx * cs, y - cy * cs, Math.floor(ox + x * TILE), Math.floor(oy + y * TILE), t);
      }
    }
    for (const ch of state.chunks.values()) {
      for (const p of ch.pois) {
        const sx = ox + (p.x + 0.5) * TILE, sy = oy + (p.y + 0.5) * TILE;
        if (sx < -200 || sy < -200 || sx > W + 200 || sy > H + 200) continue;
        ctx.font = "italic 600 13px Georgia, serif"; ctx.textAlign = "center";
        ctx.lineWidth = 4; ctx.strokeStyle = "rgba(255,255,255,0.75)";
        const name = `${p.name}${p.kind === "shrine" ? (p.state?.solved ? " shrine (open)" : " shrine") : ""}`;
        ctx.strokeText(name, sx, sy + TILE * (p.kind === "tower" ? -2.4 : 2.2));
        ctx.fillStyle = "#2b2a26"; ctx.fillText(name, sx, sy + TILE * (p.kind === "tower" ? -2.4 : 2.2));
      }
    }
    for (const n of state.npcs) {
      const d = smooth(n.id, n.x, n.y);
      drawPerson(ox + d.x * TILE, oy + d.y * TILE, "#f2d36b", n.name, false);
    }
    for (const p of state.players) {
      const d = smooth(p.id, p.x, p.y);
      drawPerson(ox + d.x * TILE, oy + d.y * TILE, "#e0665a", p.name, false);
    }
    drawPerson(W / 2, H / 2, "#ffffff", state.me.name, true);
    const night = { dawn: 0.12, day: 0, dusk: 0.18, night: 0.42 }[state.tod] || 0;
    if (night) { ctx.fillStyle = `rgba(16,22,60,${night})`; ctx.fillRect(0, 0, W, H); }
  }
  requestAnimationFrame(frame);
})();
