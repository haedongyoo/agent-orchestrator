"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { Task, TaskStep } from "@/lib/types";

export function useTask(taskId: string | undefined) {
  return useQuery({
    queryKey: ["task", taskId],
    queryFn: () => api.get<Task>(`/api/tasks/${taskId}`),
    enabled: !!taskId,
  });
}

export function useTaskSteps(taskId: string | undefined) {
  return useQuery({
    queryKey: ["task-steps", taskId],
    queryFn: () => api.get<TaskStep[]>(`/api/tasks/${taskId}/steps`),
    enabled: !!taskId,
    refetchInterval: 5000, // auto-refresh for running tasks
  });
}

export function useCancelTask(taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post(`/api/tasks/${taskId}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  });
}
