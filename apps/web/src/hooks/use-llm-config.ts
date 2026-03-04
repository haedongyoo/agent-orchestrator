"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWorkspace } from "@/providers/workspace-provider";

export interface LLMConfig {
  model: string;
  has_api_key: boolean;
  api_base_url: string | null;
  max_tokens: number;
  temperature: number;
}

export interface LLMConfigSet {
  model: string;
  api_key?: string;
  api_base_url?: string;
  max_tokens?: number;
  temperature?: number;
}

export interface LLMProvider {
  id: string;
  name: string;
  requires_api_key: boolean;
  default_base_url: string | null;
}

export interface LLMModel {
  id: string;
  name: string;
  max_tokens: number;
}

export interface TestResult {
  success: boolean;
  message: string;
  model: string;
}

export function useLLMProviders() {
  return useQuery({
    queryKey: ["llm-providers"],
    queryFn: () => api.get<LLMProvider[]>("/api/llm/providers"),
  });
}

export function useLLMModels(providerId: string | undefined) {
  return useQuery({
    queryKey: ["llm-models", providerId],
    queryFn: () => api.get<LLMModel[]>(`/api/llm/providers/${providerId}/models`),
    enabled: !!providerId,
  });
}

export function useAgentLLMConfig(agentId: string | undefined) {
  const { workspace } = useWorkspace();
  return useQuery({
    queryKey: ["agent-llm-config", workspace?.id, agentId],
    queryFn: () =>
      api.get<LLMConfig>(
        `/api/workspaces/${workspace!.id}/agents/${agentId}/llm-config`,
      ),
    enabled: !!workspace && !!agentId,
    retry: false,
  });
}

export function useSetAgentLLMConfig(agentId: string) {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: LLMConfigSet) =>
      api.post<LLMConfig>(
        `/api/workspaces/${workspace!.id}/agents/${agentId}/llm-config`,
        data,
      ),
    onSuccess: () =>
      qc.invalidateQueries({
        queryKey: ["agent-llm-config", workspace?.id, agentId],
      }),
  });
}

export function useTestAgentLLMConfig(agentId: string) {
  const { workspace } = useWorkspace();
  return useMutation({
    mutationFn: () =>
      api.post<TestResult>(
        `/api/workspaces/${workspace!.id}/agents/${agentId}/llm-config/test`,
      ),
  });
}
