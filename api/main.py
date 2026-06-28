"""
Vercel serverless entry point for RektoFun Backend.
This file MUST exist at /api/main.py because Vercel Python deployments
require the entry handler inside an /api directory.

It re-exports the FastAPI app from the project root so routes are preserved.
"""
import sys
from pathlib import Path

# Add project root to Python path so `import main` resolves to root/main.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Re-export the FastAPI application with Mangum handler
from main import app, handler  # noqa: F401,E402
