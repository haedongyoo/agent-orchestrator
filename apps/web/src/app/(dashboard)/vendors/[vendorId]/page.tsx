"use client";

import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Trash2 } from "lucide-react";
import { useVendor, useDeleteVendor } from "@/hooks/use-vendors";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function VendorDetailPage() {
  const { vendorId } = useParams<{ vendorId: string }>();
  const { data: vendor, isLoading } = useVendor(vendorId);
  const deleteVendor = useDeleteVendor(vendorId);
  const router = useRouter();

  if (isLoading) {
    return <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">Loading vendor...</div>;
  }

  if (!vendor) {
    return (
      <div className="py-20 text-center">
        <p className="text-sm text-[var(--muted-foreground)]">Vendor not found.</p>
        <Link href="/vendors"><Button variant="outline" className="mt-4">Back to Vendors</Button></Link>
      </div>
    );
  }

  const handleDelete = async () => {
    await deleteVendor.mutateAsync();
    router.push("/vendors");
  };

  const fields = [
    { label: "Email", value: vendor.email },
    { label: "Contact Name", value: vendor.contact_name },
    { label: "Phone", value: vendor.phone },
    { label: "Website", value: vendor.website },
    { label: "Country", value: vendor.country },
    { label: "Notes", value: vendor.notes },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Link href="/vendors">
            <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight">{vendor.name}</h1>
              <Badge variant="secondary">{vendor.category.replace(/_/g, " ")}</Badge>
            </div>
            <p className="text-sm text-[var(--muted-foreground)]">
              Added {new Date(vendor.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="destructive" size="sm" onClick={handleDelete} disabled={deleteVendor.isPending}>
            <Trash2 className="mr-1 h-3.5 w-3.5" />
            {deleteVendor.isPending ? "Deleting..." : "Delete"}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle>Details</CardTitle></CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-4">
            {fields.map((f) => (
              <div key={f.label}>
                <dt className="text-xs font-medium text-[var(--muted-foreground)]">{f.label}</dt>
                <dd className="text-sm">{f.value || "—"}</dd>
              </div>
            ))}
          </dl>
          {vendor.tags && vendor.tags.length > 0 && (
            <div className="mt-4">
              <dt className="mb-1 text-xs font-medium text-[var(--muted-foreground)]">Tags</dt>
              <div className="flex flex-wrap gap-1">
                {vendor.tags.map((tag) => (
                  <Badge key={tag} variant="outline">{tag}</Badge>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
