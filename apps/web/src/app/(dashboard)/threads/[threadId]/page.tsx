"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { ChatView } from "@/components/threads/chat-view";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Thread } from "@/lib/types";

export default function ThreadDetailPage() {
  const { threadId } = useParams<{ threadId: string }>();

  const { data: thread, isLoading } = useQuery({
    queryKey: ["thread", threadId],
    queryFn: () => api.get<Thread>(`/api/threads/${threadId}`),
    enabled: !!threadId,
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
        </div>
        <Badge variant={thread.status === "open" ? "default" : "secondary"}>
          {thread.status}
        </Badge>
      </div>

      {/* Chat view fills remaining space */}
      <div className="flex-1 overflow-hidden">
        <ChatView threadId={threadId} />
      </div>
    </div>
  );
}
