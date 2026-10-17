import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ToastProvider } from "../shared/toast";
import { App } from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ToastProvider>
      <App />
    </ToastProvider>
  </StrictMode>,
);
