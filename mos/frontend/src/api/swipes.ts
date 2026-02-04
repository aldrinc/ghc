import { useQuery } from "@tanstack/react-query";
import { useApiClient } from "./client";
import type { ClientSwipeAsset } from "@/types/swipes";

export function useClientSwipes(clientId?: string) {
  const { get } = useApiClient();
  return useQuery<ClientSwipeAsset[]>({
    queryKey: ["swipes", clientId],
    queryFn: () => get(`/swipes/client/${clientId}`),
    enabled: Boolean(clientId),
  });
}
