import type { Metadata } from "next";
import { Suspense } from "react";

import { AssetView } from "@/components/asset-view";
import { LoadingState } from "@/components/state";

export async function generateMetadata({ params }: PageProps<"/asset/[ticker]">): Promise<Metadata> {
  const { ticker } = await params;
  return { title: ticker.toUpperCase() };
}

async function Asset({ params }: { params: PageProps<"/asset/[ticker]">["params"] }) {
  const { ticker } = await params;
  return <AssetView ticker={ticker.toUpperCase()} />;
}

export default function AssetPage({ params }: PageProps<"/asset/[ticker]">) {
  return (
    <Suspense fallback={<LoadingState />}>
      <Asset params={params} />
    </Suspense>
  );
}
