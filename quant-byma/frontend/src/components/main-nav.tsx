"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/hoy", label: "Qué hacer hoy" },
  { href: "/", label: "Ranking" },
  { href: "/screener", label: "Screener" },
  { href: "/ccl", label: "CCL" },
  { href: "/modelo", label: "Modelo" },
  { href: "/eventos", label: "Eventos" },
  { href: "/backtest", label: "Backtest" },
  { href: "/cartera", label: "Mi cartera" },
];

export function MainNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 text-sm">
      {LINKS.map((l) => {
        const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            className={cn(
              "rounded-md px-3 py-1.5 transition-colors hover:bg-accent",
              active ? "bg-accent font-medium text-foreground" : "text-muted-foreground",
            )}
          >
            {l.label}
          </Link>
        );
      })}
    </nav>
  );
}
