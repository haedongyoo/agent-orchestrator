"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { TaskTrace } from "@/lib/types";

export function useTaskTrace(taskId: string | undefined) {
  return useQuery({
    queryKey: ["task-trace", taskId],
    queryFn: () => api.get<TaskTrace>(`/api/tasks/${taskId}/trace`),
    enabled: !!taskId,
    refetchInterval: 5000,
  });
}
