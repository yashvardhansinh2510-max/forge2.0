import { Stack } from "expo-router";

import { MobileViewport } from "@/src/components/mobile/MobileShell";
import { colors } from "@/src/theme/tokens";

export default function CustomerLayout() {
  return (
    <MobileViewport
      testID="customer-mobile-shell"
      backgroundColor={colors.surface}
      edges={["left", "right"]}
    >
      <Stack screenOptions={{ headerShown: false }} />
    </MobileViewport>
  );
}
