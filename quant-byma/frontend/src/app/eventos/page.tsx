import type { Metadata } from "next";

import { EventsView } from "@/components/events-view";

export const metadata: Metadata = { title: "Eventos" };

export default function EventsPage() {
  return <EventsView />;
}
