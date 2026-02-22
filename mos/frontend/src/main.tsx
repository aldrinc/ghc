type DeployRuntimeConfig = {
  bundleMode?: boolean;
};

declare global {
  interface Window {
    __MOS_DEPLOY_RUNTIME__?: DeployRuntimeConfig;
  }
}

async function bootstrap() {
  const runtimeMode = Boolean(window.__MOS_DEPLOY_RUNTIME__?.bundleMode);
  if (runtimeMode) {
    const mod = await import("./runtimeBootstrap");
    mod.bootstrapRuntimeApp();
    return;
  }
  const mod = await import("./adminBootstrap");
  mod.bootstrapAdminApp();
}

void bootstrap();
