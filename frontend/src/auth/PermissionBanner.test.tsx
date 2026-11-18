import { describe, it, expect } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PermissionBanner } from './PermissionBanner';
import { reportForbidden } from './session';

describe('PermissionBanner', () => {
  it('shows the permission message on a 403 and can be dismissed', async () => {
    render(<PermissionBanner />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    act(() => reportForbidden());
    expect(screen.getByRole('alert')).toHaveTextContent(
      "You don't have permission for this action",
    );

    await userEvent.setup().click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
