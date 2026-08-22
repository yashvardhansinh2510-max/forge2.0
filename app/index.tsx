import { Redirect } from "expo-router";

import { useAuth } from "@/src/state/auth";

export default function Index() {
  const { loading, kind } = useAuth();
  if (loading) return null;
  if (!kind) return <Redirect href="/(auth)/login" />;
  if (kind === "staff") return <Redirect href="/(admin)/dashboard" />;
  return <Redirect href="/(customer)/home" />;
}
