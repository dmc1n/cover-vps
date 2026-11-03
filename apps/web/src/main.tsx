import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyTheme, storedTheme } from "./theme";
import { installTouchTips } from "./touchTips";
import "./studio.css"; // the one stylesheet: tokens, light and dark (ADR-124)

applyTheme(storedTheme()); // before the first paint: no flash of the other theme
installTouchTips(); // a title= shows on a long press too (a finger has no hover, ADR-154)

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
