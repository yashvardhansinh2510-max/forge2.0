import { Stack, useRootNavigationState, useRouter, useSegments } from "expo-router";
import { useEffect } from "react";
import { View } from "react-native";

import { AuthProvider, useAuth } from "@/src/state/auth";
import { colors } from "@/src/theme/tokens";
import { ToastHost } from "@/src/components/Toast";
import { initSentry } from "@/src/lib/monitoring";

/**
 * Browser-only root shell.
 *
 * The native root needs splash screen coordination, native safe areas and the
 * gesture-handler root.  React Native Web does not: importing those modules at
 * the entry point made their native implementation part of every initial web
 * route, including the login page.  Keep this deliberately small; route-level
 * screens load their own platform integrations when a user actually opens them.
 */
function AuthGate({ children }: { children: React.ReactNode }) {
  const { loading, kind, staff, customer } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  const navigationState = useRootNavigationState();
  const isNavigationReady = navigationState?.key !== undefined;

  useEffect(() => {
    if (loading || !isNavigationReady) return;
    if (segments[0] === "privacy" || segments[0] === "terms") return;

    const inAuth = segments[0] === "(auth)";
    const inAdmin = segments[0] === "(admin)";
    const inCustomer = segments[0] === "(customer)";
    const onForceChange = inAuth && segments[1] === "set-new-password";
    const mustChangePassword =
      (kind === "staff" && !!staff?.must_change_password) ||
      (kind === "customer" && !!customer?.must_change_password);

    if (kind && mustChangePassword) {
      if (!onForceChange) router.replace("/(auth)/set-new-password");
      return;
    }
    if (kind && onForceChange) {
      router.replace(kind === "staff" ? "/(admin)/dashboard" : "/(customer)/home");
      return;
    }
    if (!kind && !inAuth) {
      router.replace("/(auth)/login");
    } else if (kind === "staff" && !inAdmin && inAuth) {
      router.replace("/(admin)/dashboard");
    } else if (kind === "customer" && !inCustomer && inAuth) {
      router.replace("/(customer)/home");
    }
  }, [kind, loading, isNavigationReady, segments, router, staff, customer]);

  return <>{children}</>;
}

export default function RootLayout() {
  useEffect(() => { initSentry(); }, []);
  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <AuthProvider>
        <AuthGate>
          <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }} />
        </AuthGate>
        <ToastHost />
      </AuthProvider>
    </View>
  );
}
