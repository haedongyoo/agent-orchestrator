"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWorkspace } from "@/providers/workspace-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Play, Square, RefreshCw } from "lucide-react";

interface ContainerInfo {
  container_id: string | null;
  status: string;
  agent_id: string;
}

export function ContainerStatus({ agentId }: { agentId: string }) {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["container-status", workspace?.id, agentId],
    queryFn: () =>
      api.get<ContainerInfo>(
        `/api/workspaces/${workspace!.id}/agents/${agentId}/container`,
      ),
    enabled: !!workspace,
    refetchInterval: 10000, // auto-refresh every 10s
    retry: false,
  });

  const startMutation = useMutation({
    mutationFn: () =>
      api.post(`/api/workspaces/${workspace!.id}/agents/${agentId}/container/start`),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["container-status", workspace?.id, agentId],
      });
    },
  });

  const stopMutation = useMutation({
    mutationFn: () =>
      api.post(`/api/workspaces/${workspace!.id}/agents/${agentId}/container/stop`),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["container-status", workspace?.id, agentId],
      });
    },
  });

  const statusColor = {
    running: "bg-green-500",
    exited: "bg-red-500",
    created: "bg-yellow-500",
    not_found: "bg-zinc-400",
  }[data?.status || "not_found"] || "bg-zinc-400";

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
              <div className={`h-2.5 w-2.5 rounded-full ${statusColor}`} />
              <span className="text-sm font-medium capitalize">
                {data?.status || "Unknown"}
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
                disabled={startMutation.isPending || data?.status === "running"}
              >
                <Play className="mr-1 h-3.5 w-3.5" />
                {startMutation.isPending ? "Starting..." : "Start"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => stopMutation.mutate()}
                disabled={stopMutation.isPending || data?.status !== "running"}
              >
                <Square className="mr-1 h-3.5 w-3.5" />
                {stopMutation.isPending ? "Stopping..." : "Stop"}
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
