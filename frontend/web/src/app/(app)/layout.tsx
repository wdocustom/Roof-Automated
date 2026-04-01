import { TopNav } from "@/components/top-nav";
import { auth } from "@/lib/auth/server";
import { redirect } from "next/navigation";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: session } = await auth.getSession();

  if (!session?.user) {
    redirect("/signin");
  }

  return (
    <div className="min-h-full flex flex-col">
      <TopNav />
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
