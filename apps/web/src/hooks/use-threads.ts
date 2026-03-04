"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWorkspace } from "@/providers/workspace-provider";
import type { Thread } from "@/lib/types";

export function useThreads() {
  const { workspace } = useWorkspace();
  return useQuery({
    queryKey: ["threads", workspace?.id],
    queryFn: () => api.get<Thread[]>(`/api/workspaces/${workspace!.id}/threads`),
    enabled: !!workspace,
  });
}
