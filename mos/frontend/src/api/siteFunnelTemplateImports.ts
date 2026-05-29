import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";
import { useWorkspace } from "@/contexts/WorkspaceContext";

function getMutationErrorMessage(err: ApiError | Error, fallback: string): string {
  const candidate = err as { message?: unknown };
  return typeof candidate.message === "string" && candidate.message ? candidate.message : fallback;
}

export interface SiteFunnelTemplateImport {
  id: string;
  siteId: string;
  sourceLabel: string;
  htmlLength: number;
  htmlSha256: string;
  createdByUserExternalId: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface SiteFunnelTemplateImportDetail extends SiteFunnelTemplateImport {
  htmlSnapshot: string;
}

export interface CreateSiteFunnelTemplateImportRequest {
  sourceLabel: string;
  htmlDocument: string;
}

export function useSiteFunnelTemplateImports(siteId: string | null | undefined) {
  const { get } = useApiClient();
  const { workspace } = useWorkspace();

  return useQuery<SiteFunnelTemplateImport[]>({
    queryKey: ["sites", siteId, "funnel-template-imports"],
    queryFn: () =>
      get<SiteFunnelTemplateImport[]>(`/sites/${siteId}/funnel-template-imports?clientId=${workspace!.id}`),
    enabled: !!workspace?.id && !!siteId,
  });
}

export function useCreateSiteFunnelTemplateImport(siteId: string | null | undefined) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  const { workspace } = useWorkspace();

  return useMutation({
    mutationFn: (request: CreateSiteFunnelTemplateImportRequest) =>
      post<SiteFunnelTemplateImportDetail>(
        `/sites/${siteId}/funnel-template-imports?clientId=${workspace!.id}`,
        request,
      ),
    onSuccess: () => {
      toast.success("HTML template imported");
      queryClient.invalidateQueries({ queryKey: ["sites", siteId, "funnel-template-imports"] });
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to import HTML template"));
    },
  });
}
