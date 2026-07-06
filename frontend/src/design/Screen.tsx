// Screen — the one page scaffold. Consistent gutters, max width, header rhythm.
import { useRouter } from "expo-router";
import React from "react";
import { ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { IconButton, Txt } from "./components";
import { useBp } from "./responsive";
import { color, layout, space } from "./tokens";

export function Screen({
  title, eyebrow, sub, back, actions, children,
  scroll = true, maxWidth = layout.content, header = true,
}: {
  title?: string;
  eyebrow?: string;
  sub?: string;
  back?: boolean;
  actions?: React.ReactNode;
  children: React.ReactNode;
  scroll?: boolean;
  maxWidth?: number;
  header?: boolean;
}) {
  const { isPhone, gutter } = useBp();
  const insets = useSafeAreaInsets();
  const router = useRouter();

  const headerBlock = header && (title || actions) ? (
    <View style={{
      flexDirection: "row", alignItems: "flex-start", gap: space.x3,
      paddingTop: isPhone ? space.x3 : space.x8,
      paddingBottom: isPhone ? space.x4 : space.x6,
    }}>
      {back ? (
        <IconButton icon="arrow-left" onPress={() => router.back()} label="Back" size={38} iconSize={19} />
      ) : null}
      <View style={{ flex: 1, minWidth: 0, gap: 3 }}>
        {eyebrow ? <Txt v="eyebrow">{eyebrow}</Txt> : null}
        {title ? <Txt v="title" style={{ fontSize: isPhone ? 20 : 22, lineHeight: isPhone ? 27 : 29 }}>{title}</Txt> : null}
        {sub ? <Txt v="sub">{sub}</Txt> : null}
      </View>
      {actions ? (
        <View style={{ flexDirection: "row", alignItems: "center", gap: space.x2 }}>{actions}</View>
      ) : null}
    </View>
  ) : null;

  const inner = (
    <View style={{
      width: "100%", maxWidth, alignSelf: "center",
      paddingHorizontal: gutter, flexGrow: 1,
    }}>
      {headerBlock}
      {children}
    </View>
  );

  if (!scroll) {
    return (
      <View style={{ flex: 1, backgroundColor: color.canvas }}>
        {inner}
      </View>
    );
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: color.canvas }}
      contentContainerStyle={{ paddingBottom: space.x16, flexGrow: 1 }}
      showsVerticalScrollIndicator={false}
    >
      {inner}
    </ScrollView>
  );
}
