"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApproveApproval, useRejectApproval } from "@/hooks/use-approvals";
import type { Approval } from "@/lib/types";

const statusVariant: Record<string, "default" | "secondary" | "destructive"> = {
  pending: "secondary",
  approved: "default",
  rejected: "destructive",
};

export function ApprovalCard({ approval }: { approval: Approval }) {
  const [note, setNote] = useState("");
  const [showActions, setShowActions] = useState(false);
  const approveAction = useApproveApproval();
  const rejectAction = useRejectApproval();

  const isPending = approval.status === "pending";

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <CardTitle className="text-base">
            {approval.approval_type.replace(/_/g, " ")}
          </CardTitle>
          <Badge variant={statusVariant[approval.status] || "secondary"}>
            {approval.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {approval.reason && (
          <p className="text-sm text-[var(--muted-foreground)]">{approval.reason}</p>
        )}

        {Object.keys(approval.scope).length > 0 && (
          <details>
            <summary className="cursor-pointer text-xs text-[var(--muted-foreground)]">
              Scope details
            </summary>
            <pre className="mt-1 overflow-auto rounded bg-[var(--muted)] p-2 text-xs">
              {JSON.stringify(approval.scope, null, 2)}
            </pre>
          </details>
        )}

        {isPending && !showActions && (
          <Button size="sm" variant="outline" onClick={() => setShowActions(true)}>
            Review
          </Button>
        )}

        {isPending && showActions && (
          <div className="space-y-3 rounded-md border border-[var(--border)] p-3">
            <Input
              placeholder="Add a note (optional)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => approveAction.mutate({ id: approval.id, note: note || undefined })}
                disabled={approveAction.isPending}
              >
                {approveAction.isPending ? "Approving..." : "Approve"}
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => rejectAction.mutate({ id: approval.id, note: note || undefined })}
                disabled={rejectAction.isPending}
              >
                {rejectAction.isPending ? "Rejecting..." : "Reject"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setShowActions(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
