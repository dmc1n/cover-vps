import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyTheme, storedTheme } from "./theme";
import "./studio.css"; // the one stylesheet: tokens, light and dark (ADR-124)

applyTheme(storedTheme()); // before the first paint: no flash of the other theme

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
