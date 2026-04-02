import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useApiClient, type ApiError } from "@/api/client";
import { toast } from "@/components/ui/toast";

export const PRODUCT_STRATEGY_SKILLS_STATUS_QUERY_KEY = (productId: string) =>
  ["products", productId, "strategy-skills", "status"] as const;

export type StrategySkillsBundleItem = {
  id: string;
  role: string;
  itemOrder: number;
  artifactId: string;
  artifactType: string;
  artifactData: Record<string, unknown>;
  createdAt: string;
};

export type StrategySkillsBundle = {
  id: string;
  bundleType: string;
  title: string;
  status: string;
  isActive: boolean;
  metadata: Record<string, unknown>;
  approvedByUser?: string | null;
  approvedAt?: string | null;
  createdAt: string;
  updatedAt: string;
  items: StrategySkillsBundleItem[];
};

export type StrategySkillsStatus = {
  clientId: string;
  productId: string;
  bundleKey: string;
  skillsBinding?: Record<string, unknown> | null;
  activeFoundationalBundle?: StrategySkillsBundle | null;
  activeWorkingBundle?: StrategySkillsBundle | null;
  activeHandoffBundle?: StrategySkillsBundle | null;
  pendingHandoffBundles: StrategySkillsBundle[];
  historicalHandoffBundles: StrategySkillsBundle[];
  foundationalCompleteness?: {
    isComplete: boolean;
    expectedDocKeys: string[];
    presentDocKeys: string[];
    missingDocKeys: string[];
  } | null;
};

export type StrategySkillsBootstrapRequest = {
  releaseVersion: string;
  strategyRoot: string;
  foundationalRoot: string;
  bundleKey?: string;
  bundleFamily?: string;
  sourceRevision?: string | null;
  sourceRef?: string | null;
};

export type StrategySkillsMutationResponse = {
  clientId: string;
  productId: string;
  result: Record<string, unknown>;
};

function getMutationErrorMessage(err: ApiError | Error, fallback: string): string {
  if ("message" in err && typeof err.message === "string") return err.message;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function useStrategySkillsStatus(productId?: string) {
  const { get } = useApiClient();
  return useQuery<StrategySkillsStatus>({
    queryKey: productId ? PRODUCT_STRATEGY_SKILLS_STATUS_QUERY_KEY(productId) : ["products", "strategy-skills", "status"],
    queryFn: () => get(`/products/${productId}/strategy-skills/status`),
    enabled: Boolean(productId),
  });
}

export function useBootstrapStrategySkills(productId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: StrategySkillsBootstrapRequest) => {
      if (!productId) throw new Error("Product ID is required");
      return post(`/products/${productId}/strategy-skills/bootstrap`, payload);
    },
    onSuccess: () => {
      if (productId) {
        queryClient.invalidateQueries({ queryKey: PRODUCT_STRATEGY_SKILLS_STATUS_QUERY_KEY(productId) });
      }
      toast.success("Strategy skills bootstrapped");
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to bootstrap strategy skills"));
    },
  });
}

export function useApproveFoundationalStrategySkills(productId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { allowIncomplete: boolean }) => {
      if (!productId) throw new Error("Product ID is required");
      return post<StrategySkillsMutationResponse>(
        `/products/${productId}/strategy-skills/foundational/approve`,
        payload,
      );
    },
    onSuccess: () => {
      if (productId) {
        queryClient.invalidateQueries({ queryKey: PRODUCT_STRATEGY_SKILLS_STATUS_QUERY_KEY(productId) });
      }
      toast.success("Foundational bundle approved");
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to approve foundational bundle"));
    },
  });
}

export function useRunStrategySkillsStage(productId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { stageKey: string; bundleKey?: string }) => {
      if (!productId) throw new Error("Product ID is required");
      return post<StrategySkillsMutationResponse>(
        `/products/${productId}/strategy-skills/stages/${payload.stageKey}`,
        {
          bundleKey: payload.bundleKey,
          promoteToActiveBundle: false,
        },
      );
    },
    onSuccess: (_data, variables) => {
      if (productId) {
        queryClient.invalidateQueries({ queryKey: PRODUCT_STRATEGY_SKILLS_STATUS_QUERY_KEY(productId) });
      }
      toast.success(`Stage "${variables.stageKey}" completed`);
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to run stage"));
    },
  });
}

export function useSelectStrategyAngle(productId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { selectedId: string; rationale: string }) => {
      if (!productId) throw new Error("Product ID is required");
      return post<StrategySkillsMutationResponse>(`/products/${productId}/strategy-skills/select-angle`, payload);
    },
    onSuccess: () => {
      if (productId) {
        queryClient.invalidateQueries({ queryKey: PRODUCT_STRATEGY_SKILLS_STATUS_QUERY_KEY(productId) });
      }
      toast.success("Angle selected");
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to select angle"));
    },
  });
}

export function useSelectStrategyHeadline(productId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { selectedId: string; rationale: string }) => {
      if (!productId) throw new Error("Product ID is required");
      return post<StrategySkillsMutationResponse>(`/products/${productId}/strategy-skills/select-headline`, payload);
    },
    onSuccess: () => {
      if (productId) {
        queryClient.invalidateQueries({ queryKey: PRODUCT_STRATEGY_SKILLS_STATUS_QUERY_KEY(productId) });
      }
      toast.success("Headline selected");
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to select headline"));
    },
  });
}

export function useApproveStrategyRole(productId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { role: string }) => {
      if (!productId) throw new Error("Product ID is required");
      return post<StrategySkillsMutationResponse>(`/products/${productId}/strategy-skills/approve-role`, payload);
    },
    onSuccess: (_data, variables) => {
      if (productId) {
        queryClient.invalidateQueries({ queryKey: PRODUCT_STRATEGY_SKILLS_STATUS_QUERY_KEY(productId) });
      }
      toast.success(`Approved ${variables.role.replace(/_/g, " ")}`);
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to approve draft role"));
    },
  });
}

export function useActivateStrategyHandoff(productId?: string) {
  const { post } = useApiClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { bundleId: string }) => {
      if (!productId) throw new Error("Product ID is required");
      return post<StrategySkillsMutationResponse>(`/products/${productId}/strategy-skills/handoff/activate`, payload);
    },
    onSuccess: () => {
      if (productId) {
        queryClient.invalidateQueries({ queryKey: PRODUCT_STRATEGY_SKILLS_STATUS_QUERY_KEY(productId) });
      }
      toast.success("Approved bundle activated");
    },
    onError: (err: ApiError | Error) => {
      toast.error(getMutationErrorMessage(err, "Failed to activate approved bundle"));
    },
  });
}
