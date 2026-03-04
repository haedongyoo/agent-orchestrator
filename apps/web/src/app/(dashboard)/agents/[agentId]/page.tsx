"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Settings, ArrowLeft } from "lucide-react";
import { useAgent } from "@/hooks/use-agents";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LLMConfigPanel } from "@/components/agents/llm-config-panel";
import { ContainerStatus } from "@/components/agents/container-status";

type Tab = "overview" | "llm" | "container";

export default function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const { data: agent, isLoading } = useAgent(agentId);
  const [tab, setTab] = useState<Tab>("overview");

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

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "llm", label: "LLM Config" },
    { id: "container", label: "Container" },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Link href="/agents">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight">{agent.name}</h1>
              <Badge variant={agent.is_enabled ? "default" : "secondary"}>
                {agent.is_enabled ? "Active" : "Disabled"}
              </Badge>
            </div>
            <p className="text-sm text-[var(--muted-foreground)]">
              {agent.allowed_tools.length} tools &middot; {agent.rate_limit_per_min}/min &middot; {agent.max_concurrency} concurrent
            </p>
          </div>
        </div>
        <Link href={`/agents/${agentId}/edit`}>
          <Button variant="outline">
            <Settings className="mr-2 h-4 w-4" />
            Edit
          </Button>
        </Link>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-[var(--border)]">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              tab === t.id
                ? "border-b-2 border-[var(--primary)] text-[var(--foreground)]"
                : "text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "overview" && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Role Prompt</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--muted-foreground)]">
                {agent.role_prompt}
              </pre>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Allowed Tools</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {agent.allowed_tools.map((tool) => (
                  <Badge key={tool} variant="secondary">
                    {tool.replace(/_/g, " ")}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {tab === "llm" && <LLMConfigPanel agentId={agentId} />}
      {tab === "container" && <ContainerStatus agentId={agentId} />}
    </div>
  );
}
