// Reusable page frame for admin screens: sticky top bar + scrollable content.
import { Feather } from "@expo/vector-icons";
import { ScrollView, StyleSheet, Text, useWindowDimensions, View, ViewStyle } from "react-native";

import { colors, spacing, type } from "@/src/theme/tokens";

export function AdminPage({
  title, subtitle, right, children, scroll = true, contentStyle,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
  children: React.ReactNode;
  scroll?: boolean;
  contentStyle?: ViewStyle;
}) {
  const { width } = useWindowDimensions();
  const isTablet = width >= 900;
  const padH = isTablet ? spacing.xxl : spacing.lg;

  const Container = scroll ? ScrollView : View;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <View style={[styles.header, { paddingHorizontal: padH }]}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text numberOfLines={1} style={type.displayMd}>{title}</Text>
          {subtitle ? <Text numberOfLines={1} style={[type.bodyMuted, { marginTop: 2 }]}>{subtitle}</Text> : null}
        </View>
        {right ? <View style={{ flexShrink: 0 }}>{right}</View> : null}
      </View>
      <Container
        {...(scroll ? { showsVerticalScrollIndicator: false, contentContainerStyle: { padding: padH, paddingTop: spacing.lg, gap: spacing.lg, ...contentStyle } } : { style: [{ flex: 1, padding: padH }, contentStyle] })}
      >
        {children}
      </Container>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    paddingTop: spacing.xl, paddingBottom: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
    flexDirection: "row", alignItems: "flex-end", gap: spacing.md,
    backgroundColor: colors.surface,
  },
});

// Simple icon-only sticky top button (for actions like "New")
export function IconAction({ icon, label, onPress, testID }: {
  icon: keyof typeof Feather.glyphMap;
  label?: string;
  onPress: () => void;
  testID?: string;
}) {
  return (
    <View>
      <Feather name={icon} size={16} color={colors.onSurface} />
      {label ? <Text>{label}</Text> : null}
    </View>
  );
}
