// Responsive — the single breakpoint authority for the design system.
import { useWindowDimensions } from "react-native";

import { layout } from "./tokens";

/** The only supported viewport tiers for application layout. */
export type Bp = "phone" | "tabletPortrait" | "tabletLandscape" | "desktop";

export function useBp() {
  const { width, height } = useWindowDimensions();
  const bp: Bp =
    width >= layout.bp.desktop ? "desktop" :
    width >= layout.bp.tabletLandscape ? "tabletLandscape" :
    width >= layout.bp.tabletPortrait ? "tabletPortrait" : "phone";

  const isPhone = bp === "phone";
  const isTablet = bp === "tabletPortrait" || bp === "tabletLandscape";
  const isDesktop = bp === "desktop";
  const isTabletPortrait = bp === "tabletPortrait";
  const isTabletLandscape = bp === "tabletLandscape";

  const gutter = isPhone ? layout.gutter.phone : isTablet ? layout.gutter.tablet : layout.gutter.desktop;

  return { bp, width, height, isPhone, isTablet, isDesktop, isTabletPortrait, isTabletLandscape, gutter };
}
