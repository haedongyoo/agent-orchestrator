"use client";

import { useWorkspace } from "@/providers/workspace-provider";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Bot, MessageSquare, CheckCircle, Users } from "lucide-react";

export default function DashboardPage() {
  const { workspace } = useWorkspace();

  if (!workspace) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <h2 className="text-lg font-semibold">No workspace selected</h2>
        <p className="mt-2 text-sm text-[var(--muted-foreground)]">
          Create a workspace to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Overview for {workspace.name}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <SummaryCard icon={Bot} label="Active Agents" value="--" />
        <SummaryCard icon={MessageSquare} label="Open Threads" value="--" />
        <SummaryCard icon={CheckCircle} label="Pending Approvals" value="--" />
        <SummaryCard icon={Users} label="Vendors" value="--" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-[var(--muted-foreground)]">
            Dashboard statistics and activity feed will be populated in PR 2.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function SummaryCard({
  icon: Icon,
  label,
  value,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <Icon className="h-4 w-4 text-[var(--muted-foreground)]" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  );
}
