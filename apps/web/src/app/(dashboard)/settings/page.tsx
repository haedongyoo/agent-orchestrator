"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useWorkspace } from "@/providers/workspace-provider";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ApiError } from "@/lib/api-client";
import type { Workspace, WorkspaceUpdate } from "@/lib/types";
import Link from "next/link";

export default function SettingsPage() {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();

  const [name, setName] = useState(workspace?.name || "");
  const [timezone, setTimezone] = useState(workspace?.timezone || "UTC");
  const [langPref, setLangPref] = useState(workspace?.language_pref || "en");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const updateWorkspace = useMutation({
    mutationFn: (data: WorkspaceUpdate) =>
      api.put<Workspace>(`/api/workspaces/${workspace!.id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workspaces"] });
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : "Failed to update");
    },
  });

  if (!workspace) {
    return <div className="py-20 text-center text-sm text-[var(--muted-foreground)]">Select a workspace first.</div>;
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Workspace configuration
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Workspace</CardTitle>
          <CardDescription>General workspace settings</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <div className="rounded-md bg-[var(--destructive)]/10 p-3 text-sm text-[var(--destructive)]">{error}</div>
          )}
          {success && (
            <div className="rounded-md bg-green-500/10 p-3 text-sm text-green-600">Settings saved.</div>
          )}
          <div className="space-y-2">
            <Label htmlFor="ws-name">Name</Label>
            <Input id="ws-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="tz">Timezone</Label>
              <Input id="tz" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lang">Language Preference</Label>
              <Input id="lang" value={langPref} onChange={(e) => setLangPref(e.target.value)} />
            </div>
          </div>
          <Button
            onClick={() => updateWorkspace.mutate({ name, timezone, language_pref: langPref })}
            disabled={updateWorkspace.isPending}
          >
            {updateWorkspace.isPending ? "Saving..." : "Save Changes"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Email Accounts</CardTitle>
          <CardDescription>Shared email accounts for agents</CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/settings/email">
            <Button variant="outline">Manage Email Accounts</Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
