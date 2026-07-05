// Breakpoint hook — the single source of truth for responsive decisions.
// Never scatter `width >= 900` checks across screens; call `useBreakpoint()`.
import { useWindowDimensions } from "react-native";

export type Breakpoint = "phone" | "tabletPortrait" | "tabletLandscape" | "desktop";

export function useBreakpoint() {
  const { width, height } = useWindowDimensions();
  let bp: Breakpoint;
  if (width >= 1280) bp = "desktop";
  else if (width >= 900) bp = "tabletLandscape";
  else if (width >= 700) bp = "tabletPortrait";
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

  // Horizontal page padding.
  const pad = isPhone ? 16 : isTablet ? 24 : 32;

  return { bp, width, height, isPhone, isTablet, isDesktop, isWide, isLandscape, isCompact, productCols, pad };
}
