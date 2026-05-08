"""
RektoFun Backend API

FastAPI + Supabase backend for persisting challenge metadata after a
successful Solana transaction.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings, get_supabase_client
from routes import challenge_sides, challenges, challenge_outcomes, health, markets, positions, users, clans, transform
from services.birdeye_price_logger import BirdeyePriceLogger
from services.challenge_scheduler import ChallengeScheduler
from services.scheduler_registry import set_scheduler


settings = get_settings()
birdeye_price_logger = BirdeyePriceLogger(settings)
challenge_scheduler = ChallengeScheduler(get_supabase_client())
set_scheduler(challenge_scheduler)


@asynccontextmanager
async def lifespan(_: FastAPI):
    birdeye_price_logger.start()
    challenge_scheduler.start()
    try:
        yield
    finally:
        await birdeye_price_logger.stop()
        await challenge_scheduler.stop()


app = FastAPI(title="RektoFun API", version="1.0.0", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(users.router)
app.include_router(challenges.router)
app.include_router(transform.router)
app.include_router(challenge_outcomes.router)
app.include_router(challenge_sides.router)
app.include_router(positions.router)
app.include_router(markets.router)
app.include_router(clans.router)
