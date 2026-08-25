// Responsive — the single breakpoint authority for the design system.
import { useWindowDimensions } from "react-native";

import { layout } from "./tokens";

export type Bp = "phone" | "tablet" | "desktop" | "wide";

export function useBp() {
  const { width, height } = useWindowDimensions();
  const bp: Bp =
    width >= layout.bp.wide ? "wide" :
    width >= layout.bp.desktop ? "desktop" :
    width >= layout.bp.tablet ? "tablet" : "phone";

  const isPhone = bp === "phone";
  const isTablet = bp === "tablet";
  const isDesktop = bp === "desktop" || bp === "wide";

  const gutter = isPhone ? layout.gutter.phone : isTablet ? layout.gutter.tablet : layout.gutter.desktop;

  return { bp, width, height, isPhone, isTablet, isDesktop, gutter };
}
