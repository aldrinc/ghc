export type DesignSystemTokens = {
  cssVars?: Record<string, string | number>;
  dataTheme?: string;
  fontUrls?: string[];
  fontCss?: string;
  [key: string]: unknown;
};

export type DesignSystem = {
  id: string;
  org_id: string;
  client_id?: string | null;
  name: string;
  tokens: DesignSystemTokens | Record<string, unknown>;
  created_at: string;
  updated_at: string;
};
