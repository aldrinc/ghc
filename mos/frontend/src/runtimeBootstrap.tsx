import React from "react";
import ReactDOM from "react-dom/client";
import RuntimeApp from "./RuntimeApp";
import "./runtime.css";

export function bootstrapRuntimeApp() {
  const root = document.getElementById("root");
  if (!root) {
    throw new Error("Root element #root was not found.");
  }

  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <RuntimeApp />
    </React.StrictMode>
  );
}
