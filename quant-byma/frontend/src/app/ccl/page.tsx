import type { Metadata } from "next";

import { CCLView } from "@/components/ccl-view";

export const metadata: Metadata = { title: "CCL" };

export default function CCLPage() {
  return <CCLView />;
}
