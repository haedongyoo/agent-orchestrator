"use client";

import { useState } from "react";
import Link from "next/link";
import { Plus, MessageSquare } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useThreads } from "@/hooks/use-threads";
import { useWorkspace } from "@/providers/workspace-provider";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { Thread, ThreadCreate } from "@/lib/types";

export default function ThreadsPage() {
  const { workspace } = useWorkspace();
  const { data: threads, isLoading } = useThreads();
  const [showNew, setShowNew] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const qc = useQueryClient();

  const createThread = useMutation({
    mutationFn: (data: ThreadCreate) =>
      api.post<Thread>(`/api/workspaces/${workspace!.id}/threads`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["threads", workspace?.id] });
      setShowNew(false);
      setNewTitle("");
    },
  });

  if (!workspace) {
    return (
      <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">
        Select a workspace first.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Threads</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            {threads?.length ?? 0} thread{threads?.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Button onClick={() => setShowNew(true)}>
          <Plus className="mr-2 h-4 w-4" />
          New Thread
        </Button>
      </div>

      {/* New thread dialog */}
      {showNew && (
        <Card>
          <CardContent className="pt-6">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (newTitle.trim()) createThread.mutate({ title: newTitle.trim() });
              }}
              className="flex gap-3"
            >
              <Input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Thread title..."
                autoFocus
              />
              <Button type="submit" disabled={createThread.isPending || !newTitle.trim()}>
                {createThread.isPending ? "Creating..." : "Create"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setShowNew(false)}>
                Cancel
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">Loading threads...</div>
      ) : threads?.length === 0 ? (
        <div className="py-20 text-center">
          <MessageSquare className="mx-auto mb-4 h-12 w-12 text-[var(--muted-foreground)]" />
          <p className="text-sm text-[var(--muted-foreground)]">No threads yet.</p>
          <Button variant="outline" className="mt-4" onClick={() => setShowNew(true)}>
            Start a conversation
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {threads?.map((thread) => (
            <Link
              key={thread.id}
              href={`/threads/${thread.id}`}
              className="flex items-center justify-between rounded-lg border border-[var(--border)] p-4 transition-colors hover:bg-[var(--accent)]"
            >
              <div className="flex items-center gap-3">
                <MessageSquare className="h-4 w-4 text-[var(--muted-foreground)]" />
                <span className="font-medium">{thread.title}</span>
              </div>
              <Badge variant={thread.status === "open" ? "default" : "secondary"}>
                {thread.status}
              </Badge>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
