import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
  plugins: [react(), tsconfigPaths()],
  server: {
    port: 5275,
    allowedHosts: ["alba-unintermittent-overnormally.ngrok-free.dev"],
  },
});
