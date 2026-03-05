"use client";

import { useCreateVendor } from "@/hooks/use-vendors";
import { VendorForm } from "@/components/vendors/vendor-form";
import type { VendorCreate } from "@/lib/types";

export default function NewVendorPage() {
  const create = useCreateVendor();

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">New Vendor</h1>
        <p className="text-sm text-[var(--muted-foreground)]">Add a vendor or contractor to your CRM</p>
      </div>
      <VendorForm
        mode="create"
        onSubmit={(data) => create.mutateAsync(data as VendorCreate)}
      />
    </div>
  );
}
