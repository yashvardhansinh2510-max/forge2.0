// Responsive helpers for the Quotation Builder product grid.
// The picker is deliberately a two-column, shop-style catalog on every
// supported phone and tablet width.  This keeps four choices visible in the
// first product viewport instead of dedicating the whole surface to one item.
export function quotationGridColumns(width: number): 1 | 2 {
  // 280px is below the narrowest supported mobile content area, but retaining
  // a single-column fallback means the layout is still usable in an embedded
  // or exceptionally narrow web view.
  if (width >= 280) return 2;
  return 1;
}
