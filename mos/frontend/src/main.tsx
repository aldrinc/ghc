type DeployRuntimeConfig = {
  bundleMode?: boolean;
};

declare global {
  interface Window {
    __MOS_DEPLOY_RUNTIME__?: DeployRuntimeConfig;
  }
}

function redirectUnsupportedLocalOrigin() {
  if (typeof window === "undefined") return false;
  const { hostname, protocol, port, pathname, search, hash } = window.location;
  if (hostname !== "127.0.0.1" && hostname !== "0.0.0.0") {
    return false;
  }
  const target = `${protocol}//localhost${port ? `:${port}` : ""}${pathname}${search}${hash}`;
  window.location.replace(target);
  return true;
}

async function loadBootstrapModule(
  kind: "admin" | "runtime"
): Promise<
  | { bootstrapAdminApp: () => void }
  | { bootstrapRuntimeApp: () => void }
> {
  if (kind === "runtime") {
    return import("./runtimeBootstrap");
  }
  return import("./adminBootstrap");
}

async function bootstrap() {
  if (redirectUnsupportedLocalOrigin()) {
    return;
  }
  const runtimeMode = Boolean(window.__MOS_DEPLOY_RUNTIME__?.bundleMode);
  if (runtimeMode) {
    const mod = await loadBootstrapModule("runtime");
    mod.bootstrapRuntimeApp();
    return;
  }
  const mod = await loadBootstrapModule("admin");
  mod.bootstrapAdminApp();
}

void bootstrap();
