import { useHasRole } from '../auth/useRoles';

/**
 * Admin-only switch between the admin's own objects and every user's ("All users").
 * Renders nothing for non-admins, whose lists always show their own data.
 */
export function AllUsersToggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  const isAdmin = useHasRole('admin');
  if (!isAdmin) return null;
  return (
    <label className="flex items-center gap-2 text-sm text-slate-600">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-4 w-4 rounded border-slate-300"
      />
      All users
    </label>
  );
}

/** An owner's display name ("legacy owner" until the legacy account is linked). */
export function ownerLabel(owner: string | null | undefined): string {
  return owner || 'legacy owner';
}
