"use client";

import { useEffect, useRef, useState } from "react";
import { useMessages, usePostMessage } from "@/hooks/use-messages";
import { useWebSocket } from "@/hooks/use-websocket";
import { MessageBubble } from "./message-bubble";
import { MessageInput } from "./message-input";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

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
  const [waitingForAgent, setWaitingForAgent] = useState(false);

  // Connect WebSocket for real-time updates (primary message delivery)
  useWebSocket(threadId);

  // Auto-scroll to bottom on new messages
  const allMessages = data?.pages.flatMap((p) => p.items) ?? [];
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [allMessages.length]);

  // Detect when an agent message arrives → stop waiting
  useEffect(() => {
    if (waitingForAgent && allMessages.length > 0) {
      const lastMsg = allMessages[allMessages.length - 1];
      if (lastMsg.sender_type === "agent") {
        setWaitingForAgent(false);
      }
    }
  }, [allMessages, waitingForAgent]);

  const handleSend = (content: string) => {
    postMessage.mutate(
      { content, channel: "web" },
      {
        onSuccess: () => {
          setWaitingForAgent(true);
        },
      },
    );
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

        {/* Sending indicator */}
        {postMessage.isPending && (
          <div className="mt-3 flex justify-end">
            <div className="flex items-center gap-2 rounded-2xl bg-[var(--primary)] px-4 py-2 text-[var(--primary-foreground)] opacity-60">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span className="text-sm">Sending...</span>
            </div>
          </div>
        )}

        {/* Bot thinking indicator */}
        {waitingForAgent && !postMessage.isPending && (
          <div className="mt-3 flex justify-start">
            <div className="flex items-center gap-2 rounded-2xl bg-[var(--muted)] px-4 py-2 text-[var(--muted-foreground)]">
              <div className="flex gap-1">
                <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:0ms]" />
                <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:150ms]" />
                <span className="inline-block h-2 w-2 animate-bounce rounded-full bg-current [animation-delay:300ms]" />
              </div>
              <span className="text-sm">Agent is thinking...</span>
            </div>
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
