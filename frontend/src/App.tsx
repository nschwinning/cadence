import { Routes, Route, Navigate, useParams } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { DashboardPage } from './pages/dashboard/DashboardPage';
import { AssetsPage } from './pages/assets/AssetsPage';
import { AssetDetailPage } from './pages/assets/AssetDetailPage';
import { WatchlistPage } from './pages/watchlist/WatchlistPage';
import { PaperTradingPage } from './pages/paper-trading/PaperTradingPage';
import { PaperTradingSessionPage } from './pages/paper-trading/PaperTradingSessionPage';
import { BotsPage } from './pages/bots/BotsPage';
import { BotSessionPage } from './pages/bots/BotSessionPage';
import { OrchestratorsPage } from './pages/orchestrators/OrchestratorsPage';
import { OrchestratorDetailPage } from './pages/orchestrators/OrchestratorDetailPage';
import { StrategiesPage } from './pages/bots/StrategiesPage';
import { StrategyDetailPage } from './pages/bots/StrategyDetailPage';
import { RunsPage } from './pages/runs/RunsPage';
import { RunDetailPage } from './pages/runs/RunDetailPage';
import { TechnicalIndicatorsPage } from './pages/technical-indicators/TechnicalIndicatorsPage';
import { SystemStatusPage } from './pages/system/SystemStatusPage';
import { AdminPage } from './pages/admin/AdminPage';

/**
 * Redirect a legacy `/paper-trading/:id` deep link to the merged
 * `/portfolios/:id` detail route, preserving the session id. The old
 * paper-trading area was folded into Portfolios.
 */
function PaperTradingSessionRedirect() {
  const { id = '' } = useParams<{ id: string }>();
  return <Navigate to={`/portfolios/${id}`} replace />;
}

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="assets" element={<AssetsPage />} />
        <Route path="assets/:ticker" element={<AssetDetailPage />} />
        <Route path="watchlist" element={<WatchlistPage />} />
        <Route path="portfolios" element={<PaperTradingPage />} />
        <Route path="portfolios/:id" element={<PaperTradingSessionPage />} />
        <Route path="bots" element={<BotsPage />} />
        {/* Static strategy routes must precede the `:id` param route. */}
        <Route path="bots/strategies" element={<StrategiesPage />} />
        <Route path="bots/strategies/:key" element={<StrategyDetailPage />} />
        <Route path="bots/:id" element={<BotSessionPage />} />
        <Route path="orchestrators" element={<OrchestratorsPage />} />
        <Route path="orchestrators/:id" element={<OrchestratorDetailPage />} />
        {/* Legacy routes: the paper-trading area merged into Portfolios. */}
        <Route
          path="paper-trading"
          element={<Navigate to="/portfolios" replace />}
        />
        <Route
          path="paper-trading/:id"
          element={<PaperTradingSessionRedirect />}
        />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:id" element={<RunDetailPage />} />
        <Route
          path="technical-indicators"
          element={<TechnicalIndicatorsPage />}
        />
        <Route path="system" element={<SystemStatusPage />} />
        <Route path="admin" element={<AdminPage />} />
      </Route>
    </Routes>
  );
}

export default App;
