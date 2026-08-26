export type AccessProfile =
  | "ground_tile_quotations_followups"
  | "ground_payments_dispatches"
  | "sanitary_quotations_followups"
  | "sanitary_purchases";

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
