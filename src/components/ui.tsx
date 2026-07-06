// BuildCon House · Design System V1 · Primitives
// Every screen composes UI from this file. No hardcoded colors, spacing, or
// typography allowed anywhere else. Feels closer to Linear / Stripe / Notion.

import { Feather } from "@expo/vector-icons";
import { useMemo, useRef } from "react";
import {
  ActivityIndicator,
  Animated,
  Modal as RNModal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  useWindowDimensions,
  View,
  ViewStyle,
} from "react-native";

import {
  colors,
  elevation,
  icon as iconSize,
  layout,
  money,
  radius,
  spacing,
  type,
} from "@/src/theme/tokens";
import { color as ds, font as dsFont, statusTone, toneColor } from "@/src/design/tokens";

type FeatherName = keyof typeof Feather.glyphMap;

// ──────────────────────────────────────────────────────────────────────────
// Press-animated wrapper — subtle scale + opacity feedback for all touchables
// ──────────────────────────────────────────────────────────────────────────
export function useSpring(active: boolean, from = 1, to = 0.97) {
  const anim = useRef(new Animated.Value(from)).current;
  Animated.spring(anim, {
    toValue: active ? to : from,
    useNativeDriver: true,
    damping: 22,
    stiffness: 320,
    mass: 0.6,
  }).start();
  return anim;
}

// ──────────────────────────────────────────────────────────────────────────
// Button — primary / secondary / ghost / danger / brand-light
// ──────────────────────────────────────────────────────────────────────────
type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "brandLight" | "outline";
type ButtonSize = "sm" | "md" | "lg";
type ButtonProps = {
  label: string;
  onPress?: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: FeatherName;
  iconRight?: FeatherName;
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  testID?: string;
  style?: ViewStyle;
};

export function Button({
  label, onPress, variant = "primary", size = "md", icon, iconRight,
  loading, disabled, fullWidth, testID, style,
}: ButtonProps) {
  const sizing = {
    sm: { padV: 8,  padH: 12, fs: 13, iconSize: 14, radius: radius.sm, height: 34 },
    md: { padV: 11, padH: 16, fs: 14, iconSize: 16, radius: radius.md, height: 44 },
    lg: { padV: 14, padH: 20, fs: 15, iconSize: 18, radius: radius.md, height: 52 },
  }[size];

  const skin = {
    primary:    { bg: colors.brand,           fg: colors.onBrand,           border: colors.brand },
    secondary:  { bg: colors.surfaceSecondary, fg: colors.onSurface,         border: colors.border },
    ghost:      { bg: "transparent",           fg: colors.onSurface,         border: "transparent" },
    danger:     { bg: colors.error,           fg: colors.onBrand,           border: colors.error },
    brandLight: { bg: colors.brandTint,       fg: colors.brand,             border: colors.brandBorder },
    outline:    { bg: "transparent",           fg: colors.brand,             border: colors.brand },
  }[variant];

  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      disabled={loading || disabled}
      style={({ pressed }) => [
        {
          backgroundColor: skin.bg,
          borderColor: skin.border,
          borderWidth: variant === "ghost" ? 0 : 1,
          paddingVertical: sizing.padV,
          paddingHorizontal: sizing.padH,
          borderRadius: sizing.radius,
          minHeight: sizing.height,
          opacity: disabled ? 0.5 : pressed ? 0.88 : 1,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "center",
          gap: 8,
          alignSelf: fullWidth ? "stretch" : "flex-start",
          ...(variant === "primary" || variant === "danger" ? elevation.hairline : null),
        },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={skin.fg} size="small" />
      ) : icon ? (
        <Feather name={icon} size={sizing.iconSize} color={skin.fg} />
      ) : null}
      <Text style={{ color: skin.fg, fontSize: sizing.fs, fontFamily: type.titleMd.fontFamily, fontWeight: "600", letterSpacing: -0.1 }}>
        {label}
      </Text>
      {iconRight && !loading ? <Feather name={iconRight} size={sizing.iconSize} color={skin.fg} /> : null}
    </Pressable>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// IconButton — circular icon-only affordance
// ──────────────────────────────────────────────────────────────────────────
export function IconButton({
  icon, onPress, size = 40, tone = "surface", testID, accessibilityLabel, active, disabled, badge,
}: {
  icon: FeatherName;
  onPress?: () => void;
  size?: number;
  tone?: "surface" | "ghost" | "brand" | "brandLight" | "translucent" | "danger";
  testID?: string;
  accessibilityLabel?: string;
  active?: boolean;
  disabled?: boolean;
  badge?: number | string;
}) {
  const skin = {
    surface:     { bg: colors.surfaceSecondary, border: colors.border, fg: colors.onSurface },
    ghost:       { bg: "transparent",           border: "transparent", fg: colors.onSurface },
    brand:       { bg: colors.brand,            border: colors.brand,  fg: colors.onBrand },
    brandLight:  { bg: colors.brandTint,        border: colors.brandBorder, fg: colors.brand },
    translucent: { bg: "rgba(255,255,255,0.92)", border: colors.border, fg: colors.onSurface },
    danger:      { bg: colors.errorBg,          border: colors.errorBorder, fg: colors.error },
  }[tone];
  const iconSize = Math.max(14, Math.floor(size * 0.44));

  return (
    <Pressable
      testID={testID}
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      disabled={disabled}
      hitSlop={layout.hitSlop}
      style={({ pressed }) => [{
        width: size, height: size, borderRadius: size / 2,
        backgroundColor: skin.bg,
        borderWidth: tone === "ghost" ? 0 : StyleSheet.hairlineWidth,
        borderColor: skin.border,
        alignItems: "center", justifyContent: "center",
        opacity: disabled ? 0.5 : pressed ? 0.85 : 1,
      }]}
    >
      <Feather name={icon} size={iconSize} color={active ? colors.brand : skin.fg} />
      {badge !== undefined && badge !== 0 && badge !== "" ? (
        <View style={styles.iconBadge}>
          <Text style={styles.iconBadgeText}>{typeof badge === "number" && badge > 99 ? "99+" : String(badge)}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Card — elevated surface, single source of truth for cards.
// ──────────────────────────────────────────────────────────────────────────
export function Card({
  children, style, testID, variant = "flat", padding, onPress,
}: {
  children: React.ReactNode;
  style?: ViewStyle | ViewStyle[];
  testID?: string;
  variant?: "flat" | "elevated" | "outlined";
  padding?: number;
  onPress?: () => void;
}) {
  const skin = {
    flat:     { bg: colors.surfaceSecondary, borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border, shadow: null as any },
    elevated: { bg: colors.surfaceSecondary, borderWidth: 0,                        borderColor: "transparent",  shadow: elevation.low },
    outlined: { bg: "transparent",           borderWidth: 1,                        borderColor: colors.border,  shadow: null },
  }[variant];

  const content = (
    <View testID={testID} style={[
      {
        backgroundColor: skin.bg,
        borderRadius: radius.lg,
        borderWidth: skin.borderWidth,
        borderColor: skin.borderColor,
        padding: padding ?? spacing.lg,
      },
      skin.shadow,
      style,
    ]}>
      {children}
    </View>
  );

  if (onPress) {
    return (
      <Pressable onPress={onPress} style={({ pressed }) => ({ opacity: pressed ? 0.92 : 1 })}>
        {content}
      </Pressable>
    );
  }
  return content;
}

// ──────────────────────────────────────────────────────────────────────────
// Badge / StatusBadge / Chip
// ──────────────────────────────────────────────────────────────────────────
export function Badge({
  label, tone = "neutral", size = "md", icon, testID,
}: {
  label: string;
  tone?: "neutral" | "brand" | "success" | "warning" | "error" | "info";
  size?: "sm" | "md";
  icon?: FeatherName;
  testID?: string;
}) {
  const map = {
    neutral: { bg: colors.surfaceTertiary, fg: colors.onSurfaceSecondary, border: colors.border },
    brand:   { bg: colors.brandTint,       fg: colors.brand,              border: colors.brandBorder },
    success: { bg: colors.successBg,       fg: colors.success,            border: colors.successBorder },
    warning: { bg: colors.warningBg,       fg: colors.warning,            border: colors.warningBorder },
    error:   { bg: colors.errorBg,         fg: colors.error,              border: colors.errorBorder },
    info:    { bg: colors.infoBg,          fg: colors.info,               border: colors.infoBorder },
  }[tone];
  const padV = size === "sm" ? 2 : 4;
  const padH = size === "sm" ? 6 : 9;
  const fs = size === "sm" ? 10 : 11;

  return (
    <View testID={testID} style={{
      backgroundColor: map.bg,
      paddingHorizontal: padH,
      paddingVertical: padV,
      borderRadius: radius.pill,
      alignSelf: "flex-start",
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: map.border,
      flexDirection: "row",
      alignItems: "center",
      gap: 4,
    }}>
      {icon ? <Feather name={icon} size={fs + 1} color={map.fg} /> : null}
      <Text style={{ color: map.fg, fontSize: fs, fontFamily: type.titleMd.fontFamily, fontWeight: "600", letterSpacing: 0.1 }}>
        {label}
      </Text>
    </View>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const meta = statusTone[status] || { label: status, tone: "neutral" as const };
  const t = toneColor[meta.tone];
  return (
    <View style={{
      flexDirection: "row",
      alignItems: "center",
      gap: 6,
      backgroundColor: t.tint,
      paddingHorizontal: 10,
      paddingVertical: 4,
      borderRadius: radius.pill,
      alignSelf: "flex-start",
    }}>
      <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: t.dot }} />
      <Text style={{ color: t.fg, fontSize: 11, fontFamily: type.titleMd.fontFamily, fontWeight: "600", letterSpacing: 0.2 }}>
        {meta.label}
      </Text>
    </View>
  );
}

export function Chip({
  label, active, onPress, testID, icon, count,
}: {
  label: string; active?: boolean; onPress?: () => void; testID?: string;
  icon?: FeatherName; count?: number;
}) {
  return (
    <Pressable
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => ({
        height: 34,
        paddingHorizontal: 14,
        borderRadius: radius.pill,
        borderWidth: 1,
        borderColor: active ? ds.brassLine : colors.border,
        backgroundColor: active ? ds.brassTint : colors.surfaceSecondary,
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "row",
        gap: 6,
        flexShrink: 0,
        opacity: pressed ? 0.85 : 1,
      })}
    >
      {icon ? <Feather name={icon} size={13} color={active ? ds.brassDeep : colors.onSurfaceSecondary} /> : null}
      <Text style={{
        color: active ? ds.brassDeep : colors.onSurface,
        fontSize: 13,
        fontFamily: type.bodyStrong.fontFamily,
        fontWeight: active ? "600" : "500",
      }}>
        {label}
      </Text>
      {typeof count === "number" ? (
        <View style={{
          backgroundColor: active ? "rgba(140,115,81,0.16)" : colors.surfaceTertiary,
          paddingHorizontal: 6,
          paddingVertical: 1,
          borderRadius: radius.pill,
          marginLeft: 2,
        }}>
          <Text style={{
            color: active ? ds.brassDeep : colors.onSurfaceSecondary,
            fontSize: 11,
            fontFamily: type.titleMd.fontFamily,
            fontWeight: "600",
          }}>
            {count}
          </Text>
        </View>
      ) : null}
    </Pressable>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Divider / Skeleton
// ──────────────────────────────────────────────────────────────────────────
export function Divider({ vertical, style, inset }: { vertical?: boolean; style?: ViewStyle; inset?: number }) {
  return (
    <View style={[
      vertical
        ? { width: StyleSheet.hairlineWidth, alignSelf: "stretch" }
        : { height: StyleSheet.hairlineWidth, alignSelf: "stretch", marginLeft: inset || 0 },
      { backgroundColor: colors.divider },
      style,
    ]} />
  );
}

export function Skeleton({ w = "100%", h = 14, style, radius: r }: { w?: number | string; h?: number; style?: ViewStyle; radius?: number }) {
  const pulse = useRef(new Animated.Value(0.5)).current;
  useMemo(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 900, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.5, duration: 900, useNativeDriver: true }),
      ]),
    ).start();
  }, [pulse]);

  return (
    <Animated.View style={[
      { width: w as any, height: h, backgroundColor: colors.surfaceTertiary, borderRadius: r ?? 8, opacity: pulse },
      style,
    ]} />
  );
}

// ──────────────────────────────────────────────────────────────────────────
// EmptyState / ErrorState / LoadingState
// ──────────────────────────────────────────────────────────────────────────
export function EmptyState({
  icon = "inbox", title, subtitle, action, tone = "neutral",
}: {
  icon?: FeatherName;
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  tone?: "neutral" | "brand";
}) {
  const chipBg = tone === "brand" ? colors.brandTint : colors.surfaceTertiary;
  const iconFg = tone === "brand" ? colors.brand : colors.onSurfaceMuted;
  return (
    <View style={{ alignItems: "center", padding: spacing.xxl, gap: spacing.md }}>
      <View style={{
        width: 64, height: 64, borderRadius: radius.pill,
        backgroundColor: chipBg,
        alignItems: "center", justifyContent: "center",
      }}>
        <Feather name={icon} size={26} color={iconFg} />
      </View>
      <Text style={[type.titleMd, { textAlign: "center" }]}>{title}</Text>
      {subtitle ? <Text style={[type.bodyMuted, { textAlign: "center", maxWidth: 320 }]}>{subtitle}</Text> : null}
      {action ? <View style={{ marginTop: 4 }}>{action}</View> : null}
    </View>
  );
}

export function ErrorState({
  title = "Something went wrong", subtitle, onRetry,
}: {
  title?: string; subtitle?: string; onRetry?: () => void;
}) {
  return (
    <EmptyState
      icon="alert-triangle"
      title={title}
      subtitle={subtitle}
      action={onRetry ? <Button label="Try again" icon="refresh-cw" variant="secondary" onPress={onRetry} /> : undefined}
    />
  );
}

export function LoadingState({ label }: { label?: string }) {
  return (
    <View style={{ alignItems: "center", padding: spacing.xxl, gap: spacing.md }}>
      <ActivityIndicator size="small" color={colors.brand} />
      {label ? <Text style={type.bodyMuted}>{label}</Text> : null}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// SectionHeader / ScreenTitle
// ──────────────────────────────────────────────────────────────────────────
export function SectionHeader({
  title, subtitle, right, tone = "default",
}: {
  title: string; subtitle?: string; right?: React.ReactNode;
  tone?: "default" | "compact";
}) {
  const titleStyle = tone === "compact" ? type.titleMd : type.titleLg;
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end", marginBottom: spacing.md, gap: spacing.md }}>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={titleStyle} numberOfLines={1}>{title}</Text>
        {subtitle ? <Text style={[type.bodyMuted, { marginTop: 2 }]} numberOfLines={2}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  );
}

export function ScreenTitle({
  title, subtitle, right, back,
}: {
  title: string; subtitle?: string | null; right?: React.ReactNode; back?: () => void;
}) {
  return (
    <View style={{
      flexDirection: "row", alignItems: "center", gap: spacing.md,
      paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: spacing.md,
      backgroundColor: colors.surface,
    }}>
      {back ? <IconButton icon="chevron-left" onPress={back} size={38} tone="surface" accessibilityLabel="Back" /> : null}
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text numberOfLines={1} style={type.displayMd}>{title}</Text>
        {subtitle ? <Text numberOfLines={1} style={[type.bodyMuted, { marginTop: 2 }]}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// SegmentedControl — iOS-native feel
// ──────────────────────────────────────────────────────────────────────────
export function SegmentedControl<T extends string>({
  value, options, onChange, size = "md", testID, fullWidth,
}: {
  value: T;
  options: { value: T; label: string; icon?: FeatherName }[];
  onChange: (v: T) => void;
  size?: "sm" | "md";
  testID?: string;
  fullWidth?: boolean;
}) {
  const h = size === "sm" ? 32 : 40;
  return (
    <View testID={testID} style={{
      flexDirection: "row",
      backgroundColor: colors.surfaceTertiary,
      borderRadius: radius.md,
      padding: 3,
      height: h,
      alignSelf: fullWidth ? "stretch" : "flex-start",
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
              paddingHorizontal: 12, minWidth: 60,
              alignItems: "center", justifyContent: "center",
              flexDirection: "row", gap: 6,
              backgroundColor: on ? colors.surfaceSecondary : "transparent",
              ...(on ? elevation.hairline : null),
            }}
          >
            {o.icon ? <Feather name={o.icon} size={13} color={on ? colors.onSurface : colors.onSurfaceMuted} /> : null}
            <Text style={{
              fontSize: size === "sm" ? 12 : 13,
              fontFamily: type.titleMd.fontFamily,
              fontWeight: on ? "600" : "500",
              color: on ? colors.onSurface : colors.onSurfaceMuted,
            }}>
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Tabs — underline scrolling nav (like Linear / Notion)
// ──────────────────────────────────────────────────────────────────────────
export function Tabs<T extends string>({
  value, options, onChange, testID,
}: {
  value: T;
  options: { value: T; label: string; count?: number }[];
  onChange: (v: T) => void;
  testID?: string;
}) {
  return (
    <View testID={testID} style={{
      flexDirection: "row",
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: colors.border,
    }}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={String(o.value)}
            testID={testID ? `${testID}-${o.value}` : undefined}
            onPress={() => onChange(o.value)}
            style={{
              paddingVertical: 10,
              paddingHorizontal: 4,
              marginRight: 20,
              borderBottomWidth: 2,
              borderBottomColor: on ? colors.brand : "transparent",
              flexDirection: "row",
              alignItems: "center",
              gap: 6,
            }}
          >
            <Text style={{
              fontSize: 14,
              fontFamily: type.titleMd.fontFamily,
              fontWeight: on ? "600" : "500",
              color: on ? colors.onSurface : colors.onSurfaceMuted,
              letterSpacing: -0.1,
            }}>
              {o.label}
            </Text>
            {typeof o.count === "number" ? (
              <View style={{
                backgroundColor: on ? colors.brandTint : colors.surfaceTertiary,
                paddingHorizontal: 6, paddingVertical: 1, borderRadius: radius.pill,
              }}>
                <Text style={{
                  fontSize: 10,
                  fontFamily: type.titleMd.fontFamily,
                  fontWeight: "600",
                  color: on ? colors.brand : colors.onSurfaceMuted,
                }}>{o.count}</Text>
              </View>
            ) : null}
          </Pressable>
        );
      })}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// TextField — unified input for the whole app
// ──────────────────────────────────────────────────────────────────────────
export function TextField({
  label, error, helper, leftIcon, rightIcon, onRightPress, containerStyle, ...rest
}: TextInputProps & {
  label?: string;
  error?: string | null;
  helper?: string;
  leftIcon?: FeatherName;
  rightIcon?: FeatherName;
  onRightPress?: () => void;
  containerStyle?: ViewStyle;
}) {
  const showError = !!error;
  return (
    <View style={[{ gap: 6 }, containerStyle]}>
      {label ? <Text style={type.label}>{label}</Text> : null}
      <View style={{
        flexDirection: "row", alignItems: "center",
        backgroundColor: colors.surfaceSecondary,
        borderWidth: 1,
        borderColor: showError ? colors.error : colors.border,
        borderRadius: radius.md,
        paddingHorizontal: leftIcon ? 12 : 14,
        minHeight: 48,
      }}>
        {leftIcon ? <Feather name={leftIcon} size={16} color={colors.onSurfaceMuted} style={{ marginRight: 8 }} /> : null}
        <TextInput
          {...rest}
          placeholderTextColor={colors.onSurfaceSubtle}
          style={[{
            flex: 1,
            paddingVertical: Platform.OS === "ios" ? 12 : 8,
            fontSize: 15,
            fontFamily: type.body.fontFamily,
            color: colors.onSurface,
          }, rest.style]}
        />
        {rightIcon ? (
          <Pressable onPress={onRightPress} hitSlop={layout.hitSlop} style={{ marginLeft: 8 }}>
            <Feather name={rightIcon} size={16} color={colors.onSurfaceMuted} />
          </Pressable>
        ) : null}
      </View>
      {helper && !showError ? <Text style={type.caption}>{helper}</Text> : null}
      {showError ? <Text style={[type.caption, { color: colors.error }]}>{error}</Text> : null}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// SearchField — compact search input
// ──────────────────────────────────────────────────────────────────────────
export function SearchField(props: TextInputProps & { onClear?: () => void }) {
  const hasValue = typeof props.value === "string" && props.value.length > 0;
  return (
    <View style={{
      flexDirection: "row", alignItems: "center",
      backgroundColor: colors.surfaceTertiary,
      borderRadius: radius.md,
      paddingHorizontal: 12,
      height: 40,
    }}>
      <Feather name="search" size={15} color={colors.onSurfaceMuted} style={{ marginRight: 8 }} />
      <TextInput
        {...props}
        placeholderTextColor={colors.onSurfaceMuted}
        style={[{
          flex: 1, fontSize: 14, fontFamily: type.body.fontFamily,
          color: colors.onSurface, paddingVertical: 0,
        }, props.style]}
      />
      {hasValue && props.onClear ? (
        <Pressable onPress={props.onClear} hitSlop={layout.hitSlop}>
          <Feather name="x" size={14} color={colors.onSurfaceMuted} />
        </Pressable>
      ) : null}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// KPI card — dashboard number tile
// ──────────────────────────────────────────────────────────────────────────
export function KpiCard({
  label, value, sub, icon, tone = "neutral", trend, onPress, style,
}: {
  label: string;
  value: string;
  sub?: string;
  icon?: FeatherName;
  tone?: "neutral" | "brand" | "success" | "warning";
  trend?: { value: string; direction: "up" | "down" };
  onPress?: () => void;
  style?: ViewStyle;
}) {
  const toneMap = {
    neutral: { bg: colors.surfaceSecondary, iconBg: colors.surfaceTertiary, iconFg: colors.onSurfaceMuted },
    brand:   { bg: colors.surfaceSecondary, iconBg: colors.brandTint,      iconFg: colors.brand },
    success: { bg: colors.surfaceSecondary, iconBg: colors.successBg,     iconFg: colors.success },
    warning: { bg: colors.surfaceSecondary, iconBg: colors.warningBg,     iconFg: colors.warning },
  }[tone];

  const Container: any = onPress ? Pressable : View;
  return (
    <Container
      onPress={onPress}
      style={[{
        backgroundColor: toneMap.bg,
        borderRadius: radius.lg,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        padding: spacing.lg,
        gap: 10,
      }, style]}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={type.captionStrong}>{label}</Text>
        {icon ? (
          <View style={{
            width: 32, height: 32, borderRadius: 10,
            backgroundColor: toneMap.iconBg,
            alignItems: "center", justifyContent: "center",
          }}>
            <Feather name={icon} size={16} color={toneMap.iconFg} />
          </View>
        ) : null}
      </View>
      <Text style={{
        fontSize: 26,
        fontFamily: type.displayMd.fontFamily,
        fontWeight: "700",
        color: colors.onSurface,
        letterSpacing: -0.5,
        fontVariant: ["tabular-nums"],
      }} numberOfLines={1} adjustsFontSizeToFit>
        {value}
      </Text>
      {sub || trend ? (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          {trend ? (
            <View style={{
              flexDirection: "row", alignItems: "center", gap: 3,
              backgroundColor: trend.direction === "up" ? colors.successBg : colors.errorBg,
              paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.sm,
            }}>
              <Feather
                name={trend.direction === "up" ? "trending-up" : "trending-down"}
                size={11}
                color={trend.direction === "up" ? colors.success : colors.error}
              />
              <Text style={{
                fontSize: 11,
                fontFamily: type.titleMd.fontFamily,
                fontWeight: "600",
                color: trend.direction === "up" ? colors.success : colors.error,
              }}>
                {trend.value}
              </Text>
            </View>
          ) : null}
          {sub ? <Text style={type.caption}>{sub}</Text> : null}
        </View>
      ) : null}
    </Container>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// ListRow — unified tappable row for lists (customers, quotations, payments)
// ──────────────────────────────────────────────────────────────────────────
export function ListRow({
  title, subtitle, meta, metaSecondary, right, leading, onPress, testID, isFirst, isLast,
}: {
  title: string;
  subtitle?: string;
  meta?: string;
  metaSecondary?: string;
  right?: React.ReactNode;
  leading?: React.ReactNode;
  onPress?: () => void;
  testID?: string;
  isFirst?: boolean;
  isLast?: boolean;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed }) => ({
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.md,
        paddingHorizontal: spacing.lg,
        paddingVertical: 14,
        backgroundColor: pressed ? colors.surfaceTertiary : "transparent",
        borderTopWidth: isFirst ? 0 : StyleSheet.hairlineWidth,
        borderColor: colors.divider,
      })}
    >
      {leading}
      <View style={{ flex: 1, minWidth: 0, gap: 2 }}>
        <Text numberOfLines={1} style={{
          fontSize: 15,
          fontFamily: type.titleMd.fontFamily,
          fontWeight: "600",
          color: colors.onSurface,
          letterSpacing: -0.1,
        }}>{title}</Text>
        {subtitle ? <Text numberOfLines={1} style={type.caption}>{subtitle}</Text> : null}
      </View>
      <View style={{ alignItems: "flex-end", gap: 4 }}>
        {meta ? <Text style={{
          fontSize: 14,
          fontFamily: type.titleMd.fontFamily,
          fontWeight: "600",
          color: colors.onSurface,
          fontVariant: ["tabular-nums"],
        }}>{meta}</Text> : null}
        {metaSecondary ? <Text style={type.caption}>{metaSecondary}</Text> : null}
        {right}
      </View>
    </Pressable>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Avatar — initials-based
// ──────────────────────────────────────────────────────────────────────────
export function Avatar({
  name, size = 36, tone = "brand",
}: {
  name?: string; size?: number; tone?: "brand" | "surface" | "neutral";
}) {
  const initials = (name || "?")
    .split(" ")
    .map((s) => s[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const skin = {
    brand:   { bg: colors.brand,           fg: colors.onBrand },
    surface: { bg: colors.surfaceTertiary, fg: colors.onSurfaceSecondary },
    neutral: { bg: colors.surfaceInverse,  fg: colors.onSurfaceInverse },
  }[tone];

  return (
    <View style={{
      width: size, height: size, borderRadius: size / 2,
      backgroundColor: skin.bg,
      alignItems: "center", justifyContent: "center",
    }}>
      <Text style={{
        color: skin.fg,
        fontSize: size * 0.36,
        fontFamily: type.titleMd.fontFamily,
        fontWeight: "600",
        letterSpacing: 0.2,
      }}>
        {initials}
      </Text>
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// PriceTag — consistent price rendering (with optional strike-through MRP)
// ──────────────────────────────────────────────────────────────────────────
export function PriceTag({
  price, mrp, size = "md", align = "left",
}: {
  price: number;
  mrp?: number;
  size?: "sm" | "md" | "lg" | "xl";
  align?: "left" | "right";
}) {
  const showSlash = typeof mrp === "number" && mrp > price;
  const priceSize = size === "xl" ? 26 : size === "lg" ? 20 : size === "sm" ? 13 : 16;
  const mrpSize   = size === "xl" ? 14 : size === "lg" ? 13 : size === "sm" ? 11 : 12;
  return (
    <View style={{ flexDirection: "row", alignItems: "baseline", gap: 6, justifyContent: align === "right" ? "flex-end" : "flex-start", flexWrap: "wrap" }}>
      <Text style={{
        fontSize: priceSize,
        fontFamily: type.titleMd.fontFamily,
        fontWeight: "700",
        color: colors.onSurface,
        fontVariant: ["tabular-nums"],
        letterSpacing: -0.2,
      }}>{money(price)}</Text>
      {showSlash ? (
        <Text style={{
          fontSize: mrpSize,
          color: colors.onSurfaceMuted,
          textDecorationLine: "line-through",
          fontVariant: ["tabular-nums"],
          fontFamily: type.body.fontFamily,
        }}>{money(mrp!)}</Text>
      ) : null}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// BrandMark — the little BC logo tile
// ──────────────────────────────────────────────────────────────────────────
export function BrandMark({ size = 32, inverse }: { size?: number; inverse?: boolean }) {
  return (
    <View style={{
      width: size, height: size, borderRadius: Math.max(8, size * 0.28),
      backgroundColor: inverse ? "rgba(255,255,255,0.14)" : colors.brand,
      borderWidth: inverse ? 1 : 0,
      borderColor: inverse ? "rgba(255,255,255,0.24)" : "transparent",
      alignItems: "center", justifyContent: "center",
    }}>
      <Feather name="home" size={size * 0.48} color={inverse ? colors.onSurfaceInverse : colors.onBrand} />
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Alerts — inline info/success/warning/error surfaces
// ──────────────────────────────────────────────────────────────────────────
export function Alert({
  tone, title, description, icon, action,
}: {
  tone: "info" | "success" | "warning" | "error";
  title: string;
  description?: string;
  icon?: FeatherName;
  action?: React.ReactNode;
}) {
  const map = {
    info:    { bg: colors.infoBg,    fg: colors.info,    border: colors.infoBorder,    icon: (icon || "info") as FeatherName },
    success: { bg: colors.successBg, fg: colors.success, border: colors.successBorder, icon: (icon || "check-circle") as FeatherName },
    warning: { bg: colors.warningBg, fg: colors.warning, border: colors.warningBorder, icon: (icon || "alert-triangle") as FeatherName },
    error:   { bg: colors.errorBg,   fg: colors.error,   border: colors.errorBorder,   icon: (icon || "x-circle") as FeatherName },
  }[tone];

  return (
    <View style={{
      backgroundColor: map.bg,
      borderColor: map.border,
      borderWidth: 1,
      borderRadius: radius.md,
      padding: spacing.md,
      flexDirection: "row",
      gap: spacing.md,
      alignItems: "flex-start",
    }}>
      <Feather name={map.icon} size={16} color={map.fg} style={{ marginTop: 2 }} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={{ fontSize: 13, fontFamily: type.titleMd.fontFamily, fontWeight: "600", color: map.fg }}>{title}</Text>
        {description ? <Text style={{ fontSize: 13, fontFamily: type.body.fontFamily, color: map.fg, opacity: 0.9, lineHeight: 18 }}>{description}</Text> : null}
      </View>
      {action}
    </View>
  );
}

// Style-sheet for internal use
const styles = StyleSheet.create({
  iconBadge: {
    position: "absolute",
    top: -2, right: -2,
    minWidth: 16, height: 16, paddingHorizontal: 4,
    borderRadius: radius.pill,
    backgroundColor: colors.error,
    alignItems: "center", justifyContent: "center",
    borderWidth: 1.5, borderColor: colors.surfaceSecondary,
  },
  iconBadgeText: {
    color: colors.onBrand,
    fontSize: 9,
    fontFamily: type.titleMd.fontFamily,
    fontWeight: "700",
  },
});

// Legacy helper
export const s = { spacing, colors, radius, type } as const;

// ══════════════════════════════════════════════════════════════════════════
// DESIGN SYSTEM · Phase 3 additions — Sheet, Modal, PageHeader, HeroBanner,
// StatTile, DataTable, richer Skeletons, HoverCard, FormField, Toolbar.
// All primitives below consume only tokens; no hardcoded hex, spacing, or
// typography. Every dialog and drawer shares identical chrome.
// ══════════════════════════════════════════════════════════════════════════

// ──────────────────────────────────────────────────────────────────────────
// Icon — one canonical way to render an icon anywhere in the app.
// ──────────────────────────────────────────────────────────────────────────
export function Icon({
  name, size = "md", color, style,
}: {
  name: FeatherName;
  size?: keyof typeof iconSize;
  color?: string;
  style?: any;
}) {
  return <Feather name={name} size={iconSize[size]} color={color || colors.onSurface} style={style} />;
}

// ──────────────────────────────────────────────────────────────────────────
// Sheet — the ONE dialog/drawer primitive.
//   variant:
//     drawer  → right-anchored 460px panel on desktop, bottom-sheet on phone (default)
//     modal   → center dialog on all breakpoints (max 520px)
//     bottom  → always bottom sheet
// Chrome (header + body scroll area + footer) identical for every screen.
// ──────────────────────────────────────────────────────────────────────────
type SheetVariant = "drawer" | "modal" | "bottom";
export function Sheet({
  visible, onClose, title, subtitle, variant = "drawer",
  children, footer, width, testID, dismissable = true, headerRight,
}: {
  visible: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  variant?: SheetVariant;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: number;
  testID?: string;
  dismissable?: boolean;
  headerRight?: React.ReactNode;
}) {
  const { width: winW } = useWindowDimensions();
  const isDesktop = winW >= 900;
  const kind: "right" | "center" | "bottom" =
    variant === "modal" ? "center"
    : variant === "bottom" ? "bottom"
    : (isDesktop ? "right" : "bottom");

  const panelStyle: ViewStyle = kind === "right" ? {
    height: "100%",
    width: width || layout.sheet.drawerWidth,
    maxWidth: "100%",
    borderTopLeftRadius: radius.lg,
    borderBottomLeftRadius: radius.lg,
    marginLeft: "auto",
  } : kind === "center" ? {
    width: "100%",
    maxWidth: width || layout.sheet.modalMaxWidth,
    maxHeight: "90%",
    borderRadius: radius.lg,
    alignSelf: "center",
    marginTop: "auto",
    marginBottom: "auto",
  } : {
    width: "100%",
    maxHeight: "92%",
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    marginTop: "auto",
  };

  const backdropAlign: ViewStyle =
    kind === "right"  ? { justifyContent: "flex-start", flexDirection: "row" }
  : kind === "center" ? { justifyContent: "center", alignItems: "center", padding: spacing.lg }
  :                     { justifyContent: "flex-end" };

  return (
    <RNModal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={[{ flex: 1, backgroundColor: colors.overlay }, backdropAlign]}>
        {dismissable ? <Pressable onPress={onClose} style={StyleSheet.absoluteFillObject} /> : null}
        <View
          testID={testID}
          style={[
            { backgroundColor: colors.surfaceSecondary, overflow: "hidden" },
            elevation.high,
            panelStyle,
          ]}
        >
          {/* Header — identical everywhere */}
          {title || onClose ? (
            <View style={sheetStyles.header}>
              <View style={{ flex: 1, minWidth: 0 }}>
                {title ? <Text numberOfLines={1} style={type.titleLg}>{title}</Text> : null}
                {subtitle ? <Text numberOfLines={2} style={[type.bodyMuted, { marginTop: 2 }]}>{subtitle}</Text> : null}
              </View>
              {headerRight}
              <IconButton icon="x" onPress={onClose} tone="ghost" size={36} accessibilityLabel="Close" testID={testID ? `${testID}-close` : undefined} />
            </View>
          ) : null}

          {/* Body */}
          <View style={{ flex: 1, minHeight: 0 }}>
            {children}
          </View>

          {/* Footer — identical everywhere */}
          {footer ? (
            <View style={sheetStyles.footer}>{footer}</View>
          ) : null}
        </View>
      </View>
    </RNModal>
  );
}

const sheetStyles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    minHeight: layout.sheet.headerHeight,
  },
  footer: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    minHeight: layout.sheet.footerHeight,
  },
});

// ──────────────────────────────────────────────────────────────────────────
// PageHeader — every screen top. Always identical chrome.
// Optional back button, title, subtitle, action cluster (right).
// ──────────────────────────────────────────────────────────────────────────
export function PageHeader({
  title, subtitle, actions, back, overline, testID, dense,
}: {
  title: string;
  subtitle?: string | null;
  actions?: React.ReactNode;
  back?: () => void;
  overline?: string;
  testID?: string;
  dense?: boolean;
}) {
  return (
    <View
      testID={testID}
      style={{
        paddingHorizontal: spacing.xl,
        paddingTop: dense ? spacing.md : spacing.lg,
        paddingBottom: dense ? spacing.md : spacing.lg,
        backgroundColor: colors.surface,
        borderBottomWidth: StyleSheet.hairlineWidth,
        borderBottomColor: colors.border,
        position: "relative",
        zIndex: 20,
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
        {back ? <IconButton icon="chevron-left" onPress={back} size={36} tone="surface" accessibilityLabel="Back" /> : null}
        <View style={{ flex: 1, minWidth: 0 }}>
          {overline ? <Text style={[type.overline, { marginBottom: 4 }]}>{overline}</Text> : null}
          <Text
            numberOfLines={1}
            style={
              dense
                ? type.titleLg
                : { fontFamily: dsFont.display, fontSize: 28, lineHeight: 36, letterSpacing: -0.3, color: colors.onSurface }
            }
          >
            {title}
          </Text>
          {subtitle ? <Text numberOfLines={2} style={[type.bodyMuted, { marginTop: 2 }]}>{subtitle}</Text> : null}
        </View>
        {actions ? <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>{actions}</View> : null}
      </View>
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// HeroBanner — the "brand card" hero used on Payments, Purchases, Followups.
// Soft blue-tinted background, overline, title, subtitle, optional action cluster.
// ──────────────────────────────────────────────────────────────────────────
export function HeroBanner({
  overline, title, subtitle, actions, tone = "brand", icon: iconName,
}: {
  overline?: string;
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  tone?: "brand" | "neutral";
  icon?: FeatherName;
}) {
  const bg = tone === "brand" ? colors.brandTint : colors.surfaceTertiary;
  const border = tone === "brand" ? colors.brandBorder : colors.border;
  return (
    <View style={{
      padding: spacing.xl,
      borderRadius: radius.lg,
      backgroundColor: bg,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: border,
      flexDirection: "row",
      gap: spacing.lg,
      alignItems: "flex-start",
    }}>
      {iconName ? (
        <View style={{
          width: 48, height: 48, borderRadius: radius.md,
          backgroundColor: colors.surfaceSecondary,
          alignItems: "center", justifyContent: "center",
          ...elevation.hairline,
        }}>
          <Feather name={iconName} size={iconSize.xl} color={colors.brand} />
        </View>
      ) : null}
      <View style={{ flex: 1, minWidth: 0 }}>
        {overline ? <Text style={[type.overline, { marginBottom: 6 }]}>{overline}</Text> : null}
        <Text style={type.displayMd} numberOfLines={2}>{title}</Text>
        {subtitle ? <Text style={[type.bodyMuted, { marginTop: 6, maxWidth: 640 }]}>{subtitle}</Text> : null}
      </View>
      {actions ? (
        <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center", flexShrink: 0 }}>{actions}</View>
      ) : null}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// StatTile — dashboard/hero stat card with icon, label, big number, delta.
// Auto-scales the value at narrow widths. Every tile identical across the app.
// ──────────────────────────────────────────────────────────────────────────
export function StatTile({
  label, value, sub, icon, tone = "neutral", onPress, style, dense,
}: {
  label: string;
  value: string | number;
  sub?: string;
  icon?: FeatherName;
  tone?: "neutral" | "brand" | "success" | "warning" | "danger";
  onPress?: () => void;
  style?: ViewStyle;
  dense?: boolean;
}) {
  const map = {
    neutral: { iconBg: colors.surfaceTertiary, iconFg: colors.onSurfaceSecondary, valueFg: colors.onSurface },
    brand:   { iconBg: colors.brandTint,       iconFg: colors.brand,              valueFg: colors.onSurface },
    success: { iconBg: colors.successBg,       iconFg: colors.success,            valueFg: colors.success },
    warning: { iconBg: colors.warningBg,       iconFg: colors.warning,            valueFg: colors.warning },
    danger:  { iconBg: colors.errorBg,         iconFg: colors.error,              valueFg: colors.error },
  }[tone];

  const Container: any = onPress ? Pressable : View;
  return (
    <Container
      onPress={onPress}
      style={[{
        flex: 1,
        minWidth: 150,
        padding: dense ? spacing.md : spacing.lg,
        borderRadius: radius.lg,
        backgroundColor: colors.surfaceSecondary,
        borderWidth: StyleSheet.hairlineWidth,
        borderColor: colors.border,
        gap: dense ? 8 : spacing.md,
      }, elevation.hairline as any, style]}
    >
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm }}>
        <Text
          style={[type.overline, { flex: 1 }]}
          numberOfLines={2}
          ellipsizeMode="tail"
        >
          {label}
        </Text>
        {icon ? (
          <View style={{
            width: dense ? 28 : 32, height: dense ? 28 : 32, borderRadius: radius.sm,
            backgroundColor: map.iconBg,
            alignItems: "center", justifyContent: "center",
            flexShrink: 0,
          }}>
            <Feather name={icon} size={dense ? iconSize.sm : iconSize.md} color={map.iconFg} />
          </View>
        ) : null}
      </View>
      <Text
        style={{
          fontSize: dense ? 20 : 24,
          fontFamily: type.displayMd.fontFamily,
          fontWeight: "700",
          color: map.valueFg,
          letterSpacing: -0.4,
          fontVariant: ["tabular-nums"],
        }}
        numberOfLines={1}
        adjustsFontSizeToFit
        minimumFontScale={0.55}
      >
        {String(value)}
      </Text>
      {sub ? <Text style={type.caption} numberOfLines={1}>{sub}</Text> : null}
    </Container>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// DataTable — Table / TableHeader / TableRow / TableCell primitives.
// Every table in the app shares row height, header height, hover, and typography.
// ──────────────────────────────────────────────────────────────────────────
export function Table({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return (
    <View style={[{
      backgroundColor: colors.surfaceSecondary,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: colors.border,
      borderRadius: radius.md,
      overflow: "hidden",
    }, style]}>
      {children}
    </View>
  );
}

export function TableHeader({ columns }: { columns: { label: string; flex?: number; width?: number; align?: "left" | "right" | "center" }[] }) {
  return (
    <View style={{
      flexDirection: "row",
      minHeight: layout.table.headerHeight,
      alignItems: "center",
      paddingHorizontal: layout.table.cellPaddingX,
      backgroundColor: colors.surfaceSubtle,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: colors.border,
      gap: spacing.md,
    }}>
      {columns.map((c, i) => (
        <Text
          key={i}
          numberOfLines={1}
          style={[
            type.overline,
            {
              flex: c.width ? undefined : (c.flex ?? 1),
              width: c.width,
              textAlign: c.align || "left",
            },
          ]}
        >
          {c.label}
        </Text>
      ))}
    </View>
  );
}

export function TableRow({
  children, onPress, isLast, testID, active,
}: {
  children: React.ReactNode;
  onPress?: () => void;
  isLast?: boolean;
  testID?: string;
  active?: boolean;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      style={({ pressed, hovered }: any) => [{
        flexDirection: "row",
        minHeight: layout.table.rowHeight,
        alignItems: "center",
        paddingHorizontal: layout.table.cellPaddingX,
        borderBottomWidth: isLast ? 0 : StyleSheet.hairlineWidth,
        borderBottomColor: colors.divider,
        backgroundColor:
          active ? colors.brandTint
          : pressed ? colors.surfaceTertiary
          : hovered ? colors.surfaceSubtle
          : "transparent",
        gap: spacing.md,
      }]}
    >
      {children}
    </Pressable>
  );
}

export function TableCell({
  children, flex, width, align = "left", testID,
}: {
  children: React.ReactNode;
  flex?: number;
  width?: number;
  align?: "left" | "right" | "center";
  testID?: string;
}) {
  return (
    <View
      testID={testID}
      style={{
        flex: width ? undefined : (flex ?? 1),
        width,
        flexDirection: align === "right" ? "row-reverse" : "row",
        justifyContent: align === "center" ? "center" : "flex-start",
        alignItems: "center",
        gap: spacing.sm,
      }}
    >
      {children}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Skeleton library — SkeletonRow, SkeletonCard, SkeletonGrid, SkeletonList.
// Consistent shimmer for every loading state.
// ──────────────────────────────────────────────────────────────────────────
export function SkeletonRow({ height = 14, widths }: { height?: number; widths?: (number | string)[] }) {
  const cols = widths || ["40%", "20%", "20%", "12%"];
  return (
    <View style={{ flexDirection: "row", gap: spacing.md, alignItems: "center", minHeight: layout.table.rowHeight, paddingHorizontal: layout.table.cellPaddingX }}>
      {cols.map((w, i) => (
        <Skeleton key={i} w={w as any} h={height} radius={radius.sm} style={{ flex: typeof w === "string" && w.endsWith("%") ? 0 : 1 }} />
      ))}
    </View>
  );
}

export function SkeletonCard({ height = 120 }: { height?: number }) {
  return (
    <View style={{
      padding: spacing.lg,
      borderRadius: radius.lg,
      backgroundColor: colors.surfaceSecondary,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: colors.border,
      gap: spacing.md,
      minHeight: height,
    }}>
      <Skeleton w="60%" h={12} radius={radius.sm} />
      <Skeleton w="40%" h={22} radius={radius.sm} />
      <Skeleton w="80%" h={12} radius={radius.sm} />
    </View>
  );
}

export function SkeletonList({ rows = 5 }: { rows?: number }) {
  return (
    <View style={{
      backgroundColor: colors.surfaceSecondary,
      borderRadius: radius.md,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: colors.border,
      overflow: "hidden",
    }}>
      {Array.from({ length: rows }).map((_, i) => (
        <View key={i} style={{
          borderBottomWidth: i === rows - 1 ? 0 : StyleSheet.hairlineWidth,
          borderBottomColor: colors.divider,
        }}>
          <SkeletonRow />
        </View>
      ))}
    </View>
  );
}

export function SkeletonGrid({ columns = 3, cards = 6 }: { columns?: number; cards?: number }) {
  return (
    <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
      {Array.from({ length: cards }).map((_, i) => (
        <View key={i} style={{ flexBasis: `${100 / columns - 1}%`, flexGrow: 1, minWidth: 200 }}>
          <SkeletonCard height={160} />
        </View>
      ))}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// FormField — label + helper + child input. Consistent form spacing everywhere.
// ──────────────────────────────────────────────────────────────────────────
export function FormField({
  label, helper, error, required, children, testID,
}: {
  label?: string;
  helper?: string;
  error?: string | null;
  required?: boolean;
  children: React.ReactNode;
  testID?: string;
}) {
  return (
    <View testID={testID} style={{ gap: 6 }}>
      {label ? (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Text style={type.label}>{label}</Text>
          {required ? <Text style={{ color: colors.error, fontSize: 12, fontWeight: "600" }}>*</Text> : null}
        </View>
      ) : null}
      {children}
      {error ? <Text style={[type.caption, { color: colors.error }]}>{error}</Text>
      : helper ? <Text style={type.caption}>{helper}</Text>
      : null}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// Toolbar — consistent sub-header row (used above lists, tables, grids).
// Layout: left cluster · flex spacer · right cluster.
// ──────────────────────────────────────────────────────────────────────────
export function Toolbar({
  left, right, style,
}: {
  left?: React.ReactNode;
  right?: React.ReactNode;
  style?: ViewStyle;
}) {
  return (
    <View style={[{
      flexDirection: "row",
      alignItems: "center",
      gap: spacing.md,
      paddingVertical: spacing.md,
    }, style]}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flex: 1, flexWrap: "wrap" }}>{left}</View>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>{right}</View>
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// SegmentedTabs — variant of Tabs that includes counts in a pill.
// (Kept in ui.tsx so screens can pick either underline or pill navigation.)
// ──────────────────────────────────────────────────────────────────────────
export function PillTabs<T extends string>({
  value, options, onChange, testID,
}: {
  value: T;
  options: { value: T; label: string; count?: number; icon?: FeatherName }[];
  onChange: (v: T) => void;
  testID?: string;
}) {
  return (
    <View testID={testID} style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={String(o.value)}
            testID={testID ? `${testID}-${o.value}` : undefined}
            onPress={() => onChange(o.value)}
            style={({ pressed }) => ({
              paddingHorizontal: spacing.md,
              height: 34,
              borderRadius: radius.pill,
              borderWidth: StyleSheet.hairlineWidth,
              borderColor: on ? colors.brand : colors.border,
              backgroundColor: on ? colors.brandTint : colors.surfaceSecondary,
              flexDirection: "row",
              alignItems: "center",
              gap: 6,
              opacity: pressed ? 0.85 : 1,
            })}
          >
            {o.icon ? <Feather name={o.icon} size={iconSize.sm} color={on ? colors.brand : colors.onSurfaceMuted} /> : null}
            <Text style={{
              fontSize: 13,
              fontFamily: type.titleMd.fontFamily,
              fontWeight: on ? "600" : "500",
              color: on ? colors.brand : colors.onSurface,
            }}>
              {o.label}
            </Text>
            {typeof o.count === "number" ? (
              <View style={{
                minWidth: 20,
                paddingHorizontal: 6,
                height: 18,
                borderRadius: radius.pill,
                backgroundColor: on ? colors.brand : colors.surfaceTertiary,
                alignItems: "center", justifyContent: "center",
              }}>
                <Text style={{
                  fontSize: 10,
                  fontFamily: type.titleMd.fontFamily,
                  fontWeight: "700",
                  color: on ? colors.onBrand : colors.onSurfaceMuted,
                }}>{o.count}</Text>
              </View>
            ) : null}
          </Pressable>
        );
      })}
    </View>
  );
}

// ──────────────────────────────────────────────────────────────────────────
// ProgressBar — thin, tone-coded progress line for order collection %.
// ──────────────────────────────────────────────────────────────────────────
export function ProgressBar({
  percent, tone = "brand", size = "sm",
}: {
  percent: number;
  tone?: "brand" | "success" | "warning" | "danger" | "neutral";
  size?: "xs" | "sm" | "md";
}) {
  const height = size === "xs" ? 3 : size === "sm" ? 4 : 8;
  const fill =
    tone === "success" ? colors.success
    : tone === "warning" ? colors.warning
    : tone === "danger" ? colors.error
    : tone === "neutral" ? colors.onSurfaceMuted
    : colors.brand;
  const pct = Math.max(0, Math.min(100, percent));
  return (
    <View style={{
      height,
      borderRadius: radius.pill,
      backgroundColor: colors.surfaceTertiary,
      overflow: "hidden",
    }}>
      <View style={{
        height: "100%",
        width: `${pct}%`,
        backgroundColor: fill,
        borderRadius: radius.pill,
      }} />
    </View>
  );
}
