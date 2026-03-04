"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { VALID_TOOLS } from "@/lib/constants";
import { ApiError } from "@/lib/api-client";
import type { Agent, AgentCreate, AgentUpdate } from "@/lib/types";

interface AgentFormProps {
  mode: "create" | "edit";
  initial?: Partial<AgentCreate>;
  agent?: Agent;
  onSubmit: (data: AgentCreate | AgentUpdate) => Promise<unknown>;
}

export function AgentForm({ mode, initial, agent, onSubmit }: AgentFormProps) {
  const router = useRouter();
  const defaults = agent || initial || {};

  const [name, setName] = useState(defaults.name || "");
  const [rolePrompt, setRolePrompt] = useState(
    ("role_prompt" in (defaults as AgentCreate) ? (defaults as AgentCreate).role_prompt : "") || "",
  );
  const [tools, setTools] = useState<string[]>(defaults.allowed_tools || []);
  const [telegramToken, setTelegramToken] = useState("");
  const [rateLimit, setRateLimit] = useState(
    defaults.rate_limit_per_min?.toString() || "10",
  );
  const [concurrency, setConcurrency] = useState(
    defaults.max_concurrency?.toString() || "3",
  );
  const [isEnabled, setIsEnabled] = useState(agent?.is_enabled ?? true);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const toggleTool = (tool: string) => {
    setTools((prev) =>
      prev.includes(tool) ? prev.filter((t) => t !== tool) : [...prev, tool],
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data: AgentCreate | AgentUpdate = {
        name,
        role_prompt: rolePrompt,
        allowed_tools: tools,
        rate_limit_per_min: parseInt(rateLimit) || 10,
        max_concurrency: parseInt(concurrency) || 3,
        is_enabled: isEnabled,
        ...(telegramToken ? { telegram_bot_token_ref: telegramToken } : {}),
      };
      await onSubmit(data);
      router.push("/agents");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to save agent");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <div className="rounded-md bg-[var(--destructive)]/10 p-3 text-sm text-[var(--destructive)]">
          {error}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Basic Info</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Negotiator Bot"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="role-prompt">Role Prompt</Label>
            <Textarea
              id="role-prompt"
              value={rolePrompt}
              onChange={(e) => setRolePrompt(e.target.value)}
              placeholder="Describe the agent's role, personality, and constraints..."
              rows={8}
              required
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Allowed Tools</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {VALID_TOOLS.map((tool) => (
              <label
                key={tool}
                className="flex cursor-pointer items-center gap-2 rounded-md border border-[var(--border)] p-3 text-sm transition-colors hover:bg-[var(--accent)]"
              >
                <input
                  type="checkbox"
                  checked={tools.includes(tool)}
                  onChange={() => toggleTool(tool)}
                  className="rounded"
                />
                {tool.replace(/_/g, " ")}
              </label>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="rate-limit">Rate limit (per min)</Label>
              <Input
                id="rate-limit"
                type="number"
                min="1"
                max="100"
                value={rateLimit}
                onChange={(e) => setRateLimit(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="concurrency">Max concurrency</Label>
              <Input
                id="concurrency"
                type="number"
                min="1"
                max="20"
                value={concurrency}
                onChange={(e) => setConcurrency(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="telegram-token">Telegram Bot Token (optional)</Label>
            <Input
              id="telegram-token"
              type="password"
              value={telegramToken}
              onChange={(e) => setTelegramToken(e.target.value)}
              placeholder={mode === "edit" ? "Leave blank to keep current" : "Bot token from @BotFather"}
            />
          </div>
          {mode === "edit" && (
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={isEnabled}
                onChange={(e) => setIsEnabled(e.target.checked)}
                className="rounded"
              />
              <span className="text-sm">Agent enabled</span>
            </label>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end gap-3">
        <Button
          type="button"
          variant="outline"
          onClick={() => router.push("/agents")}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={loading}>
          {loading
            ? mode === "create"
              ? "Creating..."
              : "Saving..."
            : mode === "create"
              ? "Create Agent"
              : "Save Changes"}
        </Button>
      </div>
    </form>
  );
}
