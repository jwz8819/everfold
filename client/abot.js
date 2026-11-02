// ABot-World-0 (Alibaba AMAP) on fal.ai as a live renderer for the "World model view" panel.
//
// This model keeps its own world: it takes movement and camera commands plus a text prompt, not the game state.
// Everfold steers it two ways: your WASD and arrow keys become its movement commands, and the server's view prompt
// for your camera becomes its scene description. How far its world drifts from the true one is what we measure.
//
// Session contract: https://fal.ai/models/fal-ai/abot-world-0/start-session/llms.txt
// The browser never sees FAL_KEY: the client talks to /api/fal/proxy on the game server, which adds it.
import { createFalClient } from "https://esm.sh/@fal-ai/client@1.11.0-alpha.6";
import { wma } from "https://esm.sh/@fal-ai/client@1.11.0-alpha.6/realtime";

const APP = "fal-ai/abot-world-0";
const MAX_PROMPT = 2000;
// ABot holds its camera and character steadier when told how to frame them (from fal's own example prompt).
const FRAMING = " Third-person follow camera directly behind the character, whole body visible at lower centre, " +
  "facing away along an open route. Keep the same character visible and recognizable in every future view. " +
  "Move smoothly with the character; stable upright horizon, no cuts, no first-person view. " +
  "Wide open walkable ground to the horizon, obstacles and other people beside the path.";

const KEYMAP = {
  w: "forward", arrowup: "forward", s: "backward", arrowdown: "backward",
  a: "left", d: "right", arrowleft: "look_left", arrowright: "look_right",
};

const fal = createFalClient({ proxyUrl: "/api/fal/proxy" });

let session = null;
let video = null;
let statusEl = null;
let latestPrompt = "";
let awaitingAck = false;      // ABot applies one world update at a time
let queuedPrompt = null;
let firstFrame = false;
let stopped = true;

const shape = (p) => (p + FRAMING).slice(0, MAX_PROMPT);
const status = (text) => { if (statusEl) statusEl.textContent = text; };

function sendUpdate(message) {
  awaitingAck = true;
  session.send(message);
}

function onData(raw) {
  let msg;
  try { msg = typeof raw === "string" ? JSON.parse(raw) : raw; } catch { return; }
  switch (msg.type) {
    case "session_info":
      status(`ABot · ${msg.resolution?.width}×${msg.resolution?.height} · ${msg.frames_per_second} fps target`);
      break;
    case "configured": case "prompt_applied": case "reset_applied":
      awaitingAck = false;
      if (queuedPrompt) { const p = queuedPrompt; queuedPrompt = null; sendUpdate({ type: "prompt", prompt: shape(p) }); }
      break;
    case "stats":
      status(`ABot · generating ${msg.generation_fps?.toFixed?.(1) ?? "?"} fps · queue ${msg.queue_depth}`);
      break;
    case "error":
      console.warn("ABot:", msg.error);
      awaitingAck = false;
      break;
    case "stream_exhausted":
      status("ABot session ended. Opening a new one…");
      if (!stopped) open(latestPrompt);       // a fresh session seeded with the current view
      break;
  }
}

function open(prompt) {
  awaitingAck = false; queuedPrompt = null; firstFrame = false;
  session = fal.realtime.open(wma(APP), {
    receive: ["video"],
    onMedia: (stream) => {
      video.srcObject = stream;
      video.onloadeddata = () => { firstFrame = true; };
    },
    onData,
    onState: (s) => { if (s === "failed") status("ABot connection failed. Check FAL_KEY and credits."); },
    onError: (e) => { console.error(e); status(`ABot error: ${e?.message || e}`); },
  });
  // configure is optional, once per session; it replaces the default world with ours
  sendUpdate({ type: "configure", prompt: shape(prompt) });
}

window.WorldModelRenderers.register("abot", {
  label: "ABot-World-0 via fal (live)",
  async start(container, prompt) {
    stopped = false;
    container.innerHTML = "";
    video = Object.assign(document.createElement("video"), { autoplay: true, playsInline: true, muted: true });
    statusEl = Object.assign(document.createElement("div"), { className: "wm-status", textContent: "Connecting to ABot…" });
    container.append(video, statusEl);
    latestPrompt = prompt || "A sunlit meadow beside a small timber village, stylized open-world adventure game.";
    open(latestPrompt);
  },
  async update(prompt) {
    latestPrompt = prompt;
    if (!session) return;
    if (awaitingAck) queuedPrompt = prompt;   // keep only the newest view
    else sendUpdate({ type: "prompt", prompt: shape(prompt) });
  },
  input(held, pressed) {
    if (!session || !firstFrame) return;      // the model ignores movement before its first frame
    const pick = (keys) => [...new Set(keys.map((k) => KEYMAP[k]).filter(Boolean))].slice(0, 8);
    session.send({ type: "commands", active: pick(held), activated: pick(pressed) });
  },
  async stop() {
    stopped = true;
    if (!session) return;
    try { session.send({ type: "stop" }); } catch {}
    await session.close();
    session = null;
  },
});

window.addEventListener("beforeunload", () => { stopped = true; session?.close(); });
