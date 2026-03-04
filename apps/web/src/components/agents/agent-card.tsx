"use client";

import Link from "next/link";
import { Bot, Settings } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Agent } from "@/lib/types";

export function AgentCard({ agent }: { agent: Agent }) {
  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--primary)]/10">
            <Bot className="h-5 w-5 text-[var(--primary)]" />
          </div>
          <div>
            <CardTitle className="text-base">
              <Link href={`/agents/${agent.id}`} className="hover:underline">
                {agent.name}
              </Link>
            </CardTitle>
            <p className="text-xs text-[var(--muted-foreground)]">
              {agent.allowed_tools.length} tools
            </p>
          </div>
        </div>
        <Badge variant={agent.is_enabled ? "default" : "secondary"}>
          {agent.is_enabled ? "Active" : "Disabled"}
        </Badge>
      </CardHeader>
      <CardContent>
        <p className="mb-3 line-clamp-2 text-sm text-[var(--muted-foreground)]">
          {agent.role_prompt.substring(0, 120)}...
        </p>
        <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
          <span>{agent.rate_limit_per_min}/min &middot; {agent.max_concurrency} concurrent</span>
          <Link href={`/agents/${agent.id}/edit`}>
            <Button variant="ghost" size="icon" className="h-7 w-7">
              <Settings className="h-3.5 w-3.5" />
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
