import { ScaffoldScreen } from "@/src/components/ScaffoldScreen";
export default function ReportsScreen() {
  return (
    <ScaffoldScreen
      title="Reports"
      subtitle="Deep dashboards. Sales, purchase, stock, GST — all in one place."
      icon="bar-chart-2"
      features={[
        "Sales conversion & pipeline velocity",
        "Product & brand performance",
        "Salesperson leaderboard with target attainment",
        "GST-ready ledgers + P&L snapshot",
      ]}
    />
  );
}
