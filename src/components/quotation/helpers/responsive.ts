// Responsive helpers for the Quotation Builder product grid.
// The explorer uses two cards at most so the normalized product frame remains
// large enough to inspect. The caller must pass its measured pane width.
export function quotationGridColumns(width: number): 1 | 2 {
  if (width >= 768) return 2;
  return 1;
}
