"use client";

import { useState } from "react";
import { useApprovals } from "@/hooks/use-approvals";
import { useWorkspace } from "@/providers/workspace-provider";
import { ApprovalCard } from "@/components/approvals/approval-card";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { CheckCircle } from "lucide-react";

type TabStatus = "pending" | "approved" | "rejected" | undefined;

const tabs: { id: TabStatus; label: string }[] = [
  { id: undefined, label: "All" },
  { id: "pending", label: "Pending" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
];

export default function ApprovalsPage() {
  const { workspace } = useWorkspace();
  const [activeTab, setActiveTab] = useState<TabStatus>("pending");
  const { data: approvals, isLoading } = useApprovals(activeTab);

  if (!workspace) {
    return (
      <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">
        Select a workspace first.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Approvals</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Review and manage agent approval requests
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-[var(--border)]">
        {tabs.map((tab) => (
          <button
            key={tab.label}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "border-b-2 border-[var(--primary)] text-[var(--foreground)]"
                : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardHeader><Skeleton className="h-5 w-40" /></CardHeader>
              <CardContent className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-1/2" />
                <Skeleton className="h-8 w-24 mt-2" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : approvals?.length === 0 ? (
        <div className="py-20 text-center">
          <CheckCircle className="mx-auto mb-4 h-12 w-12 text-[var(--muted-foreground)]" />
          <p className="text-sm text-[var(--muted-foreground)]">
            {activeTab === "pending"
              ? "No pending approvals."
              : "No approvals found."}
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {approvals?.map((approval) => (
            <ApprovalCard key={approval.id} approval={approval} />
          ))}
        </div>
      )}
    </div>
  );
}
