import React from "react";
import { StyleProp, ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { color } from "@/src/design/tokens";

type SafeAreaEdge = "top" | "right" | "bottom" | "left";

/**
 * Shared route-level mobile viewport. Screens own their internal scroll and
 * top chrome; this primitive owns the viewport background and the safe-area
 * edges that belong to the shell.
 */
export function MobileViewport({
  children,
  backgroundColor = color.canvas,
  edges = ["left", "right"],
  style,
  testID,
}: {
  children: React.ReactNode;
  backgroundColor?: string;
  edges?: SafeAreaEdge[];
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  return (
    <SafeAreaView
      testID={testID}
      edges={edges}
      style={[{ flex: 1, minWidth: 0, backgroundColor }, style]}
    >
      {children}
    </SafeAreaView>
  );
}
