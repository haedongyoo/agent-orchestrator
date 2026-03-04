"use client";

import { useState } from "react";
import Link from "next/link";
import { Plus, Search, LayoutGrid, List } from "lucide-react";
import { useAgents } from "@/hooks/use-agents";
import { useWorkspace } from "@/providers/workspace-provider";
import { AgentCard } from "@/components/agents/agent-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import type { Agent } from "@/lib/types";

export default function AgentsPage() {
  const { workspace } = useWorkspace();
  const { data: agents, isLoading } = useAgents();
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"grid" | "table">("grid");

  const filtered = agents?.filter((a) =>
    a.name.toLowerCase().includes(search.toLowerCase()),
  );

  if (!workspace) {
    return (
      <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">
        Select a workspace to manage agents.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agents</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            {agents?.length ?? 0} agent{agents?.length !== 1 ? "s" : ""} configured
          </p>
        </div>
        <Link href="/agents/new">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            New Agent
          </Button>
        </Link>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <Input
            placeholder="Search agents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <div className="flex rounded-md border border-[var(--border)]">
          <Button
            variant={view === "grid" ? "secondary" : "ghost"}
            size="icon"
            className="h-9 w-9 rounded-r-none"
            onClick={() => setView("grid")}
          >
            <LayoutGrid className="h-4 w-4" />
          </Button>
          <Button
            variant={view === "table" ? "secondary" : "ghost"}
            size="icon"
            className="h-9 w-9 rounded-l-none"
            onClick={() => setView("table")}
          >
            <List className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">
          Loading agents...
        </div>
      ) : filtered?.length === 0 ? (
        <div className="py-20 text-center">
          <p className="text-sm text-[var(--muted-foreground)]">
            {search ? "No agents match your search." : "No agents yet."}
          </p>
          {!search && (
            <Link href="/agents/new">
              <Button variant="outline" className="mt-4">
                Create your first agent
              </Button>
            </Link>
          )}
        </div>
      ) : view === "grid" ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filtered?.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
        </div>
      ) : (
        <AgentTable agents={filtered || []} />
      )}
    </div>
  );
}

function AgentTable({ agents }: { agents: Agent[] }) {
  return (
    <div className="rounded-md border border-[var(--border)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] bg-[var(--muted)]">
            <th className="px-4 py-3 text-left font-medium">Name</th>
            <th className="px-4 py-3 text-left font-medium">Tools</th>
            <th className="px-4 py-3 text-left font-medium">Rate Limit</th>
            <th className="px-4 py-3 text-left font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {agents.map((agent) => (
            <tr key={agent.id} className="border-b border-[var(--border)] last:border-0">
              <td className="px-4 py-3">
                <Link
                  href={`/agents/${agent.id}`}
                  className="font-medium hover:underline"
                >
                  {agent.name}
                </Link>
              </td>
              <td className="px-4 py-3">{agent.allowed_tools.length} tools</td>
              <td className="px-4 py-3">{agent.rate_limit_per_min}/min</td>
              <td className="px-4 py-3">
                <Badge variant={agent.is_enabled ? "default" : "secondary"}>
                  {agent.is_enabled ? "Active" : "Disabled"}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
