"use client";

import { useEffect, useRef } from "react";
import { useMessages, usePostMessage } from "@/hooks/use-messages";
import { useWebSocket } from "@/hooks/use-websocket";
import { MessageBubble } from "./message-bubble";
import { MessageInput } from "./message-input";
import { Button } from "@/components/ui/button";

interface ChatViewProps {
  threadId: string;
  disabled?: boolean;
}

export function ChatView({ threadId, disabled = false }: ChatViewProps) {
  const {
    data,
    isLoading,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useMessages(threadId);
  const postMessage = usePostMessage(threadId);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Connect WebSocket for real-time updates
  useWebSocket(threadId);

  // Auto-scroll to bottom on new messages
  const allMessages = data?.pages.flatMap((p) => p.items) ?? [];
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [allMessages.length]);

  const handleSend = (content: string) => {
    postMessage.mutate({ content, channel: "web" });
  };

  return (
    <div className="flex h-full flex-col">
      {/* Messages area */}
      <div className="flex-1 overflow-auto p-4">
        {/* Load more button */}
        {hasNextPage && (
          <div className="mb-4 text-center">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
            >
              {isFetchingNextPage ? "Loading..." : "Load older messages"}
            </Button>
          </div>
        )}

        {isLoading ? (
          <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">
            Loading messages...
          </div>
        ) : allMessages.length === 0 ? (
          <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">
            No messages yet. Send the first message below.
          </div>
        ) : (
          <div className="space-y-3">
            {allMessages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      {disabled ? (
        <div className="border-t border-[var(--border)] p-4 text-center text-sm text-[var(--muted-foreground)]">
          This thread is closed.
        </div>
      ) : (
        <MessageInput onSend={handleSend} disabled={postMessage.isPending} />
      )}
    </div>
  );
}
