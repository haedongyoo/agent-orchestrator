"use client";

import { createContext, useContext, useCallback, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type { Workspace, WorkspaceCreate } from "@/lib/types";
import { useAuth } from "./auth-provider";

interface WorkspaceContextValue {
  workspace: Workspace | null;
  workspaces: Workspace[];
  isLoading: boolean;
  switchWorkspace: (id: string) => void;
  createWorkspace: (data: WorkspaceCreate) => Promise<Workspace>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem("workspace_id");
    if (stored) setActiveId(stored);
  }, []);

  const { data: workspaces = [], isLoading } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.get<Workspace[]>("/api/workspaces"),
    enabled: !!user,
  });

  // Auto-select first workspace if none stored
  useEffect(() => {
    if (!activeId && workspaces.length > 0) {
      setActiveId(workspaces[0].id);
      localStorage.setItem("workspace_id", workspaces[0].id);
    }
  }, [activeId, workspaces]);

  const workspace = workspaces.find((w) => w.id === activeId) ?? null;

  const createWorkspace = useCallback(
    async (data: WorkspaceCreate) => {
      const ws = await api.post<Workspace>("/api/workspaces", data);
      await queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      setActiveId(ws.id);
      localStorage.setItem("workspace_id", ws.id);
      return ws;
    },
    [queryClient],
  );

  const switchWorkspace = useCallback(
    (id: string) => {
      setActiveId(id);
      localStorage.setItem("workspace_id", id);
      // Clear workspace-scoped caches
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      queryClient.invalidateQueries({ queryKey: ["threads"] });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: ["vendors"] });
    },
    [queryClient],
  );

  return (
    <WorkspaceContext.Provider
      value={{ workspace, workspaces, isLoading, switchWorkspace, createWorkspace }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
