import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import type { ReactNode } from "react";

import { THEME_CANVAS, THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "NIFTY Agent — Dashboard",
  description:
    "Monitoring dashboard for an autonomous NIFTY options trading agent: account balance, monthly and daily targets, and session performance.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: THEME_CANVAS.light },
    { media: "(prefers-color-scheme: dark)", color: THEME_CANVAS.dark },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html
      lang="en"
      // The pre-paint script below mutates <html>, so the server markup and the
      // hydrated markup legitimately differ on className/style.
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-canvas text-ink">
        {/*
          Resolves the stored/OS theme before first paint — without this the
          page would flash the light canvas on a dark-theme load.
          `beforeInteractive` is inlined into <head> in the server HTML.
        */}
        <Script
          id="theme-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }}
        />
        {children}
      </body>
    </html>
  );
}
