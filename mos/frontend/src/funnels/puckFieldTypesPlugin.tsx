import type { Plugin } from "@measured/puck";

export function createPuckFieldTypesPlugin(): Plugin {
  // The editor currently uses Puck's built-in field types only.
  // Keep this plugin entrypoint stable so editor pages can compose plugins
  // without depending on a missing module.
  return {};
}
