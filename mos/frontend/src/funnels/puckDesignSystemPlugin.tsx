import type { Plugin } from "@measured/puck";
import { DesignSystemProvider } from "@/components/design-system/DesignSystemProvider";
import type { DesignSystemTokens } from "@/types/designSystems";

type PuckDesignSystemPluginOptions = {
  tokens?: DesignSystemTokens | Record<string, unknown> | null;
};

export function createDesignSystemPlugin({ tokens }: PuckDesignSystemPluginOptions): Plugin {
  return {
    overrides: {
      iframe: ({ children }) => <DesignSystemProvider tokens={tokens}>{children}</DesignSystemProvider>,
      preview: ({ children }) => <DesignSystemProvider tokens={tokens}>{children}</DesignSystemProvider>,
    },
  };
}
