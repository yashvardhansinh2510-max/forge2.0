// BuildCon House · Design System V1 tokens.
// Blue-forward primary + premium neutral graphite/porcelain foundation.
// Inspired by Linear, Stripe, Notion, Arc — never a Tailwind template.
// Everything downstream (primitives, screens) references these tokens; no hardcoded hex.

import { Platform } from "react-native";

// ─────────────────────────────────────────────────────────────────────────────
// Palette (raw)
// ─────────────────────────────────────────────────────────────────────────────
const palette = {
  // Blues — refined premium accent (between Stripe & Linear)
  blue50:  "#EFF6FF",
  blue100: "#DBEAFE",
  blue200: "#BFDBFE",
  blue500: "#3B82F6",
  blue600: "#2563EB",   // primary
  blue700: "#1D4ED8",   // primary pressed
  blue900: "#1E3A8A",

  // Porcelain neutrals — off-white surfaces, cooler than pure gray
  gray0:   "#FFFFFF",
  gray25:  "#FCFCFD",
  gray50:  "#F7F8FA",
  gray75:  "#F1F3F6",
  gray100: "#EAECEF",
  gray150: "#DFE3E8",
  gray200: "#C6CCD3",
  gray400: "#8A95A3",
  gray500: "#6B7280",
  gray600: "#4B5563",
  gray700: "#374151",
  gray800: "#1F2937",
  gray900: "#0F172A",

  // Semantic families
  green50:  "#ECFDF5",
  green100: "#D1FAE5",
  green600: "#16A34A",
  green700: "#15803D",

  amber50:  "#FFFBEB",
  amber100: "#FEF3C7",
  amber600: "#D97706",
  amber700: "#B45309",

  red50:  "#FEF2F2",
  red100: "#FEE2E2",
  red600: "#DC2626",
  red700: "#B91C1C",

  sky50:  "#F0F9FF",
  sky100: "#E0F2FE",
  sky600: "#0284C7",
  sky700: "#0369A1",
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Semantic color roles — the ONLY thing screens should reference.
// ─────────────────────────────────────────────────────────────────────────────
export const colors = {
  // Surfaces (page → card → nested)
  surface: palette.gray50,             // primary app background
  surfaceSecondary: palette.gray0,     // cards, sheets, elevated
  surfaceTertiary: palette.gray75,     // subtle chips, hover fill
  surfaceInverse: palette.gray900,     // dark heroes, inverse chips
  surfaceRaised: palette.gray0,        // synonym for elevated card
  surfaceSubtle: palette.gray25,       // barely-there surface (e.g. table rows)

  // Text
  onSurface: palette.gray900,          // primary text
  onSurfaceSecondary: palette.gray700, // secondary text
  onSurfaceMuted: palette.gray500,     // captions, hints
  onSurfaceSubtle: palette.gray400,    // placeholders, disabled
  onSurfaceInverse: palette.gray0,     // text on dark

  // Brand (blue) — primary accent
  brand: palette.blue600,
  brandHover: palette.blue700,
  brandTint: palette.blue50,           // faint blue background wash
  brandTintStrong: palette.blue100,
  brandBorder: palette.blue200,
  onBrand: palette.gray0,
  brandSecondary: palette.gray900,     // neutral dark for "secondary CTA"

  // Borders & dividers
  border: palette.gray100,             // default hairline
  borderStrong: palette.gray150,       // hovered/emphasized
  borderMuted: "rgba(15, 23, 42, 0.06)",
  divider: palette.gray100,

  // Focus & selection
  focusRing: "rgba(37, 99, 235, 0.35)",
  selection: palette.blue100,

  // Overlays & scrims
  overlay: "rgba(15, 23, 42, 0.48)",
  overlaySoft: "rgba(15, 23, 42, 0.18)",

  // Semantic — foreground and matching background wash
  success: palette.green700,
  successFg: palette.green700,
  successBg: palette.green50,
  successBorder: palette.green100,

  warning: palette.amber700,
  warningFg: palette.amber700,
  warningBg: palette.amber50,
  warningBorder: palette.amber100,

  error: palette.red700,
  errorFg: palette.red700,
  errorBg: palette.red50,
  errorBorder: palette.red100,

  info: palette.sky700,
  infoFg: palette.sky700,
  infoBg: palette.sky50,
  infoBorder: palette.sky100,

  // Aliases (backwards compat — some screens still reference these names)
  brandTertiary: palette.gray100,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Spacing — strict 8pt grid with a 4pt exception for tight inline gaps.
// ─────────────────────────────────────────────────────────────────────────────
export const spacing = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
  huge: 64,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Radii — geometric, product-consistent.
// ─────────────────────────────────────────────────────────────────────────────
export const radius = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  pill: 999,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Elevation — subtle, layered. Never garish drop-shadows.
// ─────────────────────────────────────────────────────────────────────────────
export const elevation = {
  none: {
    shadowColor: "transparent",
    shadowOpacity: 0,
    shadowRadius: 0,
    shadowOffset: { width: 0, height: 0 },
    elevation: 0,
  },
  // Barely-there border-alternative for flat cards on light backgrounds
  hairline: {
    shadowColor: "#0B1220",
    shadowOpacity: 0.04,
    shadowRadius: 2,
    shadowOffset: { width: 0, height: 1 },
    elevation: 1,
  },
  // Standard resting card
  low: {
    shadowColor: "#0B1220",
    shadowOpacity: 0.06,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  // Sticky toolbars, floating pills
  medium: {
    shadowColor: "#0B1220",
    shadowOpacity: 0.08,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 4,
  },
  // Sheets, modals
  high: {
    shadowColor: "#0B1220",
    shadowOpacity: 0.12,
    shadowRadius: 28,
    shadowOffset: { width: 0, height: 14 },
    elevation: 8,
  },
  // Popovers, menus lifted above sheets
  overlay: {
    shadowColor: "#0B1220",
    shadowOpacity: 0.16,
    shadowRadius: 36,
    shadowOffset: { width: 0, height: 20 },
    elevation: 12,
  },
} as const;

// Legacy alias — some existing screens reference `shadow.soft` etc.
export const shadow = {
  hair: elevation.hairline,
  soft: elevation.low,
  lifted: elevation.medium,
  strong: elevation.high,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Motion — restrained, deliberate. Never bouncy for enterprise feel.
// ─────────────────────────────────────────────────────────────────────────────
export const motion = {
  instant: { duration: 80 },
  fast:    { duration: 140 },
  base:    { duration: 220 },
  slow:    { duration: 320 },
  spring:  { damping: 22, stiffness: 260, mass: 0.9 },
  springSoft: { damping: 18, stiffness: 160, mass: 0.9 },
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Font families — Inter loaded via expo-font (weight-specific families).
// Fallback to system when custom files fail to load.
// ─────────────────────────────────────────────────────────────────────────────
const systemSans = Platform.select({ ios: "System", android: "sans-serif", default: "System" });
const systemMono = Platform.select({ ios: "Menlo", android: "monospace", default: "Menlo" });

export const font = {
  regular:  "Inter-Regular",
  medium:   "Inter-Medium",
  semibold: "Inter-SemiBold",
  bold:     "Inter-Bold",
  sans:     "Inter-Regular", // default alias
  mono:     systemMono as string,
  systemSans: systemSans as string,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Typography scale — hierarchy through weight & size, not decoration.
// Every style pre-composes fontFamily so screens never re-declare it.
// ─────────────────────────────────────────────────────────────────────────────
export const type = {
  // Display — hero moments, splash, empty-state headlines
  displayXl: { fontFamily: font.bold, fontSize: 40, lineHeight: 48, letterSpacing: -0.8, color: colors.onSurface, fontWeight: "700" as const },
  displayLg: { fontFamily: font.bold, fontSize: 32, lineHeight: 40, letterSpacing: -0.6, color: colors.onSurface, fontWeight: "700" as const },
  displayMd: { fontFamily: font.bold, fontSize: 24, lineHeight: 32, letterSpacing: -0.4, color: colors.onSurface, fontWeight: "700" as const },

  // Titles — page headings, card headers
  titleLg: { fontFamily: font.semibold, fontSize: 20, lineHeight: 28, letterSpacing: -0.2, color: colors.onSurface, fontWeight: "600" as const },
  titleMd: { fontFamily: font.semibold, fontSize: 17, lineHeight: 24, letterSpacing: -0.1, color: colors.onSurface, fontWeight: "600" as const },
  titleSm: { fontFamily: font.semibold, fontSize: 15, lineHeight: 22, color: colors.onSurface, fontWeight: "600" as const },

  // Body
  bodyLg: { fontFamily: font.regular, fontSize: 16, lineHeight: 24, color: colors.onSurface, fontWeight: "400" as const },
  body:   { fontFamily: font.regular, fontSize: 14, lineHeight: 20, color: colors.onSurface, fontWeight: "400" as const },
  bodyStrong: { fontFamily: font.medium, fontSize: 14, lineHeight: 20, color: colors.onSurface, fontWeight: "500" as const },
  bodyMuted: { fontFamily: font.regular, fontSize: 14, lineHeight: 20, color: colors.onSurfaceMuted, fontWeight: "400" as const },
  bodySm: { fontFamily: font.regular, fontSize: 13, lineHeight: 18, color: colors.onSurface, fontWeight: "400" as const },

  // Meta
  caption: { fontFamily: font.regular, fontSize: 12, lineHeight: 16, color: colors.onSurfaceMuted, fontWeight: "400" as const },
  captionStrong: { fontFamily: font.medium, fontSize: 12, lineHeight: 16, color: colors.onSurfaceSecondary, fontWeight: "500" as const },
  overline: { fontFamily: font.semibold, fontSize: 10, lineHeight: 14, color: colors.onSurfaceMuted, letterSpacing: 1.2, textTransform: "uppercase" as const, fontWeight: "600" as const },
  label: { fontFamily: font.medium, fontSize: 12, lineHeight: 16, color: colors.onSurfaceSecondary, fontWeight: "500" as const },

  // Numeric (tabular)
  mono:    { fontFamily: font.mono, fontSize: 13, lineHeight: 18, color: colors.onSurface, fontVariant: ["tabular-nums" as const] },
  monoLg:  { fontFamily: font.mono, fontSize: 18, lineHeight: 24, color: colors.onSurface, fontWeight: "600" as const, fontVariant: ["tabular-nums" as const] },
  numeric: { fontFamily: font.semibold, fontSize: 16, lineHeight: 22, color: colors.onSurface, fontWeight: "600" as const, fontVariant: ["tabular-nums" as const] },
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Layout tokens
// ─────────────────────────────────────────────────────────────────────────────
export const layout = {
  hitSlop: { top: 8, bottom: 8, left: 8, right: 8 },
  tapTarget: 44,
  screenPadding: { phone: spacing.lg, tablet: spacing.xl },
  maxContentWidth: 1280,
  tabBarHeight: 60,
  headerHeight: 56,
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
export const money = (v: number, currency = "₹") =>
  `${currency}${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;

export const moneyShort = (v: number, currency = "₹") => {
  const n = Number(v || 0);
  if (Math.abs(n) >= 10000000) return `${currency}${(n / 10000000).toFixed(2)} Cr`;
  if (Math.abs(n) >= 100000) return `${currency}${(n / 100000).toFixed(2)} L`;
  if (Math.abs(n) >= 1000) return `${currency}${(n / 1000).toFixed(1)}K`;
  return `${currency}${n.toLocaleString("en-IN")}`;
};

export const roleLabels: Record<string, string> = {
  owner: "Owner", admin: "Admin", manager: "Manager", sales: "Sales",
  purchase: "Purchase", warehouse: "Warehouse", accounts: "Accounts", worker: "Worker",
};

// Status meta — used across quotations, orders, payments.
export const statusMeta: Record<string, { label: string; bg: string; fg: string; border?: string }> = {
  draft:            { label: "Draft",           bg: palette.gray75,   fg: palette.gray700,  border: palette.gray100 },
  pending_approval: { label: "Pending Approval", bg: palette.amber50,  fg: palette.amber700, border: palette.amber100 },
  approved:         { label: "Approved",        bg: palette.green50,  fg: palette.green700, border: palette.green100 },
  rejected:         { label: "Rejected",        bg: palette.red50,    fg: palette.red700,   border: palette.red100 },
  sent:             { label: "Sent",            bg: palette.blue50,   fg: palette.blue700,  border: palette.blue100 },
  won:              { label: "Won",             bg: palette.green50,  fg: palette.green700, border: palette.green100 },
  lost:             { label: "Lost",            bg: palette.red50,    fg: palette.red700,   border: palette.red100 },
  expired:          { label: "Expired",         bg: palette.gray75,   fg: palette.gray500,  border: palette.gray100 },
  ordered:          { label: "Confirmed",       bg: palette.blue50,   fg: palette.blue700,  border: palette.blue100 },
  in_transit:       { label: "In Transit",      bg: palette.sky50,    fg: palette.sky700,   border: palette.sky100 },
  delivered:        { label: "Delivered",       bg: palette.green50,  fg: palette.green700, border: palette.green100 },
  paid:             { label: "Paid",            bg: palette.green50,  fg: palette.green700, border: palette.green100 },
  partial:          { label: "Partial",         bg: palette.amber50,  fg: palette.amber700, border: palette.amber100 },
  due:              { label: "Due",             bg: palette.red50,    fg: palette.red700,   border: palette.red100 },
  overdue:          { label: "Overdue",         bg: palette.red50,    fg: palette.red700,   border: palette.red100 },
};

// Brand identity
export const brand = {
  name: "BuildCon House",
  short: "BuildCon",
  tagline: "Let you live better",
  monogram: "BC",
} as const;

// Backwards-compat: some files still import `palette` internals; expose read-only.
export const _palette = palette;
