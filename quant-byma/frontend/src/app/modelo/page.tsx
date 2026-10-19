import type { Metadata } from "next";

import { ModelView } from "@/components/model-view";

export const metadata: Metadata = { title: "Modelo" };

export default function ModelPage() {
  return <ModelView />;
}
