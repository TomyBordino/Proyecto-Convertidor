import type { Metadata } from "next";

import { PortfolioView } from "@/components/portfolio-view";

export const metadata: Metadata = { title: "Mi cartera" };

export default function PortfolioPage() {
  return <PortfolioView />;
}
