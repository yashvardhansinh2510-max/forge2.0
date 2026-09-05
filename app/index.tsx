import { Redirect } from "expo-router";

import { useAuth } from "@/src/state/auth";
import { staffLandingPath } from "@/src/access-profiles";

export default function Index() {
  const { loading, kind, staff } = useAuth();
  if (loading) return null;
  if (!kind) return <Redirect href="/(auth)/login" />;
  if (kind === "staff") return <Redirect href={staffLandingPath(staff?.access_profile, staff?.access_grants) as any} />;
  return <Redirect href="/(customer)/home" />;
}
