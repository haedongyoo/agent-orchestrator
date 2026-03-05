"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, XCircle } from "lucide-react";
import { useTask, useCancelTask } from "@/hooks/use-tasks";
import { StepTimeline } from "@/components/tasks/step-timeline";
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

export default function TaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const { data: task, isLoading } = useTask(taskId);
  const cancelTask = useCancelTask(taskId);

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

      <div>
        <h2 className="mb-4 text-lg font-semibold">Steps</h2>
        <StepTimeline taskId={taskId} />
      </div>
    </div>
  );
}
