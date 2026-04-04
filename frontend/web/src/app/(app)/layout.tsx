import { TopNav } from "@/components/top-nav";
import { auth } from "@/lib/auth/server";
import { redirect } from "next/navigation";

const BACKEND_URL =
  process.env.BACKEND_URL ||
  "https://roof-automated-production.up.railway.app";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: session } = await auth.getSession();

  if (!session?.user) {
    redirect("/signin");
  }

  // Check if user has completed onboarding (has a company record)
  try {
    const res = await fetch(`${BACKEND_URL}/api/v1/onboarding/status`, {
      headers: {
        "X-User-Id": session.user.id,
        "X-User-Email": session.user.email || "",
      },
      cache: "no-store",
    });

    if (res.ok) {
      const status = await res.json();
      if (!status.has_company) {
        redirect("/onboarding");
      }
    }
  } catch {
    // If backend is down, let them through — pages handle empty state
  }

  return (
    <div className="min-h-full flex flex-col">
      <TopNav />
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
