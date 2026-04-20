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

async function bootstrap() {
  if (redirectUnsupportedLocalOrigin()) {
    return;
  }
  const runtimeMode = Boolean(window.__MOS_DEPLOY_RUNTIME__?.bundleMode);
  if (runtimeMode) {
    const { bootstrapRuntimeApp } = await import("./runtimeBootstrap");
    bootstrapRuntimeApp();
    return;
  }
  const { bootstrapAdminApp } = await import("./adminBootstrap");
  bootstrapAdminApp();
}

void bootstrap();
