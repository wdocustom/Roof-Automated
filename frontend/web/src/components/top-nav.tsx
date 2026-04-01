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
  Menu,
  X,
} from "lucide-react";
import { clsx } from "clsx";
import { useState } from "react";
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
  const [mobileOpen, setMobileOpen] = useState(false);

  async function handleSignOut() {
    await authClient.signOut();
    router.push("/signin");
  }

  return (
    <header className="bg-gray-900 text-white sticky top-0 z-50">
      <div className="flex items-center justify-between px-4 py-3">
        {/* Logo */}
        <Link href="/dashboard" className="flex items-center gap-2">
          <HardHat className="h-7 w-7 text-orange-500" />
          <span className="text-lg font-bold tracking-tight hidden sm:inline">
            Roof Automated
          </span>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-1">
          {nav.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  active
                    ? "bg-orange-600 text-white"
                    : "text-gray-300 hover:bg-gray-800 hover:text-white"
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.name}
              </Link>
            );
          })}
        </nav>

        {/* Desktop sign out */}
        <button
          onClick={handleSignOut}
          className="hidden md:flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-gray-400 hover:bg-gray-800 hover:text-white transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Sign Out
        </button>

        {/* Mobile hamburger */}
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden text-gray-300 hover:text-white"
          aria-label="Toggle menu"
        >
          {mobileOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
        </button>
      </div>

      {/* Mobile dropdown */}
      {mobileOpen && (
        <nav className="md:hidden px-4 pb-4 space-y-1 border-t border-gray-800">
          {nav.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMobileOpen(false)}
                className={clsx(
                  "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  active
                    ? "bg-orange-600 text-white"
                    : "text-gray-300 hover:bg-gray-800 hover:text-white"
                )}
              >
                <item.icon className="h-5 w-5" />
                {item.name}
              </Link>
            );
          })}
          <button
            onClick={handleSignOut}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-400 hover:bg-gray-800 hover:text-white transition-colors w-full"
          >
            <LogOut className="h-5 w-5" />
            Sign Out
          </button>
        </nav>
      )}
    </header>
  );
}
