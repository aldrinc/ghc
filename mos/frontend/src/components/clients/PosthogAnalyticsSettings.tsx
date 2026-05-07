import { useEffect, useState } from "react";

import {
  useClientPosthogSettings,
  useParseClientPosthogSnippet,
  useUpdateClientPosthogSettings,
} from "@/api/clients";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { ClientPosthogSettings, ClientPosthogSourceMode } from "@/types/common";

const PERSON_PROFILE_OPTIONS = [
  { label: "Identified only", value: "identified_only" },
  { label: "Always", value: "always" },
];

const SOURCE_MODE_OPTIONS = [
  { label: "Structured", value: "structured" },
  { label: "Snippet", value: "snippet" },
];

function getErrorMessage(error: unknown) {
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && "message" in error) {
    return String((error as { message?: unknown }).message || "Request failed");
  }
  return "Request failed";
}

function prettyJson(value: unknown) {
  return JSON.stringify(value ?? null, null, 2);
}

function applySettingsToForm(
  settings: ClientPosthogSettings,
  setters: {
    setEnabled: (value: boolean) => void;
    setProjectApiKey: (value: string) => void;
    setApiHost: (value: string) => void;
    setUiHost: (value: string) => void;
    setDefaultsValue: (value: string) => void;
    setPersonProfiles: (value: "identified_only" | "always") => void;
    setSourceMode: (value: ClientPosthogSourceMode) => void;
    setSourceSnippet: (value: string) => void;
    setRuntimePreview: (value: Record<string, unknown> | null) => void;
  },
) {
  setters.setEnabled(Boolean(settings.enabled));
  setters.setProjectApiKey(settings.projectApiKey || "");
  setters.setApiHost(settings.apiHost || "");
  setters.setUiHost(settings.uiHost || "");
  setters.setDefaultsValue(settings.defaults || "2026-01-30");
  setters.setPersonProfiles(settings.personProfiles || "identified_only");
  setters.setSourceMode(settings.sourceMode || "structured");
  setters.setSourceSnippet(settings.sourceSnippet || "");
  setters.setRuntimePreview((settings.resolvedTracking as Record<string, unknown> | null | undefined) || null);
}

export function PosthogAnalyticsSettings({ clientId }: { clientId: string }) {
  const { data: settings, error: settingsError } = useClientPosthogSettings(clientId);
  const saveSettings = useUpdateClientPosthogSettings(clientId);
  const parseSnippet = useParseClientPosthogSnippet(clientId);

  const [enabled, setEnabled] = useState(false);
  const [projectApiKey, setProjectApiKey] = useState("");
  const [apiHost, setApiHost] = useState("");
  const [uiHost, setUiHost] = useState("");
  const [defaultsValue, setDefaultsValue] = useState("2026-01-30");
  const [personProfiles, setPersonProfiles] = useState<"identified_only" | "always">("identified_only");
  const [sourceMode, setSourceMode] = useState<ClientPosthogSourceMode>("structured");
  const [sourceSnippet, setSourceSnippet] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [runtimePreview, setRuntimePreview] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (!settings) return;
    applySettingsToForm(settings, {
      setEnabled,
      setProjectApiKey,
      setApiHost,
      setUiHost,
      setDefaultsValue,
      setPersonProfiles,
      setSourceMode,
      setSourceSnippet,
      setRuntimePreview,
    });
  }, [settings?.updatedAt, settings?.hasSettings]);

  const handleParseSnippet = async () => {
    try {
      setParseError(null);
      const parsed = await parseSnippet.mutateAsync({ snippet: sourceSnippet });
      applySettingsToForm(parsed, {
        setEnabled,
        setProjectApiKey,
        setApiHost,
        setUiHost,
        setDefaultsValue,
        setPersonProfiles,
        setSourceMode,
        setSourceSnippet,
        setRuntimePreview,
      });
    } catch (error) {
      setParseError(getErrorMessage(error));
    }
  };

  const handleSave = async () => {
    try {
      setFormError(null);
      const saved = await saveSettings.mutateAsync({
        enabled,
        projectApiKey: projectApiKey || null,
        apiHost: apiHost || null,
        uiHost: uiHost || null,
        defaults: defaultsValue || null,
        personProfiles,
        sourceMode,
        sourceSnippet: sourceSnippet || null,
      });
      applySettingsToForm(saved, {
        setEnabled,
        setProjectApiKey,
        setApiHost,
        setUiHost,
        setDefaultsValue,
        setPersonProfiles,
        setSourceMode,
        setSourceSnippet,
        setRuntimePreview,
      });
    } catch (error) {
      setFormError(getErrorMessage(error));
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-content">Workspace analytics</div>
            <div className="text-sm text-content-muted">
              Manage the workspace-owned PostHog config used for published funnels and standalone deployments.
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone={enabled ? "success" : settings?.hasSettings ? "warning" : "neutral"}>
              {enabled ? "Enabled" : settings?.hasSettings ? "Saved but disabled" : "Not configured"}
            </Badge>
            <Button onClick={() => void handleSave()} disabled={saveSettings.isPending}>
              Save
            </Button>
          </div>
        </div>

        <div className="mt-4 rounded-lg border border-border bg-surface-2 p-3">
          <label className="flex items-start gap-3 text-sm text-content">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
              className="mt-1"
            />
            <span>
              <span className="block font-medium">Enable PostHog on published runtime</span>
              <span className="block text-xs text-content-muted">
                Preview pages stay analytics-free. Published public funnels and standalone imported HTML deployments use the resolved config below.
              </span>
            </span>
          </label>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="font-medium text-content">Input mode</span>
            <Select value={sourceMode} onValueChange={(value) => setSourceMode(value as ClientPosthogSourceMode)} options={SOURCE_MODE_OPTIONS} />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-content">Person profiles</span>
            <Select value={personProfiles} onValueChange={(value) => setPersonProfiles(value as "identified_only" | "always")} options={PERSON_PROFILE_OPTIONS} />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-content">Project API key</span>
            <Input value={projectApiKey} onChange={(event) => setProjectApiKey(event.target.value)} placeholder="gPFG-..." spellCheck={false} />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-content">Defaults</span>
            <Input value={defaultsValue} onChange={(event) => setDefaultsValue(event.target.value)} placeholder="2026-01-30" spellCheck={false} />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-content">API host</span>
            <Input value={apiHost} onChange={(event) => setApiHost(event.target.value)} placeholder="https://emb.shopemberco.com" spellCheck={false} />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium text-content">UI host</span>
            <Input value={uiHost} onChange={(event) => setUiHost(event.target.value)} placeholder="https://us.posthog.com" spellCheck={false} />
          </label>
        </div>

        <div className="mt-4 rounded-lg border border-border bg-surface-2 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium text-content">Import PostHog snippet</div>
              <div className="text-xs text-content-muted">
                Paste a `posthog.init(...)` snippet to populate the canonical workspace fields and preserve the raw snippet for re-editing.
              </div>
            </div>
            <Button variant="secondary" onClick={() => void handleParseSnippet()} disabled={!sourceSnippet.trim() || parseSnippet.isPending}>
              Parse snippet
            </Button>
          </div>
          <Textarea
            value={sourceSnippet}
            onChange={(event) => setSourceSnippet(event.target.value)}
            className="mt-3 min-h-[220px] font-mono text-xs"
            placeholder="<script>posthog.init(...)</script>"
            spellCheck={false}
          />
          {parseError ? (
            <Callout variant="danger" size="sm" className="mt-3" title="Snippet parse failed">
              {parseError}
            </Callout>
          ) : null}
        </div>

        <div className="mt-4 rounded-lg border border-border bg-surface-2 p-4">
          <div className="text-sm font-medium text-content">Resolved runtime preview</div>
          <div className="mt-1 text-xs text-content-muted">
            This is the exact PostHog payload the public runtime and standalone artifact builder consume.
          </div>
          <pre className="mt-3 overflow-x-auto rounded-lg border border-border bg-background/60 p-3 text-xs text-content">
            {prettyJson(runtimePreview)}
          </pre>
        </div>

        {settings?.updatedAt ? (
          <div className="mt-3 text-xs text-content-muted">
            Last updated {new Date(settings.updatedAt).toLocaleString()}
          </div>
        ) : null}
        {settingsError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Failed to load analytics settings">
            {getErrorMessage(settingsError)}
          </Callout>
        ) : null}
        {formError ? (
          <Callout variant="danger" size="sm" className="mt-3" title="Failed to save analytics settings">
            {formError}
          </Callout>
        ) : null}
        <Callout variant="info" size="sm" className="mt-3" title="Preview behavior">
          MOS keeps preview/editor routes free of PostHog so internal review traffic does not pollute production analytics.
        </Callout>
      </div>
    </div>
  );
}
