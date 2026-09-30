import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Pagination } from './Pagination';

describe('Pagination', () => {
  it('shows the current window and page position', () => {
    render(
      <Pagination
        page={0}
        pageSize={10}
        total={25}
        onPageChange={() => {}}
        label="trades"
      />,
    );

    expect(screen.getByText('Showing 1–10 of 25 trades')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
  });

  it('disables Previous on the first page and enables Next', () => {
    render(<Pagination page={0} pageSize={10} total={25} onPageChange={() => {}} />);

    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeEnabled();
  });

  it('disables Next on the last page and enables Previous', () => {
    render(<Pagination page={2} pageSize={10} total={25} onPageChange={() => {}} />);

    expect(screen.getByText('Page 3 of 3')).toBeInTheDocument();
    expect(screen.getByText('Showing 21–25 of 25 rows')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeEnabled();
  });

  it('requests the adjacent page on Previous / Next', async () => {
    const onPageChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Pagination page={1} pageSize={10} total={25} onPageChange={onPageChange} />,
    );

    await user.click(screen.getByRole('button', { name: 'Next page' }));
    expect(onPageChange).toHaveBeenCalledWith(2);

    await user.click(screen.getByRole('button', { name: 'Previous page' }));
    expect(onPageChange).toHaveBeenCalledWith(0);
  });

  it('conveys a single-page state with both controls disabled', () => {
    render(<Pagination page={0} pageSize={10} total={4} onPageChange={() => {}} />);

    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
    expect(screen.getByText('Showing 1–4 of 4 rows')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
  });

  it('handles an empty result set', () => {
    render(<Pagination page={0} pageSize={10} total={0} onPageChange={() => {}} />);

    expect(screen.getByText('No rows')).toBeInTheDocument();
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled();
  });
});
