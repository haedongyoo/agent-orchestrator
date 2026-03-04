"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { Message } from "@/lib/types";

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.sender_type === "user";
  const isSystem = message.sender_type === "system";

  if (isSystem) {
    return (
      <div className="flex justify-center py-1">
        <span className="rounded-full bg-[var(--muted)] px-3 py-1 text-xs text-[var(--muted-foreground)]">
          {message.content}
        </span>
      </div>
    );
  }

  return (
    <div className={cn("flex gap-2", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-2",
          isUser
            ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
            : "bg-[var(--muted)] text-[var(--foreground)]",
        )}
      >
        <div className="flex items-center gap-2 pb-1">
          <span className="text-xs font-medium opacity-70">
            {message.sender_type}
          </span>
          {message.channel !== "web" && (
            <Badge variant="outline" className="h-4 px-1 text-[10px]">
              {message.channel}
            </Badge>
          )}
        </div>
        <p className="whitespace-pre-wrap text-sm">{message.content}</p>
        <p className="mt-1 text-[10px] opacity-50">
          {new Date(message.created_at).toLocaleTimeString()}
        </p>
      </div>
    </div>
  );
}
