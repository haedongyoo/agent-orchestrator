"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useAgent, useUpdateAgent } from "@/hooks/use-agents";
import { AgentForm } from "@/components/agents/agent-form";
import { Button } from "@/components/ui/button";
import type { AgentUpdate } from "@/lib/types";

export default function EditAgentPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const { data: agent, isLoading } = useAgent(agentId);
  const updateAgent = useUpdateAgent(agentId);

  if (isLoading) {
    return (
      <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">
        Loading agent...
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="py-20 text-center">
        <p className="text-sm text-[var(--muted-foreground)]">Agent not found.</p>
        <Link href="/agents">
          <Button variant="outline" className="mt-4">Back to Agents</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-3">
        <Link href={`/agents/${agentId}`}>
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Edit {agent.name}</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            Update agent configuration
          </p>
        </div>
      </div>

      <AgentForm
        mode="edit"
        agent={agent}
        onSubmit={(data) => updateAgent.mutateAsync(data as AgentUpdate)}
      />
    </div>
  );
}
