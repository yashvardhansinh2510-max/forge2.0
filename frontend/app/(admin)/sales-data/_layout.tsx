import { Slot } from "expo-router";
import { View } from "react-native";

import { WorkspaceSwitcher } from "@/src/components/analytics/WorkspaceSwitcher";

/**
 * Shell shared by every Sales Data workspace. The switcher lives here so a
 * workspace never renders its own navigation and they cannot drift apart.
 */
export default function SalesDataLayout() {
  return (
    // No gap: the switcher now owns its own vertical padding and closes with
    // a hairline rule, so an extra gap here would float that rule in dead
    // space instead of seating it against the page below.
    <View style={{ flex: 1 }}>
      <WorkspaceSwitcher />
      <View style={{ flex: 1 }}>
        <Slot />
      </View>
    </View>
  );
}
