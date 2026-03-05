"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Bot,
  MessageSquare,
  CheckCircle,
  Users,
  Settings,
  Plus,
  Search,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface Command {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  href?: string;
  action?: () => void;
  group: string;
}

const commands: Command[] = [
  { id: "dashboard", label: "Go to Dashboard", icon: LayoutDashboard, href: "/dashboard", group: "Navigation" },
  { id: "agents", label: "Go to Agents", icon: Bot, href: "/agents", group: "Navigation" },
  { id: "threads", label: "Go to Threads", icon: MessageSquare, href: "/threads", group: "Navigation" },
  { id: "approvals", label: "Go to Approvals", icon: CheckCircle, href: "/approvals", group: "Navigation" },
  { id: "vendors", label: "Go to Vendors", icon: Users, href: "/vendors", group: "Navigation" },
  { id: "settings", label: "Go to Settings", icon: Settings, href: "/settings", group: "Navigation" },
  { id: "new-agent", label: "Create New Agent", icon: Plus, href: "/agents/new", group: "Actions" },
  { id: "new-vendor", label: "Create New Vendor", icon: Plus, href: "/vendors/new", group: "Actions" },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = commands.filter((cmd) =>
    cmd.label.toLowerCase().includes(query.toLowerCase()),
  );

  const groups = [...new Set(filtered.map((c) => c.group))];

  const handleSelect = useCallback(
    (cmd: Command) => {
      setOpen(false);
      setQuery("");
      if (cmd.href) router.push(cmd.href);
      if (cmd.action) cmd.action();
    },
    [router],
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
        setQuery("");
        setSelectedIndex(0);
      }
      if (e.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  const handleKeyNav = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && filtered[selectedIndex]) {
      e.preventDefault();
      handleSelect(filtered[selectedIndex]);
    }
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/50"
        onClick={() => setOpen(false)}
      />

      {/* Dialog */}
      <div className="fixed inset-x-0 top-[20%] z-50 mx-auto w-full max-w-lg">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--background)] shadow-2xl">
          {/* Search input */}
          <div className="flex items-center border-b border-[var(--border)] px-4">
            <Search className="mr-2 h-4 w-4 shrink-0 text-[var(--muted-foreground)]" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyNav}
              placeholder="Type a command or search..."
              className="flex h-12 w-full bg-transparent text-sm outline-none placeholder:text-[var(--muted-foreground)]"
            />
            <kbd className="ml-2 shrink-0 rounded border border-[var(--border)] bg-[var(--muted)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--muted-foreground)]">
              ESC
            </kbd>
          </div>

          {/* Results */}
          <div className="max-h-72 overflow-y-auto p-2">
            {filtered.length === 0 ? (
              <p className="py-6 text-center text-sm text-[var(--muted-foreground)]">
                No results found.
              </p>
            ) : (
              groups.map((group) => (
                <div key={group}>
                  <p className="px-2 py-1.5 text-xs font-medium text-[var(--muted-foreground)]">
                    {group}
                  </p>
                  {filtered
                    .filter((c) => c.group === group)
                    .map((cmd) => {
                      const globalIdx = filtered.indexOf(cmd);
                      return (
                        <button
                          key={cmd.id}
                          onClick={() => handleSelect(cmd)}
                          className={cn(
                            "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                            globalIdx === selectedIndex
                              ? "bg-[var(--accent)] text-[var(--accent-foreground)]"
                              : "text-[var(--foreground)] hover:bg-[var(--accent)]",
                          )}
                        >
                          <cmd.icon className="h-4 w-4" />
                          {cmd.label}
                        </button>
                      );
                    })}
                </div>
              ))
            )}
          </div>

          {/* Footer hint */}
          <div className="flex items-center justify-between border-t border-[var(--border)] px-4 py-2">
            <span className="text-xs text-[var(--muted-foreground)]">
              Navigate with arrow keys
            </span>
            <span className="text-xs text-[var(--muted-foreground)]">
              Press Enter to select
            </span>
          </div>
        </div>
      </div>
    </>
  );
}
