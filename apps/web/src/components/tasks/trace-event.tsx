"use client";

import { Badge } from "@/components/ui/badge";
import type { TraceEvent } from "@/lib/types";

const eventColors: Record<string, string> = {
  started: "bg-blue-500",
  llm_request: "bg-purple-500",
  llm_response: "bg-purple-400",
  tool_call: "bg-amber-500",
  tool_result: "bg-amber-400",
  completed: "bg-green-500",
  error: "bg-red-500",
  rate_limit: "bg-orange-500",
  enqueued: "bg-zinc-400",
};

const eventLabels: Record<string, string> = {
  started: "Started",
  llm_request: "LLM Request",
  llm_response: "LLM Response",
  tool_call: "Tool Call",
  tool_result: "Tool Result",
  completed: "Completed",
  error: "Error",
  rate_limit: "Rate Limit",
  enqueued: "Enqueued",
};

export function TraceEventRow({ event }: { event: TraceEvent }) {
  const label = eventLabels[event.event_type] || event.event_type;
  const color = eventColors[event.event_type] || "bg-zinc-400";

  return (
    <div className="flex items-start gap-3 py-1.5 text-xs">
      <span className="w-20 shrink-0 text-[var(--muted-foreground)]">
        {new Date(event.timestamp).toLocaleTimeString()}
      </span>
      <Badge variant="secondary" className={`text-white ${color} shrink-0 text-[10px]`}>
        {label}
      </Badge>
      <div className="min-w-0 flex-1">
        {event.detail && (
          <details>
            <summary className="cursor-pointer text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
              {_summaryText(event)}
            </summary>
            <pre className="mt-1 overflow-auto rounded bg-[var(--muted)] p-2 text-[10px]">
              {JSON.stringify(event.detail, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
}

function _summaryText(event: TraceEvent): string {
  const d = event.detail || {};
  switch (event.event_type) {
    case "llm_response":
      return `${d.latency_ms ?? "?"}ms | ${d.input_tokens ?? 0} in / ${d.output_tokens ?? 0} out | ${d.finish_reason ?? ""}`;
    case "tool_call":
      return `${d.tool ?? "unknown"}`;
    case "tool_result":
      return `${d.tool ?? "unknown"} — ${d.latency_ms ?? "?"}ms${d.success === false ? " (failed)" : ""}`;
    case "rate_limit":
      return `${d.reason ?? ""} — wait ${d.wait_seconds ?? "?"}s`;
    case "error":
      return `${(d.error as string)?.slice(0, 80) ?? "unknown error"}`;
    case "completed":
      return `${d.duration_ms ?? "?"}ms total`;
    default:
      return Object.keys(d).length > 0 ? JSON.stringify(d).slice(0, 60) : "";
  }
}
