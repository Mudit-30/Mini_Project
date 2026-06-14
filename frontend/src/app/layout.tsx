import type { Metadata, Viewport } from "next";
import { Space_Grotesk, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

// Display = Space Grotesk (headings + big data-hero numbers), body = Inter, data = JetBrains Mono.
const fontDisplay = Space_Grotesk({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
});

const fontSans = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const fontMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "GridMind — Carbon-Aware Distributed Scheduler",
  description:
    "Turn idle laptops into a carbon-aware mini-supercomputer: run heavy tasks only when a machine is free and the grid is clean. Live dispatcher, measured CO₂ savings, and a fault-tolerant cluster.",
  applicationName: "GridMind",
  keywords: ["carbon-aware", "distributed computing", "scheduler", "green computing", "edge cluster"],
};

export const viewport: Viewport = {
  themeColor: "#0a0b0f",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${fontDisplay.variable} ${fontSans.variable} ${fontMono.variable} font-sans antialiased bg-background text-foreground`}
        suppressHydrationWarning
      >
        {children}
      </body>
    </html>
  );
}
