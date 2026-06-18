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

from config import settings
from services.database import db_service, get_db_client
from services.challenge_monitor_service import (
    start_challenge_monitor,
    stop_challenge_monitor,
)
from routes import users, challenges, positions, email_subscription

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
        raise
    
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


# Handle OPTIONS preflight requests globally
@app.options("/{path:path}")
async def handle_options(request: Request, path: str):
    """
    Handle CORS preflight requests for all routes.
    This ensures OPTIONS requests return a 200 OK response.
    """
    origin = request.headers.get("origin", "")
    if origin in settings.cors_origins:
        headers = {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Requested-With",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "86400",
        }
        return Response(status_code=200, headers=headers)
    return Response(status_code=200)


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



# Include routers
app.include_router(users.router, prefix="/api", tags=["users"])

# Include challenge routes
app.include_router(challenges.router, prefix="/api", tags=["challenges"])

# Include position routes
app.include_router(positions.router, prefix="/api", tags=["positions"])

# Include email subscription routes
app.include_router(email_subscription.router)

# Future routers (to be added as needed)
# app.include_router(transactions.router, prefix="/api/v1/transactions", tags=["transactions"])


# Import Mangum for serverless deployment (Vercel)
try:
    from mangum import Mangum
    # Create handler for serverless deployment
    handler = Mangum(app, lifespan="off")
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
        reload=settings.debug
    )
