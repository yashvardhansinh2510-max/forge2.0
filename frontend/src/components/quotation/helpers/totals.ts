/** Shared document-level totals contract used by both quotation builders. */
export type QuotationTotals = {
  subtotal: number;
  discount: number;
  transportation: number;
  grandTotal: number;
};

export type QuotationTotalLine = {
  qty: number;
  unitPrice: number;
  discountAmount?: number;
};

const money = (value: number): number => Math.round(value * 100) / 100;

export function computeQuotationTotals(
  lines: readonly QuotationTotalLine[],
  transportation = 0,
): QuotationTotals {
  let subtotal = 0;
  let discount = 0;
  for (const line of lines) {
    const gross = Number(line.qty || 0) * Number(line.unitPrice || 0);
    subtotal += gross;
    discount += Number(line.discountAmount || 0);
  }
  const roundedSubtotal = money(subtotal);
  const roundedDiscount = money(discount);
  const roundedTransportation = money(Number(transportation || 0));
  return {
    subtotal: roundedSubtotal,
    discount: roundedDiscount,
    transportation: roundedTransportation,
    grandTotal: money(roundedSubtotal - roundedDiscount + roundedTransportation),
  };
}
