// World-model renderers plug in here. Each one receives the compiled frame prompt for this player
// every few seconds and draws into the panel. The game itself never depends on a renderer.
//
//   WorldModelRenderers.register("name", {
//     label: "Shown in the dropdown",
//     async start(container, prompt) {},   // open a session, mount a <video> or <img>
//     async update(prompt) {},             // steer the running session with a new prompt
//     async stop() {},                     // close the session and free the GPU
//     input(held, pressed) {},             // optional: keys held now and keys newly pressed, for action-driven models
//   });
window.WorldModelRenderers = (() => {
  const registry = {};
  return {
    register(name, impl) {
      registry[name] = impl;
      window.dispatchEvent(new CustomEvent("renderers-changed"));
    },
    get(name) { return registry[name]; },
    list() { return Object.entries(registry).map(([name, r]) => ({ name, label: r.label || name })); },
  };
})();
