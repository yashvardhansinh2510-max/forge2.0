// Reports module removed from user-facing navigation per product decision
// (Phase 5 roadmap revision) — the backend/report groundwork, if any, is
// intentionally left untouched for a future release. This route is kept
// only so a stale bookmark/deep-link doesn't 404 or show a "Coming Soon"
// placeholder — it silently redirects to the dashboard instead.
import { Redirect } from "expo-router";
export default function ReportsScreen() {
  return <Redirect href="/(admin)/dashboard" />;
}
