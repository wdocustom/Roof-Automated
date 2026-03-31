import type { Metadata } from "next";
import { StackProvider, StackTheme } from "@stackframe/stack";
import "./globals.css";
import { Providers } from "@/lib/providers";
import { stackServerApp } from "@/lib/stack";

export const metadata: Metadata = {
  title: "Roof Automated — Contractor Dashboard",
  description: "Agentic AI platform for roofers and siders",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full bg-gray-50 font-sans">
        <StackProvider app={stackServerApp}>
          <StackTheme>
            <Providers>{children}</Providers>
          </StackTheme>
        </StackProvider>
      </body>
    </html>
  );
}
