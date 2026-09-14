import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

/**
 * Persistent application shell: a sticky top menu, a left side menu, and a
 * main content region that renders the active route via `<Outlet />`.
 * Owns the off-canvas sidebar open/close state for narrow viewports.
 */
export function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#f5f7fa]">
      <Header onToggleSidebar={() => setSidebarOpen((open) => !open)} />

      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <main className="min-h-[calc(100vh-60px)] bg-[#f5f7fa] p-4 xl:ml-[270px]">
        <Outlet />
      </main>
    </div>
  );
}

export default Layout;
