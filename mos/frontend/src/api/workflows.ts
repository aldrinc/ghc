import { useAuth } from "@clerk/clerk-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useApiClient, type ApiError } from "@/api/client";
import type {
  ActivityLog,
  ResearchArtifactRef,
  StrategyV2LaunchRecord,
  WorkflowDetail,
  WorkflowRun,
} from "@/types/common";
import type { AssetBriefType } from "@/lib/assetBriefTypes";
import { resolveRequiredApiBaseUrl } from "@/lib/apiBaseUrl";
import { toast } from "@/components/ui/toast";

const defaultBaseUrl = resolveRequiredApiBaseUrl();
const clerkTokenTemplate = import.meta.env.VITE_CLERK_JWT_TEMPLATE || "backend";

type WorkflowFilters = {
  clientId?: string;
  productId?: string;
  campaignId?: string;
};

type WorkflowQueryOptions = {
  enabled?: boolean;
};

function parseFilenameFromContentDisposition(contentDisposition: string | null): string | null {
  if (!contentDisposition) return null;
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const quotedMatch = contentDisposition.match(/filename=\"([^\"]+)\"/i);
  if (quotedMatch?.[1]) return quotedMatch[1];
  const bareMatch = contentDisposition.match(/filename=([^;]+)/i);
  return bareMatch?.[1]?.trim() || null;
}

function isZipContentType(contentType: string | null): boolean {
  if (!contentType) return false;
  return contentType.toLowerCase().includes("application/zip");
}

async function parseDownloadError(resp: Response): Promise<Error> {
  try {
    const raw = await resp.clone().json();
    const detail = (raw as { detail?: unknown })?.detail;
    if (typeof detail === "string" && detail.trim()) return new Error(detail);
    const message = (raw as { message?: unknown })?.message;
    if (typeof message === "string" && message.trim()) return new Error(message);
  } catch {
    // Fall through to text parsing.
  }
  const text = (await resp.text()).trim();
  if (text) return new Error(text);
  return new Error(resp.statusText || "Failed to download workflow research ZIP");
}

export function useWorkflows(filters?: WorkflowFilters, options?: WorkflowQueryOptions) {
  const { get } = useApiClient();
  const path = (() => {
    if (!filters) return "/workflows";
    const params = new URLSearchParams();
    if (filters.clientId) params.set("clientId", filters.clientId);
    if (filters.productId) params.set("productId", filters.productId);
    if (filters.campaignId) params.set("campaignId", filters.campaignId);
    const qs = params.toString();
    return qs ? `/workflows?${qs}` : "/workflows";
  })();
  return useQuery<WorkflowRun[]>({
    queryKey: ["workflows", filters?.clientId ?? null, filters?.productId ?? null, filters?.campaignId ?? null],
    queryFn: () => get(path),
    enabled: options?.enabled ?? true,
  });
}

export function useWorkflowLogs(workflowId?: string) {
  const { get } = useApiClient();
  return useQuery<ActivityLog[]>({
    queryKey: ["workflows", workflowId, "logs"],
    queryFn: () => get(`/workflows/${workflowId}/logs`),
    enabled: Boolean(workflowId),
  });
}

export function useWorkflowDetail(workflowId?: string) {
  const { get } = useApiClient();
  return useQuery<WorkflowDetail>({
    queryKey: ["workflows", workflowId, "detail"],
    queryFn: () => get(`/workflows/${workflowId}`),
    enabled: Boolean(workflowId),
  });
}

export type WorkflowResearchArtifact = ResearchArtifactRef & { content: unknown };

export function normalizeMarkdownContent(title: string, value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "";
  if (typeof value !== "object") return String(value);

  const asRecord = value as Record<string, unknown>;
  const directContent = asRecord.content;
  if (typeof directContent === "string" && directContent.trim()) return directContent;

  const directMarkdown = asRecord.markdown;
  if (typeof directMarkdown === "string" && directMarkdown.trim()) return directMarkdown;

  const payload = asRecord.payload;
  if (payload && typeof payload === "object") {
    const payloadRecord = payload as Record<string, unknown>;
    const payloadContent = payloadRecord.content;
    if (typeof payloadContent === "string" && payloadContent.trim()) return payloadContent;
    const payloadMarkdown = payloadRecord.markdown;
    if (typeof payloadMarkdown === "string" && payloadMarkdown.trim()) return payloadMarkdown;
  }

  let body = "";
  try {
    body = JSON.stringify(value, null, 2) || "null";
  } catch {
    body = String(value);
  }
  const heading = title.trim() ? `# ${title.trim()}\n\n` : "";
  return `${heading}\`\`\`json\n${body}\n\`\`\`\n`;
}

function sanitizeFilename(name: string): string {
  return (
    name
      .trim()
      .replace(/[<>:"/\\|?*]+/g, "")
      .replace(/\s+/g, "-")
      .toLowerCase()
      .slice(0, 80) || "document"
  );
}

function parseFilenameFromContentDisposition(contentDisposition: string | null): string | null {
  if (!contentDisposition) return null;
  const filenameMatch = contentDisposition.match(/filename\*?=(?:UTF-8''|")?([^\";]+)/i);
  if (!filenameMatch?.[1]) return null;
  try {
    return decodeURIComponent(filenameMatch[1].trim().replace(/^\"|\"$/g, ""));
  } catch {
    return filenameMatch[1].trim().replace(/^\"|\"$/g, "");
  }
}

function isZipContentType(contentType: string | null): boolean {
  if (!contentType) return false;
  const normalized = contentType.toLowerCase();
  return (
    normalized.includes("application/zip") ||
    normalized.includes("application/x-zip-compressed") ||
    normalized.includes("application/octet-stream")
  );
}

async function parseDownloadError(resp: Response): Promise<Error> {
  try {
    const raw = await resp.clone().json();
    const detail = (raw as { detail?: unknown })?.detail;
    if (typeof detail === "string" && detail.trim()) return new Error(detail);
    const message = (raw as { message?: unknown })?.message;
    if (typeof message === "string" && message.trim()) return new Error(message);
  } catch {
    // Fall through to text parsing.
  }
  const text = (await resp.text()).trim();
  if (text) return new Error(text);
  return new Error(resp.statusText || "Failed to download research archive");
}

export function useDownloadResearchMarkdown() {
  const { get } = useApiClient();

  return useMutation({
    mutationFn: async ({ workflowId, stepKey, title }: { workflowId: string; stepKey: string; title?: string }) => {
      const artifact = await get<WorkflowResearchArtifact>(`/workflows/${workflowId}/research/${stepKey}`);
      const content = normalizeMarkdownContent(artifact.title || stepKey, artifact.content);
      if (!content.trim()) {
        throw new Error("No content available to download.");
      }
      const filename = sanitizeFilename(title || artifact.title || stepKey) + ".md";
      const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      return filename;
    },
    onSuccess: (filename: string) => {
      toast.success(`Downloaded ${filename}`);
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to download document";
      toast.error(message);
    },
  });
}

export function useDownloadResearchMarkdownArchive() {
  const { getToken } = useAuth();

  return useMutation({
    mutationFn: async ({ workflowId }: { workflowId: string }) => {
      if (!workflowId?.trim()) throw new Error("Workflow ID is required.");
      const token = await getToken({ template: clerkTokenTemplate });
      const headers = new Headers();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      const response = await fetch(`${defaultBaseUrl}/workflows/${workflowId}/research/download-all`, {
        method: "GET",
        headers,
      });
      if (!response.ok) {
        throw await parseDownloadError(response);
      }
      const responseContentType = response.headers.get("Content-Type");
      if (!isZipContentType(responseContentType)) {
        const preview = (await response.text()).trim().slice(0, 240);
        const contentTypeLabel = responseContentType?.trim() || "unknown content type";
        throw new Error(
          preview
            ? `Expected a ZIP download but received ${contentTypeLabel}. Response preview: ${preview}`
            : `Expected a ZIP download but received ${contentTypeLabel}.`,
        );
      }
      const blob = await response.blob();
      const filename =
        parseFilenameFromContentDisposition(response.headers.get("Content-Disposition")) ||
        `research-documents-${sanitizeFilename(workflowId)}.zip`;
      return { blob, filename };
    },
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      toast.success(`Downloaded ${filename}`);
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to download research archive";
      toast.error(message);
    },
  });
}

export function useWorkflowResearchArtifact(
  workflowId?: string,
  stepKey?: string,
  opts?: { enabled?: boolean },
) {
  const { get } = useApiClient();
  const enabled = Boolean(workflowId && stepKey) && (opts?.enabled ?? true);
  return useQuery<WorkflowResearchArtifact>({
    queryKey: ["workflows", workflowId, "research", stepKey],
    queryFn: () => get(`/workflows/${workflowId}/research/${stepKey}`),
    enabled,
  });
}

export type WorkflowResearchDownloadScope = "all" | "foundational";

export function useDownloadWorkflowResearchZip(workflowId?: string) {
  const { getToken } = useAuth();

  return useMutation({
    mutationFn: async (scope: WorkflowResearchDownloadScope = "all") => {
      if (!workflowId) throw new Error("Workflow ID is required.");
      const token = await getToken({ template: clerkTokenTemplate });
      const headers = new Headers();
      if (token) headers.set("Authorization", `Bearer ${token}`);
      const response = await fetch(
        `${defaultBaseUrl}/workflows/${workflowId}/research/download?scope=${encodeURIComponent(scope)}`,
        {
          method: "GET",
          headers,
        },
      );
      if (!response.ok) {
        throw await parseDownloadError(response);
      }
      const responseContentType = response.headers.get("Content-Type");
      if (!isZipContentType(responseContentType)) {
        const preview = (await response.text()).trim().slice(0, 240);
        const contentTypeLabel = responseContentType?.trim() || "unknown content type";
        throw new Error(
          preview
            ? `Expected a ZIP download but received ${contentTypeLabel}. Response preview: ${preview}`
            : `Expected a ZIP download but received ${contentTypeLabel}.`,
        );
      }
      const blob = await response.blob();
      const fileNameFromHeader = parseFilenameFromContentDisposition(
        response.headers.get("Content-Disposition"),
      );
      const filename = fileNameFromHeader || `workflow-research-${workflowId}.zip`;
      return { blob, filename };
    },
    onSuccess: ({ blob, filename }) => {
      const downloadUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = downloadUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(downloadUrl);
      toast.success(`Downloaded ${filename}`);
    },
    onError: (err: ApiError | Error) => {
      const message =
        "message" in err ? err.message : err?.message || "Failed to download workflow research ZIP";
      toast.error(message);
    },
  });
}

export function useWorkflowSignal(workflowId?: string) {
  const queryClient = useQueryClient();
  const { post } = useApiClient();

  return useMutation({
    mutationFn: async ({ signal, body }: { signal: string; body: Record<string, unknown> }) => {
      if (!workflowId) throw new Error("Workflow ID is required");
      return post(`/workflows/${workflowId}/signals/${signal}`, body);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      if (workflowId) {
        queryClient.invalidateQueries({ queryKey: ["workflows", workflowId, "logs"] });
        queryClient.invalidateQueries({ queryKey: ["workflows", workflowId, "detail"] });
        queryClient.invalidateQueries({ queryKey: ["workflows", workflowId] });
      }
      toast.success("Signal sent");
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to send signal";
      toast.error(message);
    },
  });
}

export function useStopWorkflow() {
  const queryClient = useQueryClient();
  const { post } = useApiClient();

  return useMutation({
    mutationFn: (workflowId: string) => post(`/workflows/${workflowId}/signals/stop`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      toast.success("Workflow stopped");
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to stop workflow";
      toast.error(message);
    },
  });
}

export type StrategyV2LaunchActionResponse = {
  launch_workflow_run_id: string;
  launch_temporal_workflow_id: string;
  campaign_ids: string[];
  funnel_workflow_run_ids: string[];
  launch_records: StrategyV2LaunchRecord[];
};

type StrategyV2LaunchAngleCampaignRequest = {
  channels: string[];
  assetBriefTypes: AssetBriefType[];
  experimentVariantPolicy: string;
};

type StrategyV2LaunchAdditionalUmsRequest = {
  campaignId: string;
  umsSelectionIds: string[];
  launchNamePrefix: string;
  channels?: string[];
  assetBriefTypes?: AssetBriefType[];
};

type StrategyV2LaunchAdditionalAngleRequest = {
  selectedAngleIds: string[];
  channels: string[];
  assetBriefTypes: AssetBriefType[];
};

export function useStrategyV2LaunchAngleCampaign(workflowId?: string) {
  const queryClient = useQueryClient();
  const { post } = useApiClient();
  return useMutation({
    mutationFn: async (payload: StrategyV2LaunchAngleCampaignRequest) => {
      if (!workflowId) throw new Error("Workflow ID is required");
      return post<StrategyV2LaunchActionResponse>(
        `/workflows/${workflowId}/actions/strategy-v2/launch-angle-campaign`,
        payload,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Angle campaign launch started");
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to launch angle campaign";
      toast.error(message);
    },
  });
}

export function useStrategyV2LaunchAdditionalUms(workflowId?: string) {
  const queryClient = useQueryClient();
  const { post } = useApiClient();
  return useMutation({
    mutationFn: async (payload: StrategyV2LaunchAdditionalUmsRequest) => {
      if (!workflowId) throw new Error("Workflow ID is required");
      return post<StrategyV2LaunchActionResponse>(
        `/workflows/${workflowId}/actions/strategy-v2/launch-additional-ums`,
        payload,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      queryClient.invalidateQueries({ queryKey: ["funnels"] });
      toast.success("Additional UMS launch started");
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to launch additional UMS funnels";
      toast.error(message);
    },
  });
}

export function useStrategyV2LaunchAdditionalAngle(workflowId?: string) {
  const queryClient = useQueryClient();
  const { post } = useApiClient();
  return useMutation({
    mutationFn: async (payload: StrategyV2LaunchAdditionalAngleRequest) => {
      if (!workflowId) throw new Error("Workflow ID is required");
      return post<StrategyV2LaunchActionResponse>(
        `/workflows/${workflowId}/actions/strategy-v2/launch-additional-angle`,
        payload,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Additional angle launch started");
    },
    onError: (err: ApiError | Error) => {
      const message = "message" in err ? err.message : err?.message || "Failed to launch additional angles";
      toast.error(message);
    },
  });
}
