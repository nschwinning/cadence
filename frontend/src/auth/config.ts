/**
 * Login configuration (Keycloak realm `cadence`, OIDC authorization code + PKCE).
 *
 * Login is on only when `VITE_AUTH_ENABLED` is `"true"` (set by compose). Without it —
 * tests and local development — the app behaves as before and every role is granted.
 */
export const authEnabled = import.meta.env.VITE_AUTH_ENABLED === 'true';

export const oidcAuthority =
  import.meta.env.VITE_OIDC_AUTHORITY || `${window.location.origin}/auth/realms/cadence`;

export const oidcClientId = import.meta.env.VITE_OIDC_CLIENT_ID || 'cadence-web';
