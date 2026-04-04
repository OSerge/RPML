from fastapi import APIRouter

from server.api.v1.auth import router as auth_router
from server.api.v1.dashboard import router as dashboard_router
from server.api.v1.demo import router as demo_router
from server.api.v1.debts import router as debts_router
from server.api.v1.optimization import router as optimization_router
from server.api.v1.plans import router as plans_router
from server.api.v1.scenario import router as scenario_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(demo_router, prefix="/demo", tags=["demo"])
api_router.include_router(debts_router, prefix="/debts", tags=["debts"])
api_router.include_router(scenario_router, prefix="/scenario", tags=["scenario"])
api_router.include_router(optimization_router, prefix="/optimization", tags=["optimization"])
api_router.include_router(plans_router, prefix="/optimization", tags=["optimization"])
