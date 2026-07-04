import { Stack, useRouter, useSegments } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { LogBox, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { AuthProvider, useAuth } from "@/src/state/auth";
import { colors } from "@/src/theme/tokens";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

function AuthGate({ children }: { children: React.ReactNode }) {
  const { loading, kind } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    const inAuth = segments[0] === "(auth)";
    const inAdmin = segments[0] === "(admin)";
    const inCustomer = segments[0] === "(customer)";

    if (!kind && !inAuth) {
      router.replace("/(auth)/login");
    } else if (kind === "staff" && (!inAdmin || segments.length === 0)) {
      if (inAuth || segments.length === 0) router.replace("/(admin)/dashboard");
    } else if (kind === "customer" && !inCustomer) {
      if (inAuth || segments.length === 0) router.replace("/(customer)/home");
    }
  }, [kind, loading, segments, router]);

  return <>{children}</>;
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();
  useEffect(() => {
    if (loaded || error) SplashScreen.hideAsync();
  }, [loaded, error]);
  if (!loaded && !error) return null;

  return (
    <SafeAreaProvider>
      <View style={{ flex: 1, backgroundColor: colors.surface }}>
        <StatusBar style="dark" />
        <AuthProvider>
          <AuthGate>
            <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }} />
          </AuthGate>
        </AuthProvider>
      </View>
    </SafeAreaProvider>
  );
}
