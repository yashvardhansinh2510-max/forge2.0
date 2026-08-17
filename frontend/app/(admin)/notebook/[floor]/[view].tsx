import { Redirect, useLocalSearchParams } from "expo-router";

/** Legacy notebook URLs remain valid without creating extra workspaces. */
export default function LegacyNotebookView() {
  const { floor, view } = useLocalSearchParams<{ floor?: string; view?: string }>();
  const base = `/(admin)/notebook/${floor === "furniture" ? "furniture" : "kitchen"}`;
  return <Redirect href={(view === "quotation" ? `${base}/quotation-follow-up` : base) as any} />;
}
