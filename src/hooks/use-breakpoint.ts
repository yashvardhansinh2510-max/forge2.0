// Breakpoint hook — the single source of truth for responsive decisions.
// Never scatter `width >= 900` checks across screens; call `useBreakpoint()`.
// Boundaries come from design tokens so every screen flips phone/tablet at
// the same width as `useBp()` and `AdminPage`.
import { useWindowDimensions } from "react-native";

import { layout } from "@/src/design/tokens";

export type Breakpoint = "phone" | "tabletPortrait" | "tabletLandscape" | "desktop";

export function useBreakpoint() {
  const { width, height } = useWindowDimensions();
  let bp: Breakpoint;
  if (width >= 1280) bp = "desktop";
  else if (width >= layout.bp.desktop) bp = "tabletLandscape";
  else if (width >= layout.bp.tablet) bp = "tabletPortrait";
  else bp = "phone";

  const isPhone = bp === "phone";
  const isTablet = bp === "tabletPortrait" || bp === "tabletLandscape";
  const isDesktop = bp === "desktop";
  // "wide" = tablet-landscape or larger — trigger two-column layouts here.
  const isWide = bp === "tabletLandscape" || bp === "desktop";
  const isLandscape = width > height;
  const isCompact = bp === "phone";

  // Card columns for a product grid — tuned for supplier bathware imagery.
  const productCols =
    bp === "desktop"        ? 5 :
    bp === "tabletLandscape"? 4 :
    bp === "tabletPortrait" ? 3 :
    2;

  // Horizontal page padding — same rhythm as AdminPage/useBp gutters.
  const pad = isPhone ? layout.gutter.phone : isTablet ? layout.gutter.tablet : layout.gutter.desktop;

  return { bp, width, height, isPhone, isTablet, isDesktop, isWide, isLandscape, isCompact, productCols, pad };
}
