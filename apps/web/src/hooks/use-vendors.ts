"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWorkspace } from "@/providers/workspace-provider";
import type { Vendor } from "@/lib/types";

export function useVendors() {
  const { workspace } = useWorkspace();
  return useQuery({
    queryKey: ["vendors", workspace?.id],
    queryFn: () => api.get<Vendor[]>(`/api/workspaces/${workspace!.id}/vendors`),
    enabled: !!workspace,
  });
}
