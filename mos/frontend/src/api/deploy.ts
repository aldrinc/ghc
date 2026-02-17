import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "@/api/client";

export type DeployWorkloadDomainsResponse = {
  workload_name: string;
  plan_path: string;
  workload_found: boolean;
  server_names: string[];
  https?: boolean | null;
};

export function useDeployWorkloadDomains({
  workloadName,
  planPath,
  instanceName,
}: {
  workloadName?: string;
  planPath?: string;
  instanceName?: string;
}) {
  const { get } = useApiClient();
  const enabled = Boolean(workloadName);

  return useQuery<DeployWorkloadDomainsResponse>({
    queryKey: ["deploy", "workload-domains", workloadName ?? null, planPath ?? null, instanceName ?? null],
    queryFn: async () => {
      const params = new URLSearchParams();
      params.set("workload_name", workloadName || "");
      if (planPath) params.set("plan_path", planPath);
      if (instanceName) params.set("instance_name", instanceName);
      return get(`/deploy/plans/workloads/domains?${params.toString()}`);
    },
    enabled,
  });
}

