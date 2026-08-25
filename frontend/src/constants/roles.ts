export const MANAGER_ROLES = ["owner", "admin", "manager"] as const;

export function canManageDestructiveData(role?: string | null): boolean {
  return !!role && (MANAGER_ROLES as readonly string[]).includes(role);
}
