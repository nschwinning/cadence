/** Cadence roles: `viewer` ⊂ `trader` ⊂ `admin` (mirrors the realm's composite roles). */
export type Role = 'viewer' | 'trader' | 'admin';

const IMPLIED: Record<Role, Role[]> = {
  viewer: ['viewer'],
  trader: ['trader', 'viewer'],
  admin: ['admin', 'trader', 'viewer'],
};

export const ALL_ROLES: ReadonlySet<Role> = new Set<Role>(['viewer', 'trader', 'admin']);

/** The effective roles for a token's realm roles (unknown roles ignored). */
export function expandRoles(raw: unknown): Set<Role> {
  const effective = new Set<Role>();
  if (!Array.isArray(raw)) return effective;
  for (const role of raw as unknown[]) {
    if (role === 'viewer' || role === 'trader' || role === 'admin') {
      for (const implied of IMPLIED[role as Role]) effective.add(implied);
    }
  }
  return effective;
}

/** Decode a JWT's payload (no verification — the backend verifies every token). */
export function decodeJwtPayload(token: string | undefined): Record<string, unknown> {
  if (!token) return {};
  const part = token.split('.')[1];
  if (!part) return {};
  try {
    const base64 = part.replace(/-/g, '+').replace(/_/g, '/');
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
    return JSON.parse(atob(padded)) as Record<string, unknown>;
  } catch {
    return {};
  }
}

/** The effective roles carried by an access token's `realm_access.roles`. */
export function rolesFromAccessToken(token: string | undefined): Set<Role> {
  const access = decodeJwtPayload(token).realm_access as { roles?: unknown } | undefined;
  return expandRoles(access?.roles);
}
