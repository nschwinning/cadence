import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Modal } from './Modal';

describe('Modal', () => {
  it('renders nothing when closed', () => {
    render(
      <Modal open={false} onClose={() => {}} title="Build">
        <p>Body content</p>
      </Modal>,
    );
    expect(screen.queryByText('Body content')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders children and exposes an accessible dialog when open', () => {
    render(
      <Modal open onClose={() => {}} title="Build an AI portfolio">
        <p>Body content</p>
      </Modal>,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleName('Build an AI portfolio');
    expect(screen.getByText('Body content')).toBeInTheDocument();
  });

  it('calls onClose when the close control is activated', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <Modal open onClose={onClose} title="Build">
        <p>Body content</p>
      </Modal>,
    );
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose on a backdrop click but not on a panel click', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <Modal open onClose={onClose} title="Build">
        <p>Body content</p>
      </Modal>,
    );
    // Clicking the body (inside the panel) must not close.
    await user.click(screen.getByText('Body content'));
    expect(onClose).not.toHaveBeenCalled();

    // Clicking the backdrop (the dialog's parent) closes.
    const backdrop = screen.getByRole('dialog').parentElement as HTMLElement;
    await user.click(backdrop);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onClose on Escape', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <Modal open onClose={onClose} title="Build">
        <p>Body content</p>
      </Modal>,
    );
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
