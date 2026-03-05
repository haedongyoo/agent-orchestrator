"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Plus } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useWorkspace } from "@/providers/workspace-provider";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ApiError } from "@/lib/api-client";
import type { SharedEmailAccount, SharedEmailCreate } from "@/lib/types";

export default function EmailSettingsPage() {
  const { workspace } = useWorkspace();
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);

  const { data: accounts, isLoading } = useQuery({
    queryKey: ["shared-emails", workspace?.id],
    queryFn: () =>
      api.get<SharedEmailAccount[]>(`/api/workspaces/${workspace!.id}/shared-email`),
    enabled: !!workspace,
  });

  const [provider, setProvider] = useState("imap");
  const [credRef, setCredRef] = useState("");
  const [fromAlias, setFromAlias] = useState("");
  const [signature, setSignature] = useState("");
  const [error, setError] = useState("");

  const addEmail = useMutation({
    mutationFn: (data: SharedEmailCreate) =>
      api.post<SharedEmailAccount>(`/api/workspaces/${workspace!.id}/shared-email`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["shared-emails", workspace?.id] });
      setShowAdd(false);
      setCredRef("");
      setFromAlias("");
      setSignature("");
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.detail : "Failed to add email account");
    },
  });

  if (!workspace) return null;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/settings">
          <Button variant="ghost" size="icon"><ArrowLeft className="h-4 w-4" /></Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Email Accounts</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            Shared email accounts used by agents
          </p>
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-[var(--muted-foreground)]">Loading...</p>
      ) : accounts && accounts.length > 0 ? (
        <div className="space-y-3">
          {accounts.map((acct) => (
            <Card key={acct.id}>
              <CardContent className="flex items-center justify-between py-4">
                <div>
                  <p className="font-medium">{acct.from_alias}</p>
                  <p className="text-xs text-[var(--muted-foreground)]">{acct.provider_type}</p>
                </div>
                <Badge variant={acct.is_active ? "default" : "secondary"}>
                  {acct.is_active ? "Active" : "Inactive"}
                </Badge>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="py-8 text-center text-sm text-[var(--muted-foreground)]">
            No email accounts configured.
          </CardContent>
        </Card>
      )}

      {!showAdd ? (
        <Button onClick={() => setShowAdd(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Email Account
        </Button>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Add Email Account</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {error && (
              <div className="rounded-md bg-[var(--destructive)]/10 p-3 text-sm text-[var(--destructive)]">{error}</div>
            )}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Provider</Label>
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  className="flex h-9 w-full rounded-md border border-[var(--input)] bg-transparent px-3 py-1 text-sm"
                >
                  <option value="imap">IMAP</option>
                  <option value="gmail">Gmail</option>
                  <option value="graph">Microsoft Graph</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label>From Alias</Label>
                <Input value={fromAlias} onChange={(e) => setFromAlias(e.target.value)} placeholder="noreply@company.com" />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Credentials Reference</Label>
              <Input value={credRef} onChange={(e) => setCredRef(e.target.value)} placeholder="Vault/KMS reference" />
            </div>
            <div className="space-y-2">
              <Label>Signature Template (optional)</Label>
              <Input value={signature} onChange={(e) => setSignature(e.target.value)} placeholder="HTML signature" />
            </div>
            <div className="flex gap-2">
              <Button
                onClick={() =>
                  addEmail.mutate({
                    provider_type: provider,
                    credentials_ref: credRef,
                    from_alias: fromAlias,
                    signature_template: signature || undefined,
                  })
                }
                disabled={addEmail.isPending || !credRef || !fromAlias}
              >
                {addEmail.isPending ? "Adding..." : "Add Account"}
              </Button>
              <Button variant="ghost" onClick={() => setShowAdd(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
