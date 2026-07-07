// Responsive helpers for the Quotation Builder product grid.
// Keeps the visual contract explicit: desktop 3 columns, tablet 2, phone 1.
export function quotationGridColumns(width: number): number {
  if (width >= 1040) return 3;
  if (width >= 640) return 2;
  return 1;
}
