"""
RektoFun Backend API

FastAPI + Supabase backend for persisting challenge metadata after a
successful Solana transaction.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from config import get_settings
from services.database import db_service, get_db_client
from services.challenge_monitor_service import (
    start_challenge_monitor,
    stop_challenge_monitor,
)
from routes import users, challenges, positions, email_subscription, categories, notifications, activity

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan events.
    
    Initializes the Supabase database connection on startup,
    starts the challenge monitor for real-time price tracking,
    and cleans up resources on shutdown.
    """
    # Startup: Initialize database connection
    logger.info("Initializing Supabase database connection...")
    try:
        db_service.initialize() 
        logger.info("Supabase database connection established successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase connection: {e}")
        logger.warning("Continuing without database - API will return errors for DB operations")
        # Don't raise - continue without database
    
    # Startup: Initialize challenge monitor
    logger.info("Starting challenge monitor service...")
    try:
        await start_challenge_monitor()
        logger.info("Challenge monitor service started successfully")
    except Exception as e:
        logger.error(f"Failed to start challenge monitor service: {e}")
        # Don't raise - we can still run without the monitor
    
    yield
    
    # Shutdown: Cleanup resources
    logger.info("Shutting down and cleaning up resources...")
    
    # Stop challenge monitor
    try:
        await stop_challenge_monitor()
        logger.info("Challenge monitor service stopped")
    except Exception as e:
        logger.error(f"Error stopping challenge monitor: {e}")
    
    # Close database connection
    await db_service.close()
    logger.info("Cleanup completed")


app = FastAPI(
    title=get_settings().app_name,
    version=get_settings().app_version,
    lifespan=lifespan
)

# Configure CORS - TEMPORARILY ALLOW ALL ORIGINS
# TODO: Restrict origins once the frontend domain is finalized.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# Handle OPTIONS preflight requests globally
@app.options("/{path:path}")
async def handle_options(request: Request, path: str):
    """
    Handle CORS preflight requests for all routes.
    Mirrors any origin so cross-origin POSTs (e.g., create_challenge) work.
    """
    origin = request.headers.get("origin", "*")
    headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
        "Access-Control-Allow-Credentials": "false",
        "Access-Control-Max-Age": "86400",
    }
    return Response(status_code=200, headers=headers)


@app.get("/health")
async def health_check():
    """
    Health check endpoint to verify API and database connectivity.
    """
    return {
        "status": "healthy",
        "version": get_settings().app_version,
        "database_connected": db_service.is_connected()
    }



# Include routers
app.include_router(users.router, prefix="/api", tags=["users"])

# Include challenge routes
app.include_router(challenges.router, prefix="/api", tags=["challenges"])

# Include position routes
app.include_router(positions.router, prefix="/api", tags=["positions"])

# Include email subscription routes
app.include_router(email_subscription.router)

# Include category routes
app.include_router(categories.router, prefix="/api", tags=["categories"])
app.include_router(notifications.router, prefix="/api", tags=["notifications"])
app.include_router(activity.router, prefix="/api", tags=["activity"])

# Future routers (to be added as needed)
# app.include_router(transactions.router, prefix="/api/v1/transactions", tags=["transactions"])


# Import Mangum for serverless deployment (Vercel)
try:
    from mangum import Mangum
    # Use lifespan="auto" so FastAPI's startup/shutdown hooks (including
    # start_challenge_monitor) are executed even in the serverless environment.
    # Previously "off" meant the lifespan context never ran, so _ws_client was
    # always None and no streams were ever activated.
    handler = Mangum(app, lifespan="auto")
    logger.info("Mangum handler created for serverless deployment")
except ImportError:
    handler = None
    logger.info("Mangum not installed, running in traditional mode")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=get_settings().debug
    )
