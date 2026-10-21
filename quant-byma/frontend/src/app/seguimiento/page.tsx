import type { Metadata } from "next";

import { TrackingView } from "@/components/tracking-view";

export const metadata: Metadata = { title: "Seguimiento" };

export default function TrackingPage() {
  return <TrackingView />;
}
