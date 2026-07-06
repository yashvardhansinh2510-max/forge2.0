// Reusable page frame for logged-in screens.
// Now composed on top of the shared PageHeader primitive so every AdminPage
// gets identical chrome (title + overline + subtitle + action cluster + optional
// back). No hardcoded typography or spacing anywhere.
//
// Also exposes IconAction for right-cluster buttons (unchanged API for callers).
import { Feather } from "@expo/vector-icons";
import { Pressable, ScrollView, StyleSheet, Text, View, ViewStyle } from "react-native";

import { PageHeader } from "@/src/components/ui";
import { colors, layout, radius, spacing, type } from "@/src/theme/tokens";

export function AdminPage({
  title,
  subtitle,
  overline,
  right,
  back,
  children,
  scroll = true,
  contentStyle,
}: {
  title: string;
  subtitle?: string | null;
  overline?: string;
  right?: React.ReactNode;
  back?: () => void;
  children: React.ReactNode;
  scroll?: boolean;
  contentStyle?: ViewStyle;
  /** @deprecated — header now always uses a subtle divider */
  headerBorder?: boolean;
}) {
  const Container: any = scroll ? ScrollView : View;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface }}>
      <PageHeader
        title={title}
        subtitle={subtitle || undefined}
        overline={overline}
        back={back}
        actions={right}
      />
      <Container
        {...(scroll
          ? {
              showsVerticalScrollIndicator: false,
              contentContainerStyle: {
                paddingHorizontal: layout.screenPadding.tablet,
                paddingTop: spacing.xl,
                paddingBottom: spacing.xxxl,
                gap: spacing.lg,
                ...contentStyle,
              },
            }
          : {
              style: [
                {
                  flex: 1,
                  paddingHorizontal: layout.screenPadding.tablet,
                  paddingTop: spacing.xl,
                },
                contentStyle,
              ],
            })}
      >
        {children}
      </Container>
    </View>
  );
}

// Icon-only tappable in a page header's right cluster. Kept exported for
// backwards-compat with older screens. Renders a bordered 40x40 tile with
// centered icon + optional label chip. Uses tokens only.
export function IconAction({
  icon, label, onPress, testID, tone = "surface",
}: {
  icon: keyof typeof Feather.glyphMap;
  label?: string;
  onPress: () => void;
  testID?: string;
  tone?: "surface" | "brand";
}) {
  const isBrand = tone === "brand";
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => [{
        flexDirection: "row",
        alignItems: "center",
        gap: 8,
        height: 40,
        paddingHorizontal: label ? spacing.md : 0,
        width: label ? undefined : 40,
        borderRadius: radius.md,
        backgroundColor: isBrand ? colors.brand : colors.surfaceSecondary,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: isBrand ? colors.brand : colors.border,
        opacity: pressed ? 0.88 : 1,
        justifyContent: "center",
      }]}
    >
      <Feather name={icon} size={16} color={isBrand ? colors.onBrand : colors.onSurface} />
      {label ? (
        <Text style={{
          fontSize: 13,
          fontFamily: type.titleMd.fontFamily,
          fontWeight: "600",
          color: isBrand ? colors.onBrand : colors.onSurface,
        }}>{label}</Text>
      ) : null}
    </Pressable>
  );
}
