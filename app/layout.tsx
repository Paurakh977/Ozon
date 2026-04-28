import "./globals.css";
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { ThemeProvider } from "@/components/providers";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Ozon | Advanced Graphing Calculator & Math AI",
  description: "A powerful graphing calculator built on the Desmos engine. Features include calculus (derivatives, integrals), complex numbers, polar & parametric curves, function analysis, and an AI agent for natural language math.",
  keywords: [
    "graphing calculator", 
    "desmos alternative", 
    "calculus", 
    "derivatives", 
    "integrals", 
    "complex numbers", 
    "math ai", 
    "function analysis"
  ],
  icons: {
    icon: "/logo.svg",
    apple: "/logo.png",
  },
  openGraph: {
    title: "Ozon Calculator",
    description: "Advanced graphing with calculus, complex numbers, and AI capabilities.",
    siteName: "Ozon",
    type: "website",
  }
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
