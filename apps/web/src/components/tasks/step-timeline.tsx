"use client";

import { useTaskSteps } from "@/hooks/use-tasks";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { TaskStep } from "@/lib/types";

const statusColors: Record<string, string> = {
  queued: "bg-zinc-400",
  running: "bg-blue-500",
  done: "bg-green-500",
  failed: "bg-red-500",
};

export function StepTimeline({ taskId }: { taskId: string }) {
  const { data: steps, isLoading } = useTaskSteps(taskId);

  if (isLoading) {
    return <p className="text-sm text-[var(--muted-foreground)]">Loading steps...</p>;
  }

  if (!steps || steps.length === 0) {
    return <p className="text-sm text-[var(--muted-foreground)]">No steps yet.</p>;
  }

  return (
    <div className="relative space-y-4">
      {/* Vertical line */}
      <div className="absolute left-3 top-0 h-full w-px bg-[var(--border)]" />

      {steps.map((step) => (
        <StepCard key={step.id} step={step} />
      ))}
    </div>
  );
}

function StepCard({ step }: { step: TaskStep }) {
  return (
    <div className="relative flex gap-4 pl-8">
      {/* Dot */}
      <div
        className={`absolute left-1.5 top-4 h-3 w-3 rounded-full border-2 border-[var(--background)] ${statusColors[step.status] || "bg-zinc-400"}`}
      />

      <Card className="flex-1">
        <CardContent className="p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Badge variant="secondary" className="text-xs">
                {step.step_type}
              </Badge>
              <Badge
                variant={step.status === "done" ? "default" : step.status === "failed" ? "destructive" : "secondary"}
                className="text-xs"
              >
                {step.status}
              </Badge>
            </div>
            <span className="text-xs text-[var(--muted-foreground)]">
              {new Date(step.created_at).toLocaleTimeString()}
            </span>
          </div>

          {step.tool_call && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                Tool Call
              </summary>
              <pre className="mt-1 overflow-auto rounded bg-[var(--muted)] p-2 text-xs">
                {JSON.stringify(step.tool_call, null, 2)}
              </pre>
            </details>
          )}

          {step.result && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
                Result
              </summary>
              <pre className="mt-1 overflow-auto rounded bg-[var(--muted)] p-2 text-xs">
                {JSON.stringify(step.result, null, 2)}
              </pre>
            </details>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
