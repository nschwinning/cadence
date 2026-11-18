import { describe, it, expect } from 'vitest';
import { decodeJwtPayload, expandRoles, rolesFromAccessToken } from './roles';

/** An unsigned JWT with the given payload (only the payload is read client-side). */
function jwt(payload: Record<string, unknown>): string {
  const b64 = btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `header.${b64}.signature`;
}

describe('roles', () => {
  it('expands the hierarchy viewer ⊂ trader ⊂ admin', () => {
    expect([...expandRoles(['viewer'])].sort()).toEqual(['viewer']);
    expect([...expandRoles(['trader'])].sort()).toEqual(['trader', 'viewer']);
    expect([...expandRoles(['admin'])].sort()).toEqual(['admin', 'trader', 'viewer']);
  });

  it('ignores unknown roles and malformed input', () => {
    expect(expandRoles(['offline_access', 'uma_authorization']).size).toBe(0);
    expect(expandRoles(undefined).size).toBe(0);
    expect(expandRoles('admin').size).toBe(0);
  });

  it('reads realm roles from an access token', () => {
    const token = jwt({ realm_access: { roles: ['trader', 'default-roles-cadence'] } });
    expect([...rolesFromAccessToken(token)].sort()).toEqual(['trader', 'viewer']);
  });

  it('tolerates a missing or broken token', () => {
    expect(rolesFromAccessToken(undefined).size).toBe(0);
    expect(decodeJwtPayload('not-a-jwt')).toEqual({});
    expect(decodeJwtPayload('a.%%%.c')).toEqual({});
  });
});
