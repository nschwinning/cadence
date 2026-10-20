import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { DashboardIcon } from '../icons/DashboardIcon';
import { AssetsIcon } from '../icons/AssetsIcon';
import { WatchlistIcon } from '../icons/WatchlistIcon';
import { PortfoliosIcon } from '../icons/PortfoliosIcon';
import { RunsIcon } from '../icons/RunsIcon';
import { TechnicalIndicatorsIcon } from '../icons/TechnicalIndicatorsIcon';
import { SystemIcon } from '../icons/SystemIcon';

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
  {
    to: '/watchlist',
    label: 'Watchlist',
    icon: <WatchlistIcon className="h-5 w-5" />,
  },
  { to: '/portfolios', label: 'Portfolios', icon: <PortfoliosIcon className="h-5 w-5" /> },
  { to: '/runs', label: 'Runs', icon: <RunsIcon className="h-5 w-5" /> },
  {
    to: '/technical-indicators',
    label: 'Technical Indicators',
    icon: <TechnicalIndicatorsIcon className="h-5 w-5" />,
  },
  { to: '/system', label: 'System', icon: <SystemIcon className="h-5 w-5" /> },
];

/**
 * Left side navigation menu. Permanently visible at `xl`+; off-canvas below
 * `xl`, opened from the header and dismissed via the dimmed overlay.
 */
export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const location = useLocation();
  const navState = location.state as { from?: string } | null;
  // An asset detail page (`/assets/:ticker`) opened from the watchlist belongs to
  // the Watchlist view, not the Assets list. The URL alone can't express that, so
  // we read the router link state the watchlist sets when navigating. On a direct
  // load or refresh (no state) this falls back to the URL-based Assets highlight.
  const inWatchlistAssetContext =
    /^\/assets\/[^/]+$/.test(location.pathname) && navState?.from === 'watchlist';

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
                  className={({ isActive }) => {
                    let active = isActive;
                    if (inWatchlistAssetContext) {
                      // Shift the highlight off Assets and onto Watchlist for a
                      // watchlist-originated asset detail page.
                      if (item.to === '/assets') active = false;
                      else if (item.to === '/watchlist') active = true;
                    }
                    return `flex items-center gap-2 rounded px-3 py-2 no-underline ${
                      active
                        ? 'bg-emerald-500 text-white'
                        : 'text-slate-700 hover:bg-[#f5f7fa]'
                    }`;
                  }}
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
