import { ScaffoldScreen } from "@/src/components/ScaffoldScreen";
export default function ReportsScreen() {
  return (
    <ScaffoldScreen
      title="Reports"
      subtitle="Deep dashboards. Sales, purchase, stock, receivables — all in one place."
      icon="bar-chart-2"
      features={[
        "Sales conversion & pipeline velocity",
        "Product & brand performance",
        "Salesperson leaderboard with target attainment",
        "Receivables ledger + P&L snapshot",
      ]}
    />
  );
}
