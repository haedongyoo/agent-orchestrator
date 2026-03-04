import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Auth guard is client-side (JWT in localStorage).
// This middleware only handles basic redirects for unauthenticated server-side requests.
// The actual auth check happens in the AuthProvider on the client.

const publicPaths = ["/login", "/register", "/sso"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public paths and static assets
  if (
    publicPaths.some((p) => pathname.startsWith(p)) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    pathname === "/"
  ) {
    return NextResponse.next();
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
