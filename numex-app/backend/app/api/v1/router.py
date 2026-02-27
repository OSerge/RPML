"""API v1 router."""

from fastapi import APIRouter

from app.api.v1 import auth, debts, plans, budget, goals, chat, simulator

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(debts.router, prefix="/debts", tags=["debts"])
api_router.include_router(plans.router, prefix="/optimize", tags=["optimize"])
api_router.include_router(budget.router, prefix="/budget", tags=["budget"])
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
api_router.include_router(chat.router, prefix="/explain", tags=["explain"])
api_router.include_router(simulator.router, prefix="/simulator", tags=["simulator"])
