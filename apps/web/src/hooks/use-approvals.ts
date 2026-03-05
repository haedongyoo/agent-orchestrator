"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
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
  });
}

export function useApproveApproval() {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      api.post<Approval>(`/api/approvals/${id}/approve`, { note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals", workspace?.id] }),
  });
}

export function useRejectApproval() {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      api.post<Approval>(`/api/approvals/${id}/reject`, { note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals", workspace?.id] }),
  });
}
