"use client";

import { useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { WS_URL } from "@/lib/constants";
import type { Message } from "@/lib/types";

interface WSEvent {
  type: "new_message" | "task_status" | "approval_requested" | "approval_decided";
  data: Record<string, unknown>;
}

export function useWebSocket(threadId: string | undefined) {
  const wsRef = useRef<WebSocket | null>(null);
  const qc = useQueryClient();

  const connect = useCallback(() => {
    if (!threadId) return;

    const ws = new WebSocket(`${WS_URL}/ws/threads/${threadId}`);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      try {
        const event: WSEvent = JSON.parse(evt.data);

        if (event.type === "new_message") {
          // Merge new message into the query cache
          qc.setQueryData(
            ["messages", threadId],
            (old: { pages: { items: Message[]; next_cursor: string | null }[] } | undefined) => {
              if (!old) return old;
              const msg = event.data as unknown as Message;
              const lastPage = old.pages[old.pages.length - 1];
              // Avoid duplicates
              if (lastPage.items.some((m) => m.id === msg.id)) return old;
              return {
                ...old,
                pages: [
                  ...old.pages.slice(0, -1),
                  {
                    ...lastPage,
                    items: [...lastPage.items, msg],
                  },
                ],
              };
            },
          );
        }

        if (event.type === "task_status") {
          qc.invalidateQueries({ queryKey: ["tasks"] });
        }

        if (event.type === "approval_requested" || event.type === "approval_decided") {
          qc.invalidateQueries({ queryKey: ["approvals"] });
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      // Reconnect after 3s
      setTimeout(() => {
        if (wsRef.current === ws) connect();
      }, 3000);
    };

    return ws;
  }, [threadId, qc]);

  useEffect(() => {
    const ws = connect();
    return () => {
      if (ws) {
        wsRef.current = null;
        ws.close();
      }
    };
  }, [connect]);
}
