import { Sidebar } from "@/components/sidebar";
import { stackServerApp } from "@/lib/stack";
import { redirect } from "next/navigation";

export default async function ProjectsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await stackServerApp.getUser();

  if (!user) {
    redirect("/signin");
  }

  return (
    <div className="flex min-h-full w-full">
      <Sidebar />
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
