import { Stack, useRootNavigationState, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { LogBox, Text, View } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { useAppFonts } from "@/src/hooks/use-app-fonts";
import { AuthProvider, useAuth } from "@/src/state/auth";
import { colors, font } from "@/src/theme/tokens";
import { ToastHost } from "@/src/components/Toast";
import { initSentry } from "@/src/lib/monitoring";

// Production monitoring — complete no-op unless EXPO_PUBLIC_SENTRY_DSN is set
// (see src/lib/monitoring.ts). Safe to call unconditionally at module load.
initSentry();

// Global default: any Text without an explicit fontFamily inherits Inter-Regular.
// This ensures every legacy screen automatically renders with our typographic voice.
// Individual weights (Medium/SemiBold/Bold) still opt-in explicitly via type.* tokens.
const anyText = Text as any;
anyText.defaultProps = anyText.defaultProps || {};
anyText.defaultProps.style = [{ fontFamily: font.regular }, anyText.defaultProps.style];

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

function AuthGate({ children }: { children: React.ReactNode }) {
  const { loading, kind, staff, customer } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  const navigationState = useRootNavigationState();
  const isNavigationReady = navigationState?.key !== undefined;

  useEffect(() => {
    if (loading || !isNavigationReady) return;
    const inAuth = segments[0] === "(auth)";
    const inAdmin = segments[0] === "(admin)";
    const inCustomer = segments[0] === "(customer)";
    const onForceChange = inAuth && segments[1] === "set-new-password";

    // Security requirement: a temporary password (Team > Reset Password,
    // Customers > Send Invite/Reset Password) must force a real password
    // before the user can reach anything else — checked before the normal
    // staff/customer routing below so it wins regardless of destination.
    const mustChangePassword =
      (kind === "staff" && !!staff?.must_change_password) ||
      (kind === "customer" && !!customer?.must_change_password);

    if (kind && mustChangePassword && !onForceChange) {
      router.replace("/(auth)/set-new-password");
      return;
    }
    if (kind && !mustChangePassword && onForceChange) {
      // Just finished the forced change — fall through to normal routing.
      router.replace(kind === "staff" ? "/(admin)/dashboard" : "/(customer)/home");
      return;
    }

    if (!kind && !inAuth) {
      router.replace("/(auth)/login");
  } else if (kind === "staff" && !inAdmin) {
    if (inAuth) router.replace("/(admin)/dashboard");
  } else if (kind === "customer" && !inCustomer) {
    if (inAuth) router.replace("/(customer)/home");
    }
  }, [kind, loading, isNavigationReady, segments, router, staff, customer]);

  return <>{children}</>;
}

export default function RootLayout() {
  const [loaded, error] = useAppFonts();
  useEffect(() => {
    if (loaded || error) SplashScreen.hideAsync();
  }, [loaded, error]);
  if (!loaded && !error) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <View style={{ flex: 1, backgroundColor: colors.surface }}>
          <StatusBar style="dark" />
          <AuthProvider>
            <AuthGate>
              <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }} />
            </AuthGate>
            <ToastHost />
          </AuthProvider>
        </View>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
