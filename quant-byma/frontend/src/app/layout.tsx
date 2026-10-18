import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";

import { MainNav } from "@/components/main-nav";

import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: "Quant BYMA", template: "%s · Quant BYMA" },
  description: "Análisis técnico, fundamental y de CCL para acciones argentinas y CEDEARs",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <header className="sticky top-0 z-20 border-b bg-background/85 backdrop-blur">
          <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-6 px-4">
            <Link href="/" className="font-semibold tracking-tight">
              Quant<span className="text-primary">BYMA</span>
            </Link>
            <Suspense fallback={<div className="h-8" />}>
              <MainNav />
            </Suspense>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
        <footer className="border-t py-4 text-center text-xs text-muted-foreground">
          Herramienta de análisis cuantitativo. No constituye recomendación de inversión.
        </footer>
      </body>
    </html>
  );
}
