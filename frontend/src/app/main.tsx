import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@xyflow/react/dist/style.css";

import { ErrorBoundary } from "../components/common/ErrorBoundary";
import { App } from "./App";
import "../theme/tokens.css";
import "./app.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("缺少 #root 挂载点");
}

createRoot(rootElement).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);
