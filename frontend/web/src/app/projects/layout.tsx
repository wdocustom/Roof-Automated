import { Sidebar } from "@/components/sidebar";
import { auth } from "@/lib/auth/server";
import { redirect } from "next/navigation";

export default async function ProjectsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: session } = await auth.getSession();

  if (!session?.user) {
    redirect("/signin");
  }

  return (
    <div className="flex min-h-full w-full">
      <Sidebar />
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
