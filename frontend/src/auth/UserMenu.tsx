import { useAuth } from 'react-oidc-context';
import { authEnabled } from './config';

function SignedInUser() {
  const auth = useAuth();
  const profile = auth.user?.profile;
  const name = profile?.preferred_username || profile?.name || profile?.email || 'Signed in';
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="hidden text-slate-200 sm:inline" data-testid="signed-in-user">
        {name}
      </span>
      <button
        type="button"
        onClick={() => void auth.signoutRedirect()}
        className="rounded px-2 py-1 text-slate-200 ring-1 ring-white/30 hover:bg-white/10"
      >
        Log out
      </button>
    </div>
  );
}

/** The signed-in user's name and a Log out action (nothing while login is disabled). */
export function UserMenu() {
  return authEnabled ? <SignedInUser /> : null;
}
