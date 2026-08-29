export type AccessProfile =
  | "ground_tile_quotations_followups"
  | "ground_payments_dispatches"
  | "sanitary_quotations_followups"
  | "sanitary_purchases";

export const PROFILE_PROVISIONING: Record<AccessProfile, {
  label: string;
  description: string;
  floorId: string;
  minimumRole: "sales" | "accounts" | "purchase";
}> = {
  ground_tile_quotations_followups: {
    label: "Ground Floor · Tile Quotations & Follow-ups",
    description: "Tiles, quotations, follow-ups, and read-only customer delivery status.",
    floorId: "ground-floor",
    minimumRole: "sales",
  },
  ground_payments_dispatches: {
    label: "Ground Floor · Payments & Dispatches",
    description: "Ground Floor payments and tile dispatch workflow.",
    floorId: "ground-floor",
    minimumRole: "accounts",
  },
  sanitary_quotations_followups: {
    label: "Sanitary Bathroom · Quotations & Follow-ups",
    description: "Sanitary quotations and customer follow-ups.",
    floorId: "first-floor",
    minimumRole: "sales",
  },
  sanitary_purchases: {
    label: "Sanitary Bathroom · Purchases",
    description: "Sanitary purchase orders, suppliers, and purchase tracking.",
    floorId: "first-floor",
    minimumRole: "purchase",
  },
};

export const PROFILE_MODULES: Record<AccessProfile, Set<string>> = {
  ground_tile_quotations_followups: new Set(["tiles", "followups"]),
  ground_payments_dispatches: new Set(["payments", "orders"]),
  sanitary_quotations_followups: new Set(["quotations", "followups"]),
  sanitary_purchases: new Set(["purchases"]),
};

export function staffLandingPath(profile?: AccessProfile | null): string {
  switch (profile) {
    case "ground_tile_quotations_followups": return "/(admin)/tiles";
    case "ground_payments_dispatches": return "/(admin)/payments";
    case "sanitary_quotations_followups": return "/(admin)/quotations";
    case "sanitary_purchases": return "/(admin)/purchases";
    default: return "/(admin)/dashboard";
  }
}
