// Legacy route → redirect to the new material tracker at /purchases.
// The individual PO detail page ([id].tsx) stays so links to specific POs still work.
import { Redirect } from "expo-router";

export default function LegacyPurchaseOrdersIndex() {
  return <Redirect href="/(admin)/purchases" />;
}
