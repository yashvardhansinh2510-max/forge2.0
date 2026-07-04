import { ScaffoldScreen } from "@/src/components/ScaffoldScreen";
export default function PurchaseOrdersScreen() {
  return (
    <ScaffoldScreen
      title="Purchase Orders"
      subtitle="Supplier POs, receipts, GRN and reconciliation."
      icon="shopping-cart"
      features={[
        "Draft PO from selected products or low-stock alerts",
        "Supplier catalog matching + variant fill",
        "Split shipments and partial receipts",
        "Auto-linked payment vouchers",
      ]}
    />
  );
}
