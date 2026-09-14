import { Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { DashboardPage } from './pages/dashboard/DashboardPage';
import { AssetsPage } from './pages/assets/AssetsPage';
import { AssetDetailPage } from './pages/assets/AssetDetailPage';
import { PortfoliosPage } from './pages/portfolios/PortfoliosPage';
import { PortfolioDetailPage } from './pages/portfolios/PortfolioDetailPage';
import { PaperTradingPage } from './pages/paper-trading/PaperTradingPage';
import { PaperTradingSessionPage } from './pages/paper-trading/PaperTradingSessionPage';

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="assets" element={<AssetsPage />} />
        <Route path="assets/:ticker" element={<AssetDetailPage />} />
        <Route path="portfolios" element={<PortfoliosPage />} />
        <Route path="portfolios/:id" element={<PortfolioDetailPage />} />
        <Route path="paper-trading" element={<PaperTradingPage />} />
        <Route path="paper-trading/:id" element={<PaperTradingSessionPage />} />
      </Route>
    </Routes>
  );
}

export default App;
