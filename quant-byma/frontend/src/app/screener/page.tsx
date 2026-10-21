import type { Metadata } from "next";

import { Screener } from "@/components/screener";

export const metadata: Metadata = { title: "Screener" };

export default function ScreenerPage() {
  return <Screener />;
}
