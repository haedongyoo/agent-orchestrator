"use client";

import { Button } from "@/components/ui/button";
import { API_URL } from "@/lib/constants";

const providers = [
  { id: "google", label: "Google" },
  { id: "github", label: "GitHub" },
  { id: "microsoft", label: "Microsoft" },
] as const;

export function SsoButtons() {
  const handleSso = (provider: string) => {
    // The callback will redirect back to /sso/callback?token=... via the redirect_uri param
    const callbackUrl = `${window.location.origin}/sso/callback`;
    // We pass redirect_uri as a query param on the SSO initiation endpoint
    // The backend's SSO callback will redirect to this URL with the token
    window.location.href = `${API_URL}/api/auth/sso/${provider}?redirect_uri=${encodeURIComponent(callbackUrl)}`;
  };

  return (
    <div className="grid grid-cols-3 gap-3">
      {providers.map((p) => (
        <Button
          key={p.id}
          variant="outline"
          size="sm"
          onClick={() => handleSso(p.id)}
        >
          {p.label}
        </Button>
      ))}
    </div>
  );
}
