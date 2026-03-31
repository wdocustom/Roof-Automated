import { auth } from "@/lib/auth/server";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_URL || "https://roof-automated-production.up.railway.app";

/**
 * Server-side API proxy that forwards authenticated requests to the Railway backend.
 * The session is validated server-side, and the user ID is passed as a header.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { data: session } = await auth.getSession();
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { path } = await params;
  const backendPath = `/api/v1/${path.join("/")}`;
  const url = new URL(backendPath, BACKEND_URL);
  // Forward query params
  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.set(key, value);
  });

  const res = await fetch(url.toString(), {
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": session.user.id,
      "X-User-Email": session.user.email || "",
    },
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { data: session } = await auth.getSession();
  if (!session?.user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { path } = await params;
  const backendPath = `/api/v1/${path.join("/")}`;
  const url = new URL(backendPath, BACKEND_URL);

  const body = await request.text();

  const res = await fetch(url.toString(), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": session.user.id,
      "X-User-Email": session.user.email || "",
    },
    body,
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
