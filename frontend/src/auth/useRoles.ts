import { useAuth } from 'react-oidc-context';
import { authEnabled } from './config';
import { ALL_ROLES, rolesFromAccessToken, type Role } from './roles';

function useTokenRoles(): ReadonlySet<Role> {
  const auth = useAuth();
  return rolesFromAccessToken(auth.user?.access_token);
}

/** The signed-in user's effective roles (every role while login is disabled). */
export const useRoles: () => ReadonlySet<Role> = authEnabled ? useTokenRoles : () => ALL_ROLES;

/** Whether the signed-in user holds `role` (directly or through the hierarchy). */
export function useHasRole(role: Role): boolean {
  return useRoles().has(role);
}
