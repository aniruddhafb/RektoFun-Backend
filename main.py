"""
RektoFun Backend API

FastAPI + Supabase backend for persisting challenge metadata after a
successful Solana transaction.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routes import challenge_sides, challenges, challenge_outcomes, health, markets, positions, users, clans

app = FastAPI(title="RektoFun API", version="1.0.0")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(users.router)
app.include_router(challenges.router)
app.include_router(challenge_outcomes.router)
app.include_router(challenge_sides.router)
app.include_router(positions.router)
app.include_router(markets.router)
app.include_router(clans.router)
