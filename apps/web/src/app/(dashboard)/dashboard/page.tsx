"use client";

import { useState } from "react";
import Link from "next/link";
import { useWorkspace } from "@/providers/workspace-provider";
import { useAgents } from "@/hooks/use-agents";
import { useThreads } from "@/hooks/use-threads";
import { useVendors } from "@/hooks/use-vendors";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AgentCard } from "@/components/agents/agent-card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Bot, MessageSquare, CheckCircle, Users, Plus } from "lucide-react";

export default function DashboardPage() {
  const { workspace } = useWorkspace();
  const { data: agents, isLoading: loadingAgents } = useAgents();
  const { data: threads, isLoading: loadingThreads } = useThreads();
  const { data: vendors, isLoading: loadingVendors } = useVendors();

  if (!workspace) {
    return <CreateWorkspacePrompt />;
  }

  const activeAgents = agents?.filter((a) => a.is_enabled) || [];
  const openThreads = threads?.filter((t) => t.status === "open") || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Overview for {workspace.name}
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {loadingAgents ? (
          <SkeletonCard />
        ) : (
          <SummaryCard icon={Bot} label="Active Agents" value={String(activeAgents.length)} href="/agents" />
        )}
        {loadingThreads ? (
          <SkeletonCard />
        ) : (
          <SummaryCard icon={MessageSquare} label="Open Threads" value={String(openThreads.length)} href="/threads" />
        )}
        <SummaryCard icon={CheckCircle} label="Pending Approvals" value="--" href="/approvals" />
        {loadingVendors ? (
          <SkeletonCard />
        ) : (
          <SummaryCard icon={Users} label="Vendors" value={String(vendors?.length ?? 0)} href="/vendors" />
        )}
      </div>

      {/* Agent grid */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Agents</h2>
          <Link href="/agents/new">
            <Button size="sm" variant="outline">
              <Plus className="mr-1 h-3.5 w-3.5" />
              New
            </Button>
          </Link>
        </div>
        {loadingAgents ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Card key={i}>
                <CardHeader><Skeleton className="h-5 w-32" /></CardHeader>
                <CardContent className="space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-2/3" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : agents && agents.length > 0 ? (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {agents.slice(0, 6).map((agent) => (
              <AgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="py-8 text-center text-sm text-[var(--muted-foreground)]">
              No agents configured yet.{" "}
              <Link href="/agents/new" className="underline">
                Create one
              </Link>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Recent threads */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Recent Threads</h2>
          <Link href="/threads">
            <Button size="sm" variant="outline">View all</Button>
          </Link>
        </div>
        {loadingThreads ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 w-full rounded-lg" />
            ))}
          </div>
        ) : threads && threads.length > 0 ? (
          <div className="space-y-2">
            {threads.slice(0, 5).map((thread) => (
              <Link
                key={thread.id}
                href={`/threads/${thread.id}`}
                className="flex items-center justify-between rounded-lg border border-[var(--border)] p-3 transition-colors hover:bg-[var(--accent)]"
              >
                <span className="text-sm font-medium">{thread.title}</span>
                <Badge variant={thread.status === "open" ? "default" : "secondary"}>
                  {thread.status}
                </Badge>
              </Link>
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="py-8 text-center text-sm text-[var(--muted-foreground)]">
              No threads yet.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-4 rounded" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-7 w-12" />
      </CardContent>
    </Card>
  );
}

function CreateWorkspacePrompt() {
  const { createWorkspace } = useWorkspace();
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setCreating(true);
    try {
      await createWorkspace({ name: name.trim() });
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center py-20">
      <h2 className="text-lg font-semibold">No workspace yet</h2>
      <p className="mt-2 mb-4 text-sm text-[var(--muted-foreground)]">
        Create a workspace to get started.
      </p>
      <div className="flex gap-2 w-full max-w-sm">
        <Input
          placeholder="Workspace name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
        />
        <Button onClick={handleCreate} disabled={creating || !name.trim()}>
          {creating ? "Creating..." : "Create"}
        </Button>
      </div>
    </div>
  );
}

function SummaryCard({
  icon: Icon,
  label,
  value,
  href,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  href: string;
}) {
  return (
    <Link href={href}>
      <Card className="transition-shadow hover:shadow-md">
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">{label}</CardTitle>
          <Icon className="h-4 w-4 text-[var(--muted-foreground)]" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{value}</div>
        </CardContent>
      </Card>
    </Link>
  );
}
