"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWorkspace } from "@/providers/workspace-provider";
import type { Approval } from "@/lib/types";

export function useApprovals(status?: string) {
  const { workspace } = useWorkspace();
  const params = status ? `?status=${status}` : "";
  return useQuery({
    queryKey: ["approvals", workspace?.id, status],
    queryFn: () =>
      api.get<Approval[]>(`/api/workspaces/${workspace!.id}/approvals${params}`),
    enabled: !!workspace,
    retry: false, // approvals endpoint may still be 501
  });
}
