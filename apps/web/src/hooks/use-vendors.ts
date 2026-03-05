"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import { useWorkspace } from "@/providers/workspace-provider";
import type { Vendor, VendorCreate } from "@/lib/types";

export function useVendors() {
  const { workspace } = useWorkspace();
  return useQuery({
    queryKey: ["vendors", workspace?.id],
    queryFn: () => api.get<Vendor[]>(`/api/workspaces/${workspace!.id}/vendors`),
    enabled: !!workspace,
  });
}

export function useVendor(vendorId: string | undefined) {
  const { workspace } = useWorkspace();
  return useQuery({
    queryKey: ["vendor", workspace?.id, vendorId],
    queryFn: () =>
      api.get<Vendor>(`/api/workspaces/${workspace!.id}/vendors/${vendorId}`),
    enabled: !!workspace && !!vendorId,
  });
}

export function useCreateVendor() {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: VendorCreate) =>
      api.post<Vendor>(`/api/workspaces/${workspace!.id}/vendors`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendors", workspace?.id] }),
  });
}

export function useUpdateVendor(vendorId: string) {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<VendorCreate>) =>
      api.put<Vendor>(`/api/workspaces/${workspace!.id}/vendors/${vendorId}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendors", workspace?.id] });
      qc.invalidateQueries({ queryKey: ["vendor", workspace?.id, vendorId] });
    },
  });
}

export function useDeleteVendor(vendorId: string) {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api.delete(`/api/workspaces/${workspace!.id}/vendors/${vendorId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendors", workspace?.id] }),
  });
}
