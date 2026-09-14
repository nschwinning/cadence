import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { DashboardIcon } from '../icons/DashboardIcon';
import { AssetsIcon } from '../icons/AssetsIcon';
import { PortfoliosIcon } from '../icons/PortfoliosIcon';
import { PaperTradingIcon } from '../icons/PaperTradingIcon';

interface SidebarProps {
  /** Whether the off-canvas sidebar is open (narrow viewports only). */
  isOpen: boolean;
  /** Closes the off-canvas sidebar (overlay click / after navigating). */
  onClose: () => void;
}

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  /** Whether the link matches only the exact path (index route). */
  end?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: <DashboardIcon className="h-5 w-5" />, end: true },
  { to: '/assets', label: 'Assets', icon: <AssetsIcon className="h-5 w-5" /> },
  { to: '/portfolios', label: 'Portfolios', icon: <PortfoliosIcon className="h-5 w-5" /> },
  {
    to: '/paper-trading',
    label: 'Paper Trading',
    icon: <PaperTradingIcon className="h-5 w-5" />,
  },
];

/**
 * Left side navigation menu. Permanently visible at `xl`+; off-canvas below
 * `xl`, opened from the header and dismissed via the dimmed overlay.
 */
export function Sidebar({ isOpen, onClose }: SidebarProps) {
  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 xl:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed bottom-0 left-0 top-[60px] z-40 w-[270px] overflow-y-auto border-r border-slate-200 bg-white transition-transform duration-300 ease-in-out xl:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <nav className="p-3" aria-label="Main">
          <ul className="m-0 list-none p-0">
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.end}
                  onClick={onClose}
                  className={({ isActive }) =>
                    `flex items-center gap-2 rounded px-3 py-2 no-underline ${
                      isActive
                        ? 'bg-emerald-500 text-white'
                        : 'text-slate-700 hover:bg-[#f5f7fa]'
                    }`
                  }
                >
                  {item.icon}
                  <span>{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
    </>
  );
}

export default Sidebar;
