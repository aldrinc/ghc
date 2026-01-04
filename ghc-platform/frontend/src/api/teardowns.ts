import { useCallback } from "react";
import { useApiClient } from "./client";
import type { Teardown } from "@/types/teardowns";

export function useTeardownApi() {
  const { get } = useApiClient();

  const listTeardowns = useCallback(
    (params?: {
      clientId?: string;
      campaignId?: string;
      proofType?: string;
      beatKey?: string;
      signalCategory?: string;
      numericUnit?: string;
      claimTopic?: string;
      claimTextContains?: string;
      limit?: number;
      includeChildren?: boolean;
    }): Promise<Teardown[]> => {
      const searchParams = new URLSearchParams();
      if (params?.clientId) searchParams.set("clientId", params.clientId);
      if (params?.campaignId) searchParams.set("campaignId", params.campaignId);
      if (params?.proofType) searchParams.set("proofType", params.proofType);
      if (params?.beatKey) searchParams.set("beatKey", params.beatKey);
      if (params?.signalCategory) searchParams.set("signalCategory", params.signalCategory);
      if (params?.numericUnit) searchParams.set("numericUnit", params.numericUnit);
      if (params?.claimTopic) searchParams.set("claimTopic", params.claimTopic);
      if (params?.claimTextContains) searchParams.set("claimTextContains", params.claimTextContains);
      if (params?.limit) searchParams.set("limit", params.limit.toString());
      if (params?.includeChildren) searchParams.set("includeChildren", "true");
      const qs = searchParams.toString();
      const path = qs ? `/teardowns?${qs}` : "/teardowns";
      return get<Teardown[]>(path);
    },
    [get],
  );

  return { listTeardowns };
}
