import { Slot } from "expo-router";
import { View } from "react-native";

import { WorkspaceSwitcher } from "@/src/components/analytics/WorkspaceSwitcher";
import { spacing } from "@/src/theme/tokens";

/**
 * Shell shared by every Sales Data workspace. The switcher lives here so a
 * workspace never renders its own navigation and they cannot drift apart.
 */
export default function SalesDataLayout() {
  return (
    <View style={{ flex: 1, gap: spacing.md }}>
      <WorkspaceSwitcher />
      <View style={{ flex: 1 }}>
        <Slot />
      </View>
    </View>
  );
}
