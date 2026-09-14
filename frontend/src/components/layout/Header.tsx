import logoUrl from '../../assets/cadence-logo.svg';
import { HamburgerIcon } from '../icons/HamburgerIcon';

interface HeaderProps {
  /** Toggles the off-canvas sidebar on narrow viewports. */
  onToggleSidebar: () => void;
}

/** Dark, sticky top menu: brand on the left, mobile nav toggle beside it. */
export function Header({ onToggleSidebar }: HeaderProps) {
  return (
    <header className="sticky top-0 z-30 flex h-[60px] items-center gap-3 bg-[#2a3547] px-4 text-white">
      <button
        type="button"
        onClick={onToggleSidebar}
        aria-label="Toggle navigation menu"
        className="-ml-1 inline-flex items-center justify-center rounded p-1 text-white hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/50 xl:hidden"
      >
        <HamburgerIcon className="h-6 w-6" />
      </button>

      <a href="/" className="flex items-center gap-2 no-underline">
        <img src={logoUrl} alt="" className="h-8 w-8" />
        <span className="text-lg font-semibold text-white">Cadence</span>
      </a>
    </header>
  );
}

export default Header;
