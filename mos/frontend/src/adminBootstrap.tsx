import React from "react";
import ReactDOM from "react-dom/client";
import { ClerkProvider } from "@clerk/clerk-react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui/toast";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { queryClient } from "@/lib/queryClient";
import App from "./App";
import "./index.css";
import "@measured/puck/puck.css";

function getClerkPublishableKey() {
  const clerkKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY?.trim();
  if (!clerkKey) {
    throw new Error("VITE_CLERK_PUBLISHABLE_KEY is required to bootstrap the admin app.");
  }
  if (clerkKey === "pk_test_placeholder") {
    throw new Error("VITE_CLERK_PUBLISHABLE_KEY is set to the placeholder value.");
  }
  return clerkKey;
}

export function bootstrapAdminApp() {
  const root = document.getElementById("root");
  if (!root) {
    throw new Error("Root element #root was not found.");
  }
  const clerkKey = getClerkPublishableKey();

  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <ThemeProvider>
        <ClerkProvider publishableKey={clerkKey}>
          <QueryClientProvider client={queryClient}>
            <ToastProvider>
              <App />
            </ToastProvider>
          </QueryClientProvider>
        </ClerkProvider>
      </ThemeProvider>
    </React.StrictMode>
  );
}
