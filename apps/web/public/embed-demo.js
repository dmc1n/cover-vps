// The dealer embed's demo page (ADR-150): what a dealer's own script hears. The component's
// CustomEvents bubble out of its shadow root; the frame posts the same as messages.
const log = document.getElementById("log");
const TYPES = [
  "s2dio:ready",
  "s2dio:priced",
  "s2dio:checkout-started",
  "s2dio:order-sent",
  "s2dio:added-to-cart",
  "s2dio:error",
];

function line(from, type, detail) {
  const li = document.createElement("li");
  li.textContent = `${new Date().toLocaleTimeString()} ${from} ${type} ${JSON.stringify(detail)}`;
  log.prepend(li);
}

for (const type of TYPES)
  document.addEventListener(type, (e) => {
    const dealer = e.target.getAttribute ? e.target.getAttribute("dealer") : "";
    line(dealer, type, e.detail);
  });

window.addEventListener("message", (e) => {
  if (e.origin !== location.origin || !e.data || e.data.source !== "s2dio-configurator") return;
  line("frame", e.data.type, e.data.detail);
});
