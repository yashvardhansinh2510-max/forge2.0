// Responsive helpers for the Quotation Builder product grid.
// The explorer uses two cards at most so the normalized product frame remains
// large enough to inspect. On a phone, two columns give workers the familiar
// shop-style scan (four products in the first viewport) instead of making
// them scroll one large product card at a time.
export function quotationGridColumns(width: number): 1 | 2 {
  if (width >= 320) return 2;
  return 1;
}
