"use client";

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { MessagePage, MessageCreate, Message } from "@/lib/types";

export function useMessages(threadId: string | undefined) {
  return useInfiniteQuery({
    queryKey: ["messages", threadId],
    queryFn: ({ pageParam }) => {
      const params = pageParam ? `?cursor=${pageParam}` : "";
      return api.get<MessagePage>(`/api/threads/${threadId}/messages${params}`);
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    initialPageParam: undefined as string | undefined,
    enabled: !!threadId,
  });
}

export function usePostMessage(threadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: MessageCreate) =>
      api.post<Message>(`/api/threads/${threadId}/messages`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["messages", threadId] }),
  });
}
