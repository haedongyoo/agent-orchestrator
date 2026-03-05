"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, XCircle } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useAgents } from "@/hooks/use-agents";
import { ChatView } from "@/components/threads/chat-view";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Thread } from "@/lib/types";

export default function ThreadDetailPage() {
  const { threadId } = useParams<{ threadId: string }>();
  const qc = useQueryClient();
  const { data: agents } = useAgents();

  const { data: thread, isLoading } = useQuery({
    queryKey: ["thread", threadId],
    queryFn: () => api.get<Thread>(`/api/threads/${threadId}`),
    enabled: !!threadId,
  });

  const closeThread = useMutation({
    mutationFn: () => api.post<Thread>(`/api/threads/${threadId}/close`, {}),
    onSuccess: (data) => {
      qc.setQueryData(["thread", threadId], data);
      qc.invalidateQueries({ queryKey: ["threads"] });
    },
  });

  if (isLoading) {
    return (
      <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">
        Loading thread...
      </div>
    );
  }

  if (!thread) {
    return (
      <div className="py-20 text-center">
        <p className="text-sm text-[var(--muted-foreground)]">Thread not found.</p>
        <Link href="/threads">
          <Button variant="outline" className="mt-4">Back to Threads</Button>
        </Link>
      </div>
    );
  }

  const assignedAgent = thread.agent_id
    ? agents?.find((a) => a.id === thread.agent_id)
    : null;
  const isClosed = thread.status === "closed";

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      {/* Thread header */}
      <div className="flex items-center gap-3 border-b border-[var(--border)] pb-4">
        <Link href="/threads">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-lg font-semibold">{thread.title}</h1>
          {assignedAgent && (
            <p className="text-xs text-[var(--muted-foreground)]">
              Agent: {assignedAgent.name}
            </p>
          )}
        </div>
        <Badge variant={isClosed ? "secondary" : "default"}>
          {thread.status}
        </Badge>
        {!isClosed && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => closeThread.mutate()}
            disabled={closeThread.isPending}
          >
            <XCircle className="mr-1 h-4 w-4" />
            {closeThread.isPending ? "Closing..." : "Close"}
          </Button>
        )}
      </div>

      {/* Chat view fills remaining space */}
      <div className="flex-1 overflow-hidden">
        <ChatView threadId={threadId} disabled={isClosed} />
      </div>
    </div>
  );
}
