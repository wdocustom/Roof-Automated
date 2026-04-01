"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  FolderKanban,
  MessageSquare,
  DollarSign,
  Bot,
  Settings,
  HardHat,
  LogOut,
} from "lucide-react";
import { clsx } from "clsx";
import { authClient } from "@/lib/auth/client";

const nav = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Projects", href: "/projects", icon: FolderKanban },
  { name: "Messages", href: "/messages", icon: MessageSquare },
  { name: "Payments", href: "/payments", icon: DollarSign },
  { name: "AI Agents", href: "/agents", icon: Bot },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();

  async function handleSignOut() {
    await authClient.signOut();
    router.push("/signin");
  }

  return (
    <header className="bg-gray-900 text-white sticky top-0 z-50">
      <div className="flex items-center gap-1 px-4 py-3 overflow-x-auto">
        {/* Logo */}
        <Link href="/dashboard" className="flex items-center gap-2 shrink-0 mr-4">
          <HardHat className="h-7 w-7 text-orange-500" />
          <span className="text-lg font-bold tracking-tight">
            Roof Automated
          </span>
        </Link>

        {/* Nav links — always visible */}
        {nav.map((item) => {
          const Icon = item.icon;
          const active = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap shrink-0",
                active
                  ? "bg-orange-600 text-white"
                  : "text-gray-300 hover:bg-gray-800 hover:text-white"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.name}
            </Link>
          );
        })}

        {/* Sign out — always visible, pushed right */}
        <button
          onClick={handleSignOut}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-gray-400 hover:bg-gray-800 hover:text-white transition-colors whitespace-nowrap shrink-0 ml-auto"
        >
          <LogOut className="h-4 w-4" />
          Sign Out
        </button>
      </div>
    </header>
  );
}
