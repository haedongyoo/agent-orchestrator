"use client";

import { useState } from "react";
import Link from "next/link";
import { Plus, Search, Trash2, Users } from "lucide-react";
import { useVendors } from "@/hooks/use-vendors";
import { useWorkspace } from "@/providers/workspace-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

export default function VendorsPage() {
  const { workspace } = useWorkspace();
  const { data: vendors, isLoading } = useVendors();
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");

  const filtered = vendors?.filter((v) => {
    const matchSearch = v.name.toLowerCase().includes(search.toLowerCase()) ||
      (v.contact_name?.toLowerCase().includes(search.toLowerCase()) ?? false);
    const matchCategory = !categoryFilter || v.category === categoryFilter;
    return matchSearch && matchCategory;
  });

  const categories = [...new Set(vendors?.map((v) => v.category) || [])];

  if (!workspace) {
    return <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">Select a workspace first.</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Vendors</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            {vendors?.length ?? 0} vendor{vendors?.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link href="/vendors/new">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            New Vendor
          </Button>
        </Link>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <Input
            placeholder="Search vendors..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="h-9 rounded-md border border-[var(--input)] bg-transparent px-3 text-sm"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">Loading vendors...</div>
      ) : filtered?.length === 0 ? (
        <div className="py-20 text-center">
          <Users className="mx-auto mb-4 h-12 w-12 text-[var(--muted-foreground)]" />
          <p className="text-sm text-[var(--muted-foreground)]">
            {search || categoryFilter ? "No vendors match your filters." : "No vendors yet."}
          </p>
          {!search && !categoryFilter && (
            <Link href="/vendors/new">
              <Button variant="outline" className="mt-4">Add your first vendor</Button>
            </Link>
          )}
        </div>
      ) : (
        <div className="rounded-md border border-[var(--border)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--muted)]">
                <th className="px-4 py-3 text-left font-medium">Name</th>
                <th className="px-4 py-3 text-left font-medium">Category</th>
                <th className="px-4 py-3 text-left font-medium">Contact</th>
                <th className="px-4 py-3 text-left font-medium">Email</th>
                <th className="px-4 py-3 text-left font-medium">Country</th>
                <th className="px-4 py-3 text-left font-medium">Tags</th>
              </tr>
            </thead>
            <tbody>
              {filtered?.map((vendor) => (
                <tr key={vendor.id} className="border-b border-[var(--border)] last:border-0">
                  <td className="px-4 py-3">
                    <Link href={`/vendors/${vendor.id}`} className="font-medium hover:underline">
                      {vendor.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant="secondary" className="text-xs">
                      {vendor.category.replace(/_/g, " ")}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-[var(--muted-foreground)]">{vendor.contact_name || "—"}</td>
                  <td className="px-4 py-3 text-[var(--muted-foreground)]">{vendor.email || "—"}</td>
                  <td className="px-4 py-3 text-[var(--muted-foreground)]">{vendor.country || "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {vendor.tags?.slice(0, 3).map((tag) => (
                        <Badge key={tag} variant="outline" className="text-xs">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
