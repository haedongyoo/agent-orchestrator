"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWorkspace } from "@/providers/workspace-provider";
import type { Agent, AgentCreate, AgentUpdate, AgentTemplate } from "@/lib/types";

export function useAgents() {
  const { workspace } = useWorkspace();
  return useQuery({
    queryKey: ["agents", workspace?.id],
    queryFn: () => api.get<Agent[]>(`/api/workspaces/${workspace!.id}/agents`),
    enabled: !!workspace,
  });
}

export function useAgent(agentId: string | undefined) {
  const { workspace } = useWorkspace();
  const { data: agents } = useAgents();
  // Agent detail is fetched from the list (no separate endpoint needed)
  return {
    data: agents?.find((a) => a.id === agentId),
    isLoading: !agents && !!workspace,
  };
}

export function useCreateAgent() {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AgentCreate) =>
      api.post<Agent>(`/api/workspaces/${workspace!.id}/agents`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents", workspace?.id] }),
  });
}

export function useUpdateAgent(agentId: string) {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AgentUpdate) =>
      api.put<Agent>(`/api/workspaces/${workspace!.id}/agents/${agentId}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents", workspace?.id] }),
  });
}

export function useDeleteAgent(agentId: string) {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.delete(`/api/workspaces/${workspace!.id}/agents/${agentId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents", workspace?.id] }),
  });
}

export function useAgentTemplates() {
  return useQuery({
    queryKey: ["agent-templates"],
    queryFn: () => api.get<AgentTemplate[]>("/api/agent-templates"),
  });
}
