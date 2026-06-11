"""
RektoFun Backend API

FastAPI + Supabase backend for persisting challenge metadata after a
successful Solana transaction.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from services.database import db_service, get_db_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan events.
    
    Initializes the Supabase database connection on startup
    and cleans up resources on shutdown.
    """
    # Startup: Initialize database connection
    logger.info("Initializing Supabase database connection...")
    try:
        db_service.initialize() 
        logger.info("Supabase database connection established successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase connection: {e}")
        raise
    
    yield
    
    # Shutdown: Cleanup resources
    logger.info("Shutting down and cleaning up resources...")
    await db_service.close()
    logger.info("Cleanup completed")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify API and database connectivity.
    """
    return {
        "status": "healthy",
        "version": settings.app_version,
        "database_connected": db_service.is_connected()
    }


# Include routers (to be added as needed)
# app.include_router(challenges.router, prefix="/api/v1/challenges", tags=["challenges"])
# app.include_router(transactions.router, prefix="/api/v1/transactions", tags=["transactions"])


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )