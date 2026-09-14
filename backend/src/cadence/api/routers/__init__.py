"""Router aggregation. Each resource exposes a ``<name>_router``."""

from cadence.api.routers.ai_portfolio import router as ai_portfolio_router
from cadence.api.routers.assets import router as assets_router
from cadence.api.routers.dashboard import router as dashboard_router
from cadence.api.routers.health import router as health_router
from cadence.api.routers.paper_trading import router as paper_trading_router
from cadence.api.routers.portfolios import router as portfolios_router
from cadence.api.routers.recommendations import router as recommendations_router

__all__ = [
    "ai_portfolio_router",
    "assets_router",
    "dashboard_router",
    "health_router",
    "paper_trading_router",
    "portfolios_router",
    "recommendations_router",
]
