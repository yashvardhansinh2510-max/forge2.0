// Shared primitives. Kept small — everything else composes from these.
import { Feather } from "@expo/vector-icons";
import { ActivityIndicator, Pressable, StyleSheet, Text, View, ViewStyle } from "react-native";

import { colors, radius, spacing, type, statusMeta, money } from "@/src/theme/tokens";

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

// ---------- IconButton (circular, for headers, cards) ----------
export function IconButton({
  icon, onPress, size = 40, tone = "surface", testID, accessibilityLabel, active, disabled,
}: {
  icon: keyof typeof Feather.glyphMap;
  onPress?: () => void;
  size?: number;
  tone?: "surface" | "ghost" | "brand" | "translucent";
  testID?: string;
  accessibilityLabel?: string;
  active?: boolean;
  disabled?: boolean;
}) {
  const bg =
    tone === "brand" ? colors.brand :
    tone === "translucent" ? "rgba(255,255,255,0.92)" :
    tone === "ghost" ? "transparent" :
    colors.surfaceSecondary;
  const fg = tone === "brand" ? colors.onBrand : active ? colors.brand : colors.onSurface;
  const iconSize = Math.max(14, Math.floor(size * 0.45));
  return (
    <Pressable
      testID={testID}
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      disabled={disabled}
      hitSlop={8}
      style={({ pressed }) => [{
        width: size, height: size, borderRadius: size / 2,
        backgroundColor: bg,
        borderWidth: tone === "surface" ? StyleSheet.hairlineWidth : 0,
        borderColor: colors.border,
        alignItems: "center", justifyContent: "center",
        opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
      }]}
    >
      <Feather name={icon} size={iconSize} color={fg} />
    </Pressable>
  );
}

// ---------- Segmented control (2-4 options, horizontally packed) ----------
export function SegmentedControl<T extends string>({
  value, options, onChange, size = "md", testID,
}: {
  value: T;
  options: { value: T; label: string; icon?: keyof typeof Feather.glyphMap }[];
  onChange: (v: T) => void;
  size?: "sm" | "md";
  testID?: string;
}) {
  const h = size === "sm" ? 32 : 36;
  return (
    <View testID={testID} style={{
      flexDirection: "row",
      backgroundColor: colors.surfaceTertiary,
      borderRadius: radius.md, padding: 3, height: h,
    }}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={String(o.value)}
            testID={testID ? `${testID}-${o.value}` : undefined}
            onPress={() => onChange(o.value)}
            style={{
              flex: 1, borderRadius: radius.sm + 2,
              paddingHorizontal: 10, minWidth: 68,
              alignItems: "center", justifyContent: "center",
              flexDirection: "row", gap: 6,
              backgroundColor: on ? colors.surfaceSecondary : "transparent",
              ...(on ? { shadowColor: "#000", shadowOpacity: 0.06, shadowRadius: 3, shadowOffset: { width: 0, height: 1 }, elevation: 1 } : null),
            }}
          >
            {o.icon ? <Feather name={o.icon} size={13} color={on ? colors.onSurface : colors.onSurfaceMuted} /> : null}
            <Text style={{ fontSize: size === "sm" ? 12 : 13, fontWeight: on ? "700" : "500", color: on ? colors.onSurface : colors.onSurfaceMuted }}>
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

// ---------- PriceTag — consistent price rendering everywhere ----------
export function PriceTag({
  price, mrp, size = "md", align = "left",
}: {
  price: number;
  mrp?: number;
  size?: "sm" | "md" | "lg" | "xl";
  align?: "left" | "right";
}) {
  const showSlash = typeof mrp === "number" && mrp > price;
  const priceSize = size === "xl" ? 26 : size === "lg" ? 18 : size === "sm" ? 13 : 15;
  const mrpSize   = size === "xl" ? 14 : size === "lg" ? 12 : size === "sm" ? 10 : 11;
  return (
    <View style={{ flexDirection: "row", alignItems: "baseline", gap: 6, justifyContent: align === "right" ? "flex-end" : "flex-start" }}>
      <Text style={{ fontSize: priceSize, fontWeight: "700", color: colors.onSurface, fontVariant: ["tabular-nums"] }}>{money(price)}</Text>
      {showSlash ? (
        <Text style={{ fontSize: mrpSize, color: colors.onSurfaceMuted, textDecorationLine: "line-through", fontVariant: ["tabular-nums"] }}>
          {money(mrp!)}
        </Text>
      ) : null}
    </View>
  );
}

// ---------- ScreenTitle — mobile-first sticky title bar (never wraps) ----------
export function ScreenTitle({
  title, subtitle, right, back,
}: {
  title: string;
  subtitle?: string | null;
  right?: React.ReactNode;
  back?: () => void;
}) {
  return (
    <View style={{
      flexDirection: "row", alignItems: "center", gap: spacing.md,
      paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: spacing.md,
      borderBottomWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
      backgroundColor: colors.surface,
    }}>
      {back ? <IconButton icon="chevron-left" onPress={back} size={36} tone="surface" accessibilityLabel="Back" /> : null}
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text numberOfLines={1} style={type.displayMd}>{title}</Text>
        {subtitle ? <Text numberOfLines={1} style={[type.bodyMuted, { marginTop: 2 }]}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  );
}

export const s = { spacing, colors, radius, type } as const;
