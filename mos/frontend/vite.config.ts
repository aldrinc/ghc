import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  optimizeDeps: {
    // These entrypoints are loaded through a runtime branch in src/main.tsx, so
    // tell Vite to pre-scan them instead of discovering them only on-demand.
    entries: ["index.html", "src/adminBootstrap.tsx", "src/runtimeBootstrap.tsx"],
  },
  server: {
    port: 5173,
    allowedHosts: ["moshq.app", "www.moshq.app"],
    warmup: {
      clientFiles: ["./src/main.tsx", "./src/adminBootstrap.tsx", "./src/runtimeBootstrap.tsx"],
    },
  },
});
