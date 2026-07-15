// Forge Quotation Builder 3.0 · entry point
// -----------------------------------------------------------------------------
// The 1,300-line monolith has been split into a feature-scoped architecture
// under /src/components/quotation. This file just wires up the provider +
// responsive shell so the same builder works across mobile, tablet portrait,
// tablet landscape and desktop.
//
// All state is centralised in BuilderContext, so future features (payments,
// approvals, complete-the-set upgrades, AI recommendations, comparison mode)
// can slot in without another mega file appearing.
// -----------------------------------------------------------------------------
import { useLocalSearchParams, useRouter } from "expo-router";

import { BuilderProvider, BuilderShell } from "@/src/components/quotation";

export default function QuotationBuilderScreen() {
  const router = useRouter();
  // Optional ?productId=... — set by Catalog's "Add to quotation" CTA so
  // starting a new quotation from a product's detail page actually seeds
  // that product instead of landing on an empty builder.
  const { productId } = useLocalSearchParams<{ productId?: string }>();
  return (
    <BuilderProvider
      initialProductId={productId || null}
      onFinalize={(quotationId) => router.replace(`/(admin)/quotations/${quotationId}` as any)}
    >
      <BuilderShell onBack={() => router.back()} />
    </BuilderProvider>
  );
}
