// Forge design tokens. Mirrors /app/design_guidelines.json — monochromatic
// Carbon/Graphite so the UI feels timeless and enterprise-native, not AI-generic.
import { Platform } from "react-native";

export const colors = {
  surface: "#FAFAFA",
  surfaceSecondary: "#FFFFFF",
  surfaceTertiary: "#F4F4F5",
  surfaceInverse: "#18181B",
  onSurface: "#111111",
  onSurfaceMuted: "#71717A",
  onSurfaceSecondary: "#3F3F46",
  onSurfaceInverse: "#FAFAFA",
  brand: "#18181B",
  brandSecondary: "#3F3F46",
  brandTertiary: "#E4E4E7",
  onBrand: "#FFFFFF",
  success: "#166534",
  successBg: "#DCFCE7",
  warning: "#854D0E",
  warningBg: "#FEF9C3",
  error: "#991B1B",
  errorBg: "#FEE2E2",
  info: "#1E40AF",
  infoBg: "#DBEAFE",
  border: "#E4E4E7",
  borderStrong: "#D4D4D8",
  divider: "#F4F4F5",
  overlay: "rgba(9,9,11,0.45)",
} as const;

export const spacing = {
  xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48,
} as const;

export const radius = { sm: 6, md: 12, lg: 20, pill: 999 } as const;

export const shadow = {
  soft: {
    shadowColor: "#000",
    shadowOpacity: 0.05,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  strong: {
    shadowColor: "#000",
    shadowOpacity: 0.1,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 12 },
    elevation: 8,
  },
} as const;

const systemSans = Platform.select({ ios: "System", android: "sans-serif", default: "System" });
const systemMono = Platform.select({ ios: "Menlo", android: "monospace", default: "Menlo" });

export const font = {
  sans: systemSans as string,
  mono: systemMono as string,
} as const;

export const type = {
  displayLg: { fontFamily: font.sans, fontSize: 34, fontWeight: "700" as const, letterSpacing: -0.5, color: colors.onSurface },
  displayMd: { fontFamily: font.sans, fontSize: 24, fontWeight: "700" as const, letterSpacing: -0.3, color: colors.onSurface },
  titleLg: { fontFamily: font.sans, fontSize: 20, fontWeight: "600" as const, color: colors.onSurface },
  titleMd: { fontFamily: font.sans, fontSize: 17, fontWeight: "600" as const, color: colors.onSurface },
  bodyLg: { fontFamily: font.sans, fontSize: 16, color: colors.onSurface },
  body: { fontFamily: font.sans, fontSize: 14, color: colors.onSurface },
  bodyMuted: { fontFamily: font.sans, fontSize: 14, color: colors.onSurfaceMuted },
  caption: { fontFamily: font.sans, fontSize: 12, color: colors.onSurfaceMuted },
  overline: { fontFamily: font.sans, fontSize: 10, fontWeight: "600" as const, color: colors.onSurfaceMuted, letterSpacing: 1.4, textTransform: "uppercase" as const },
  mono: { fontFamily: font.mono, fontSize: 13, color: colors.onSurface, fontVariant: ["tabular-nums" as const] },
  monoLg: { fontFamily: font.mono, fontSize: 18, color: colors.onSurface, fontWeight: "600" as const, fontVariant: ["tabular-nums" as const] },
};

export const money = (v: number, currency = "₹") =>
  `${currency} ${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}`;

export const roleLabels: Record<string, string> = {
  owner: "Owner", admin: "Admin", manager: "Manager", sales: "Sales",
  purchase: "Purchase", warehouse: "Warehouse", accounts: "Accounts", worker: "Worker",
};

export const statusMeta: Record<string, { label: string; bg: string; fg: string }> = {
  draft: { label: "Draft", bg: "#F4F4F5", fg: "#3F3F46" },
  pending_approval: { label: "Pending Approval", bg: "#FEF9C3", fg: "#854D0E" },
  approved: { label: "Approved", bg: "#DCFCE7", fg: "#166534" },
  rejected: { label: "Rejected", bg: "#FEE2E2", fg: "#991B1B" },
  sent: { label: "Sent", bg: "#DBEAFE", fg: "#1E40AF" },
  won: { label: "Won", bg: "#DCFCE7", fg: "#166534" },
  lost: { label: "Lost", bg: "#FEE2E2", fg: "#991B1B" },
  expired: { label: "Expired", bg: "#F4F4F5", fg: "#71717A" },
};
