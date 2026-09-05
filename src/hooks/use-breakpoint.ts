// Breakpoint hook — the single source of truth for responsive decisions.
// Never scatter `width >= 900` checks across screens; call `useBreakpoint()`.
// Boundaries come from design tokens so every screen flips phone/tablet at
// the same width as `useBp()` and `AdminPage`.
import { useBp } from "@/src/design/responsive";

export type Breakpoint = "phone" | "tabletPortrait" | "tabletLandscape" | "desktop";

export function useBreakpoint() {
  const canonical = useBp();
  const { width, height } = canonical;
  const bp: Breakpoint = canonical.bp;

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
  const pad = canonical.gutter;

  return { bp, width, height, isPhone, isTablet, isDesktop, isWide, isLandscape, isCompact, productCols, pad };
}
