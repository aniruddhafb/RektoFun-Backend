"""
Configuration settings for RektoFun Backend API
"""

import os
from typing import List

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment variables"""

    # API Settings
    app_name: str = "RektoFun API"
    app_version: str = "1.0.0"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # CORS Settings
    @property
    def cors_origins(self) -> List[str]:
        origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
        return [origin.strip() for origin in origins.split(",")]

    # Supabase Settings
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")

    # Database connection settings (optional - for direct PostgreSQL connection)
    database_url: str = os.getenv("DATABASE_URL", "")

    @property
    def is_configured(self) -> bool:
        """Check if required Supabase configuration is present"""
        return bool(self.supabase_url and self.supabase_key)


# Global settings instance
settings = Settings()