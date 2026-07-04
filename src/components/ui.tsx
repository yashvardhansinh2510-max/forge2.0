// Shared primitives. Kept small — everything else composes from these.
import { Feather } from "@expo/vector-icons";
import { ActivityIndicator, Pressable, StyleSheet, Text, View, ViewStyle, TextStyle } from "react-native";

import { colors, radius, spacing, type, statusMeta } from "@/src/theme/tokens";

// ---------- Button ----------
type ButtonProps = {
  label: string;
  onPress?: () => void;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  icon?: keyof typeof Feather.glyphMap;
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  testID?: string;
};

export function Button({ label, onPress, variant = "primary", size = "md", icon, loading, disabled, fullWidth, testID }: ButtonProps) {
  const bg = variant === "primary" ? colors.brand
    : variant === "secondary" ? colors.surfaceSecondary
    : variant === "danger" ? colors.error
    : "transparent";
  const fg = variant === "primary" || variant === "danger" ? colors.onBrand
    : colors.onSurface;
  const border = variant === "secondary" ? colors.border : "transparent";
  const padV = size === "sm" ? 8 : size === "lg" ? 14 : 11;
  const padH = size === "sm" ? 12 : size === "lg" ? 20 : 16;
  const fs = size === "sm" ? 13 : size === "lg" ? 16 : 14;

  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={loading || disabled}
      style={({ pressed }) => [{
        backgroundColor: bg, borderColor: border, borderWidth: 1,
        paddingVertical: padV, paddingHorizontal: padH, borderRadius: radius.md,
        opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
        flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
        alignSelf: fullWidth ? "stretch" : "flex-start",
      }]}
    >
      {loading ? <ActivityIndicator color={fg} size="small" /> : null}
      {icon && !loading ? <Feather name={icon} size={fs + 2} color={fg} /> : null}
      <Text style={{ color: fg, fontSize: fs, fontWeight: "600" }}>{label}</Text>
    </Pressable>
  );
}

// ---------- Card ----------
export function Card({ children, style, testID }: { children: React.ReactNode; style?: ViewStyle; testID?: string }) {
  return (
    <View testID={testID} style={[styles.card, style]}>
      {children}
    </View>
  );
}

// ---------- Badge ----------
export function Badge({ label, tone = "neutral", testID }: { label: string; tone?: "neutral" | "success" | "warning" | "error" | "info"; testID?: string }) {
  const map = {
    neutral: { bg: colors.surfaceTertiary, fg: colors.onSurfaceSecondary },
    success: { bg: colors.successBg, fg: colors.success },
    warning: { bg: colors.warningBg, fg: colors.warning },
    error: { bg: colors.errorBg, fg: colors.error },
    info: { bg: colors.infoBg, fg: colors.info },
  };
  const c = map[tone];
  return (
    <View testID={testID} style={{ backgroundColor: c.bg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill, alignSelf: "flex-start" }}>
      <Text style={{ color: c.fg, fontSize: 11, fontWeight: "600", letterSpacing: 0.2 }}>{label}</Text>
    </View>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const m = statusMeta[status] || { label: status, bg: colors.surfaceTertiary, fg: colors.onSurfaceSecondary };
  return (
    <View style={{ backgroundColor: m.bg, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill, alignSelf: "flex-start" }}>
      <Text style={{ color: m.fg, fontSize: 11, fontWeight: "600" }}>{m.label}</Text>
    </View>
  );
}

// ---------- Divider ----------
export function Divider({ vertical, style }: { vertical?: boolean; style?: ViewStyle }) {
  return <View style={[
    vertical ? { width: StyleSheet.hairlineWidth, alignSelf: "stretch" } : { height: StyleSheet.hairlineWidth, alignSelf: "stretch" },
    { backgroundColor: colors.border }, style,
  ]} />;
}

// ---------- Chip (horizontal filter row) ----------
export function Chip({ label, active, onPress, testID }: { label: string; active?: boolean; onPress?: () => void; testID?: string }) {
  return (
    <Pressable
      onPress={onPress}
      testID={testID}
      style={{
        height: 36, paddingHorizontal: 14, borderRadius: radius.pill,
        borderWidth: 1, borderColor: active ? colors.brand : colors.border,
        backgroundColor: active ? colors.brand : colors.surfaceSecondary,
        alignItems: "center", justifyContent: "center", flexShrink: 0,
      }}
    >
      <Text style={{ color: active ? colors.onBrand : colors.onSurface, fontSize: 13, fontWeight: "500" }}>{label}</Text>
    </Pressable>
  );
}

// ---------- Skeleton ----------
export function Skeleton({ w = "100%", h = 14, style }: { w?: number | string; h?: number; style?: ViewStyle }) {
  return <View style={[{ width: w as any, height: h, backgroundColor: colors.surfaceTertiary, borderRadius: 6 }, style]} />;
}

// ---------- EmptyState ----------
export function EmptyState({ icon = "inbox", title, subtitle, action }: {
  icon?: keyof typeof Feather.glyphMap; title: string; subtitle?: string; action?: React.ReactNode;
}) {
  return (
    <View style={{ alignItems: "center", padding: spacing.xxl, gap: spacing.md }}>
      <View style={{ width: 56, height: 56, borderRadius: radius.pill, backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center" }}>
        <Feather name={icon} size={24} color={colors.onSurfaceMuted} />
      </View>
      <Text style={[type.titleMd, { textAlign: "center" }]}>{title}</Text>
      {subtitle ? <Text style={[type.bodyMuted, { textAlign: "center", maxWidth: 360 }]}>{subtitle}</Text> : null}
      {action}
    </View>
  );
}

// ---------- Section header ----------
export function SectionHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", marginBottom: spacing.md }}>
      <View style={{ flex: 1 }}>
        <Text style={type.titleLg}>{title}</Text>
        {subtitle ? <Text style={[type.bodyMuted, { marginTop: 2 }]}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    padding: spacing.lg,
  },
});

export const s = { spacing, colors, radius, type } as const;
