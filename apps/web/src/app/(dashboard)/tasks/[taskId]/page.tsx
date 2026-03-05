"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, XCircle } from "lucide-react";
import { useTask, useCancelTask } from "@/hooks/use-tasks";
import { useTaskTrace } from "@/hooks/use-task-trace";
import { StepTimeline } from "@/components/tasks/step-timeline";
import { TraceEventRow } from "@/components/tasks/trace-event";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const statusVariant: Record<string, "default" | "secondary" | "destructive"> = {
  queued: "secondary",
  running: "default",
  blocked: "secondary",
  needs_approval: "secondary",
  done: "default",
  failed: "destructive",
};

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`;
  return String(n);
}

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const { data: task, isLoading } = useTask(taskId);
  const cancelTask = useCancelTask(taskId);
  const { data: trace } = useTaskTrace(taskId);
  const [activeTab, setActiveTab] = useState<"steps" | "trace">("steps");

  if (isLoading) {
    return (
      <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">
        Loading task...
      </div>
    );
  }

  if (!task) {
    return (
      <div className="py-20 text-center">
        <p className="text-sm text-[var(--muted-foreground)]">Task not found.</p>
      </div>
    );
  }

  const canCancel = ["queued", "running", "blocked", "needs_approval"].includes(task.status);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Link href={`/threads/${task.thread_id}`}>
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight">Task</h1>
              <Badge variant={statusVariant[task.status] || "secondary"}>
                {task.status}
              </Badge>
            </div>
            <p className="text-sm text-[var(--muted-foreground)]">
              Created {new Date(task.created_at).toLocaleString()}
            </p>
          </div>
        </div>
        {canCancel && (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => cancelTask.mutate()}
            disabled={cancelTask.isPending}
          >
            <XCircle className="mr-2 h-4 w-4" />
            {cancelTask.isPending ? "Cancelling..." : "Cancel Task"}
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Objective</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm">{task.objective}</p>
        </CardContent>
      </Card>

      {/* Summary bar */}
      {trace && (trace.total_tokens > 0 || trace.total_duration_ms > 0) && (
        <div className="flex gap-4 text-xs text-[var(--muted-foreground)]">
          <span>Steps: {trace.steps.length}</span>
          <span>Duration: {(trace.total_duration_ms / 1000).toFixed(1)}s</span>
          <span>Tokens: {formatTokens(trace.total_tokens)}</span>
        </div>
      )}

      {/* Tab selector */}
      <div className="flex gap-1 border-b border-[var(--border)]">
        <button
          onClick={() => setActiveTab("steps")}
          className={`px-3 py-2 text-sm font-medium ${
            activeTab === "steps"
              ? "border-b-2 border-[var(--foreground)] text-[var(--foreground)]"
              : "text-[var(--muted-foreground)]"
          }`}
        >
          Steps
        </button>
        <button
          onClick={() => setActiveTab("trace")}
          className={`px-3 py-2 text-sm font-medium ${
            activeTab === "trace"
              ? "border-b-2 border-[var(--foreground)] text-[var(--foreground)]"
              : "text-[var(--muted-foreground)]"
          }`}
        >
          Trace
        </button>
      </div>

      {activeTab === "steps" ? (
        <StepTimeline taskId={taskId} />
      ) : (
        <div className="space-y-4">
          {trace && trace.steps.length > 0 ? (
            trace.steps.map((sw) => (
              <Card key={sw.step.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-2 text-sm">
                    <Badge variant="secondary">{sw.step.step_type}</Badge>
                    <Badge
                      variant={sw.step.status === "done" ? "default" : sw.step.status === "failed" ? "destructive" : "secondary"}
                    >
                      {sw.step.status}
                    </Badge>
                    {sw.step.duration_ms != null && (
                      <span className="text-xs text-[var(--muted-foreground)]">
                        {(sw.step.duration_ms / 1000).toFixed(1)}s
                      </span>
                    )}
                    {sw.step.agent_model && (
                      <span className="text-[10px] text-[var(--muted-foreground)]">
                        {sw.step.agent_model}
                      </span>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  {sw.traces.length > 0 ? (
                    <div className="divide-y divide-[var(--border)]">
                      {sw.traces.map((evt) => (
                        <TraceEventRow key={evt.id} event={evt} />
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-[var(--muted-foreground)]">No trace events.</p>
                  )}
                </CardContent>
              </Card>
            ))
          ) : (
            <p className="text-sm text-[var(--muted-foreground)]">No trace data available.</p>
          )}
        </div>
      )}
    </div>
  );
}
