"use client";

import { useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWorkspace } from "@/providers/workspace-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Play, Square, RefreshCw, Loader2 } from "lucide-react";

interface ContainerInfo {
  container_id: string | null;
  status: string;
  agent_id: string;
}

const STATUS_COLORS: Record<string, string> = {
  running: "bg-green-500",
  starting: "bg-yellow-500",
  stopping: "bg-yellow-500",
  stopped: "bg-zinc-400",
  crashed: "bg-red-500",
  exited: "bg-red-500",
  created: "bg-yellow-500",
  no_container: "bg-zinc-400",
  not_found: "bg-zinc-400",
  unknown: "bg-zinc-400",
};

const TRANSITIONAL = new Set(["starting", "stopping", "created"]);

export function ContainerStatus({ agentId }: { agentId: string }) {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  const queryKey = ["container-status", workspace?.id, agentId];

  const { data, isLoading, refetch } = useQuery({
    queryKey,
    queryFn: () =>
      api.get<ContainerInfo>(
        `/api/workspaces/${workspace!.id}/agents/${agentId}/container`,
      ),
    enabled: !!workspace,
    refetchInterval: 10000,
    retry: false,
  });

  // Poll faster (every 2s) while in a transitional state
  const isTransitional = TRANSITIONAL.has(data?.status || "");
  useEffect(() => {
    if (!isTransitional) return;
    const interval = setInterval(() => refetch(), 2000);
    return () => clearInterval(interval);
  }, [isTransitional, refetch]);

  const startMutation = useMutation({
    mutationFn: () =>
      api.post(`/api/workspaces/${workspace!.id}/agents/${agentId}/container/start`),
    onMutate: () => {
      // Optimistic update — show "starting" immediately
      qc.setQueryData(queryKey, (old: ContainerInfo | undefined) => ({
        ...old,
        status: "starting",
        agent_id: agentId,
        container_id: old?.container_id ?? null,
      }));
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
    },
    onError: () => {
      // Revert on failure
      qc.invalidateQueries({ queryKey });
    },
  });

  const stopMutation = useMutation({
    mutationFn: () =>
      api.post(`/api/workspaces/${workspace!.id}/agents/${agentId}/container/stop`),
    onMutate: () => {
      // Optimistic update — show "stopping" immediately
      qc.setQueryData(queryKey, (old: ContainerInfo | undefined) => ({
        ...old,
        status: "stopping",
        agent_id: agentId,
        container_id: old?.container_id ?? null,
      }));
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey });
    },
    onError: () => {
      qc.invalidateQueries({ queryKey });
    },
  });

  const status = data?.status || "not_found";
  const statusColor = STATUS_COLORS[status] || "bg-zinc-400";
  const isPending = startMutation.isPending || stopMutation.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          Container
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => refetch()}>
            <RefreshCw className="h-3.5 w-3.5" />
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <p className="text-sm text-[var(--muted-foreground)]">Checking container status...</p>
        ) : (
          <>
            <div className="flex items-center gap-2">
              {isTransitional ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-yellow-500" />
              ) : (
                <div className={`h-2.5 w-2.5 rounded-full ${statusColor}`} />
              )}
              <span className="text-sm font-medium capitalize">
                {status}
              </span>
              {data?.container_id && (
                <Badge variant="secondary" className="ml-2 font-mono text-xs">
                  {data.container_id.substring(0, 12)}
                </Badge>
              )}
            </div>

            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => startMutation.mutate()}
                disabled={isPending || status === "running" || status === "starting"}
              >
                {status === "starting" ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Play className="mr-1 h-3.5 w-3.5" />
                )}
                {status === "starting" ? "Starting..." : "Start"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => stopMutation.mutate()}
                disabled={isPending || (status !== "running" && status !== "starting")}
              >
                {status === "stopping" ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Square className="mr-1 h-3.5 w-3.5" />
                )}
                {status === "stopping" ? "Stopping..." : "Stop"}
              </Button>
            </div>

            {(startMutation.error || stopMutation.error) && (
              <p className="text-sm text-[var(--destructive)]">
                {(startMutation.error || stopMutation.error)?.message}
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
