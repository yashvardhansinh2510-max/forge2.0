import { ScaffoldScreen } from "@/src/components/ScaffoldScreen";
export default function PaymentsScreen() {
  return (
    <ScaffoldScreen
      title="Payments"
      subtitle="Ledger, advances, refunds — reconciled with quotations & POs."
      icon="credit-card"
      features={[
        "Multi-mode entry (UPI, Bank, Cheque, Card, Cash)",
        "Auto-linked to quotation, invoice or PO",
        "Advance / on-account / write-off workflows",
        "Bank reconciliation with CSV import",
      ]}
    />
  );
}
