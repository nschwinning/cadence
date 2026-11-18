import type { ReactNode } from 'react';
import { InMemoryWebStorage, WebStorageStateStore, type User } from 'oidc-client-ts';
import { AuthProvider } from 'react-oidc-context';
import { authEnabled, oidcAuthority, oidcClientId } from './config';
import { AuthGate } from './AuthGate';

/** After the login redirect: drop the code from the URL and return to the saved page. */
function onSigninCallback(user: User | undefined): void {
  const state = user?.state as { returnTo?: string } | undefined;
  const returnTo = state?.returnTo?.startsWith('/') ? state.returnTo : '/';
  window.history.replaceState({}, document.title, returnTo);
}

/**
 * Login for the whole app (OIDC authorization code + PKCE against the Keycloak realm).
 * Tokens stay in memory and renew silently; a reload re-authenticates through the
 * Keycloak session. A no-op wrapper while login is disabled.
 */
export function CadenceAuthProvider({ children }: { children: ReactNode }) {
  if (!authEnabled) return <>{children}</>;
  return (
    <AuthProvider
      authority={oidcAuthority}
      client_id={oidcClientId}
      redirect_uri={`${window.location.origin}/`}
      post_logout_redirect_uri={`${window.location.origin}/`}
      scope="openid profile"
      automaticSilentRenew
      userStore={new WebStorageStateStore({ store: new InMemoryWebStorage() })}
      onSigninCallback={onSigninCallback}
    >
      <AuthGate>{children}</AuthGate>
    </AuthProvider>
  );
}
