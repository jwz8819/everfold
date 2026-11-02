// Odyssey-2 Pro as a live renderer for the "World model view" panel.
// The API key stays on the game server: the browser asks /odyssey/credentials for a short-lived session token
// (Odyssey's client-credentials flow, documentation.api.odyssey.ml/client-credentials).
// Odyssey takes text only, and a stream lasts at most 150 seconds, so this re-opens the stream before the limit.
import { Odyssey, credentialsFromDict } from "https://esm.sh/@odysseyml/odyssey";

const STREAM_LIMIT_MS = 150_000;
const REOPEN_AT_MS = 140_000;

let client = null;
let startedAt = 0;
let lastPrompt = "";

async function openStream(prompt) {
  startedAt = Date.now();
  await client.startStream({ prompt, portrait: false });
}

window.WorldModelRenderers.register("odyssey", {
  label: "Odyssey-2 Pro (live)",
  async start(container, prompt) {
    const res = await fetch("/odyssey/credentials", { method: "POST" });
    if (!res.ok) throw new Error(res.status === 404 ? "Set ODYSSEY_API_KEY on the game server." : `credentials ${res.status}`);
    client = new Odyssey();
    const stream = await client.connectWithCredentials(credentialsFromDict(await res.json()));
    const video = document.createElement("video");
    Object.assign(video, { autoplay: true, playsInline: true, muted: true, srcObject: stream });
    container.innerHTML = "";
    container.appendChild(video);
    lastPrompt = prompt || "A quiet green meadow at the edge of a forest, stylized open-world adventure game.";
    await openStream(lastPrompt);
  },
  async update(prompt) {
    if (!client) return;
    lastPrompt = prompt;
    if (Date.now() - startedAt > REOPEN_AT_MS) {
      await client.endStream();
      await openStream(prompt);       // a fresh stream, seeded with the current view
    } else {
      await client.interact({ prompt });
    }
  },
  async stop() {
    if (!client) return;
    try { await client.endStream(); } catch {}
    client.disconnect();
    client = null;
  },
});

window.addEventListener("beforeunload", () => client && client.disconnect());
console.assert(REOPEN_AT_MS < STREAM_LIMIT_MS);
