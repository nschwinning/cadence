import { useEffect, type ReactNode } from 'react';
import { useAuth } from 'react-oidc-context';
import { setSessionHandlers } from './session';

/** Where to return after login. */
interface LoginState {
  returnTo?: string;
}

function currentPath(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

/**
 * Require a login before rendering the app: start the Keycloak login when there is no
 * session, keep the API client supplied with the current access token, and log in again
 * when the API answers 401.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const auth = useAuth();

  useEffect(() => {
    setSessionHandlers({
      getToken: () => auth.user?.access_token,
      onUnauthorized: () => {
        void auth.signinRedirect({ state: { returnTo: currentPath() } satisfies LoginState });
      },
    });
  }, [auth]);

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated && !auth.activeNavigator && !auth.error) {
      void auth.signinRedirect({ state: { returnTo: currentPath() } satisfies LoginState });
    }
  }, [auth]);

  if (auth.error) {
    return (
      <div role="alert" className="m-8 rounded border border-red-300 bg-red-50 p-4 text-red-800">
        <p className="font-semibold">Sign-in failed</p>
        <p className="mt-1 text-sm">{auth.error.message}</p>
        <button
          type="button"
          onClick={() => void auth.signinRedirect({ state: { returnTo: '/' } })}
          className="mt-3 rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
        >
          Try again
        </button>
      </div>
    );
  }
  if (!auth.isAuthenticated) {
    return (
      <p role="status" aria-live="polite" className="m-8 text-slate-500">
        Signing in…
      </p>
    );
  }
  return <>{children}</>;
}
