"use client";

import { useState } from "react";
import Link from "next/link";
import { Plus, MessageSquare, Bot } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useThreads } from "@/hooks/use-threads";
import { useAgents } from "@/hooks/use-agents";
import { useWorkspace } from "@/providers/workspace-provider";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { Thread, ThreadCreate } from "@/lib/types";

export default function ThreadsPage() {
  const { workspace } = useWorkspace();
  const { data: threads, isLoading } = useThreads();
  const { data: agents } = useAgents();
  const [showNew, setShowNew] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const qc = useQueryClient();

  const createThread = useMutation({
    mutationFn: (data: ThreadCreate) =>
      api.post<Thread>(`/api/workspaces/${workspace!.id}/threads`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["threads", workspace?.id] });
      setShowNew(false);
      setNewTitle("");
      setSelectedAgentId("");
    },
  });

  if (!workspace) {
    return (
      <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">
        Select a workspace first.
      </div>
    );
  }

  const enabledAgents = agents?.filter((a) => a.is_enabled) ?? [];

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
                if (newTitle.trim()) {
                  const data: ThreadCreate = { title: newTitle.trim() };
                  if (selectedAgentId) data.agent_id = selectedAgentId;
                  createThread.mutate(data);
                }
              }}
              className="space-y-3"
            >
              <Input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Thread title..."
                autoFocus
              />
              <div className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-[var(--muted-foreground)]" />
                <select
                  value={selectedAgentId}
                  onChange={(e) => setSelectedAgentId(e.target.value)}
                  className="flex-1 rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
                >
                  <option value="">Auto-assign agent</option>
                  {enabledAgents.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex gap-3">
                <Button type="submit" disabled={createThread.isPending || !newTitle.trim()}>
                  {createThread.isPending ? "Creating..." : "Create"}
                </Button>
                <Button type="button" variant="ghost" onClick={() => { setShowNew(false); setSelectedAgentId(""); }}>
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-14 w-full rounded-lg" />
          ))}
        </div>
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
          {threads?.map((thread) => {
            const assignedAgent = thread.agent_id
              ? agents?.find((a) => a.id === thread.agent_id)
              : null;
            return (
              <Link
                key={thread.id}
                href={`/threads/${thread.id}`}
                className="flex items-center justify-between rounded-lg border border-[var(--border)] p-4 transition-colors hover:bg-[var(--accent)]"
              >
                <div className="flex items-center gap-3">
                  <MessageSquare className="h-4 w-4 text-[var(--muted-foreground)]" />
                  <div>
                    <span className="font-medium">{thread.title}</span>
                    {assignedAgent && (
                      <span className="ml-2 text-xs text-[var(--muted-foreground)]">
                        {assignedAgent.name}
                      </span>
                    )}
                  </div>
                </div>
                <Badge variant={thread.status === "open" ? "default" : "secondary"}>
                  {thread.status}
                </Badge>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
