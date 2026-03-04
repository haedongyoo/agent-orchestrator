"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/providers/auth-provider";

function SsoCallbackInner() {
  const searchParams = useSearchParams();
  const { loginWithToken } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = searchParams.get("token");
    if (token) {
      loginWithToken(token);
    } else {
      setError("No token received from SSO provider.");
    }
  }, [searchParams, loginWithToken]);

  if (error) {
    return (
      <div className="text-center">
        <h2 className="text-lg font-semibold text-[var(--destructive)]">SSO Error</h2>
        <p className="mt-2 text-sm text-[var(--muted-foreground)]">{error}</p>
        <a href="/login" className="mt-4 inline-block text-sm underline">
          Back to login
        </a>
      </div>
    );
  }

  return (
    <div className="text-center">
      <p className="text-sm text-[var(--muted-foreground)]">Completing sign in...</p>
    </div>
  );
}

export default function SsoCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="text-center">
          <p className="text-sm text-[var(--muted-foreground)]">Loading...</p>
        </div>
      }
    >
      <SsoCallbackInner />
    </Suspense>
  );
}
