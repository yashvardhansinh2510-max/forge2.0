// BuildCon House · Design System V1 · Primitives
// Every screen composes UI from this file. No hardcoded colors, spacing, or
// typography allowed anywhere else. Feels closer to Linear / Stripe / Notion.

import { Feather } from "@expo/vector-icons";
import { useMemo, useRef } from "react";
import {
  ActivityIndicator,
  Animated,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from "react-native";

import {
  colors,
  elevation,
  layout,
  money,
  radius,
  spacing,
  statusMeta,
  type,
} from "@/src/theme/tokens";

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
  const m = statusMeta[status] || { label: status, bg: colors.surfaceTertiary, fg: colors.onSurfaceSecondary, border: colors.border };
  return (
    <View style={{
      backgroundColor: m.bg,
      paddingHorizontal: 9,
      paddingVertical: 4,
      borderRadius: radius.pill,
      alignSelf: "flex-start",
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: m.border || "transparent",
    }}>
      <Text style={{ color: m.fg, fontSize: 11, fontFamily: type.titleMd.fontFamily, fontWeight: "600" }}>
        {m.label}
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
        borderColor: active ? colors.brand : colors.border,
        backgroundColor: active ? colors.brand : colors.surfaceSecondary,
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "row",
        gap: 6,
        flexShrink: 0,
        opacity: pressed ? 0.85 : 1,
      })}
    >
      {icon ? <Feather name={icon} size={13} color={active ? colors.onBrand : colors.onSurfaceSecondary} /> : null}
      <Text style={{
        color: active ? colors.onBrand : colors.onSurface,
        fontSize: 13,
        fontFamily: type.bodyStrong.fontFamily,
        fontWeight: active ? "600" : "500",
      }}>
        {label}
      </Text>
      {typeof count === "number" ? (
        <View style={{
          backgroundColor: active ? "rgba(255,255,255,0.22)" : colors.surfaceTertiary,
          paddingHorizontal: 6,
          paddingVertical: 1,
          borderRadius: radius.pill,
          marginLeft: 2,
        }}>
          <Text style={{
            color: active ? colors.onBrand : colors.onSurfaceSecondary,
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
