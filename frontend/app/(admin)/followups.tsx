import { ScaffoldScreen } from "@/src/components/ScaffoldScreen";
export default function FollowupsScreen() {
  return (
    <ScaffoldScreen
      title="Follow-ups"
      subtitle="Never lose a lead. Structured cadence built for showroom teams."
      icon="bell"
      features={[
        "Due today, this week, snoozed",
        "One-tap WhatsApp / Call / Email actions",
        "Auto-generated on quotation lifecycle events",
        "Assignment + escalation to managers",
      ]}
    />
  );
}
