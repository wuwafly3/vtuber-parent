import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./console/App";
import { PetApp } from "./pet/PetApp";

// Tauri 通过 URL 参数 ?mode=pet / ?mode=console 区分窗口模式。
// 纯浏览器开发时无参数, 默认走控制台。
const params = new URLSearchParams(window.location.search);
const mode = params.get("mode") || "console";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {mode === "pet" ? <PetApp /> : <App />}
  </StrictMode>
);
