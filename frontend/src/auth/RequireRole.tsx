import type { ReactNode } from 'react';
import type { Role } from './roles';
import { useHasRole } from './useRoles';

/**
 * Render `children` only for users holding `role`; otherwise `fallback` (nothing by
 * default). The backend enforces every role as well — this only hides controls a user
 * could not use.
 */
export function RequireRole({
  role,
  children,
  fallback = null,
}: {
  role: Role;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  return <>{useHasRole(role) ? children : fallback}</>;
}
