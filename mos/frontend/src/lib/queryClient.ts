import { QueryClient } from "@tanstack/react-query";
import { toast } from "@/components/ui/toast";
import type { ApiError } from "@/api/client";

function formatError(error: unknown): string {
  if ((error as ApiError)?.message) return (error as ApiError).message;
  if (error instanceof Error) return error.message;
  return "Something went wrong";
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
      onError: (error) => toast.error(formatError(error)),
    },
  },
});
