// Pricing helpers — pure, memoisable, testable.
import type { Line } from "./types";

export function effectivePct(l: Line, catDiscs: Record<string, number>, projPct: number): { pct: number; source: string } {
  if (l.discount_pct != null) return { pct: l.discount_pct, source: "product" };
  if (l.category_id && catDiscs[l.category_id] != null) return { pct: catDiscs[l.category_id], source: "category" };
  if (projPct) return { pct: projPct, source: "project" };
  return { pct: 0, source: "none" };
}

export function sourceBadge(source: string): { tone: "info" | "success" | "warning"; label: string } | null {
  if (source === "category") return { tone: "info", label: "Cat" };
  if (source === "project") return { tone: "success", label: "Proj" };
  return null;
}

export function computeLineTotal(l: Line, pct: number): number {
  return l.qty * l.unit_price * (1 - pct / 100);
}

export function computeTotals(
  lines: Line[],
  projectDiscount: number,
  categoryDiscounts: Record<string, number>,
): { subtotal: number; discount: number; grand: number } {
  let sub = 0, disc = 0;
  for (const l of lines) {
    const gross = l.qty * l.unit_price;
    const { pct } = effectivePct(l, categoryDiscounts, projectDiscount);
    const d = gross * pct / 100;
    sub += gross; disc += d;
  }
  return { subtotal: sub, discount: disc, grand: Math.round((sub - disc) * 100) / 100 };
}

// Approximate swatch colour from a finish label. Kept deliberately small — we
// fall back to a neutral chrome tone when we don't recognise the finish.
export function finishSwatch(finish?: string | null): string {
  const f = (finish || "").toLowerCase();
  if (!f) return "#c5c8cc";
  if (f.includes("matt black") || f.includes("matte black") || f.includes(" black")) return "#111214";
  if (f.includes("chrome")) return "#c5c8cc";
  if (f.includes("brushed") && f.includes("brass")) return "#a37f38";
  if (f.includes("brass") || f.includes("gold")) return "#d4a94b";
  if (f.includes("copper")) return "#b87333";
  if (f.includes("bronze")) return "#8a5a2b";
  if (f.includes("nickel")) return "#a5a5a8";
  if (f.includes("stone") || f.includes("grey") || f.includes("gray")) return "#8a8a8f";
  if (f.includes("taupe")) return "#7f6f5b";
  if (f.includes("white")) return "#f6f6f7";
  return "#c5c8cc";
}
