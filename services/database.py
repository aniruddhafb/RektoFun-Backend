"""
Supabase database service for RektoFun Backend API

Provides database client initialization and connection management.
"""

from typing import Optional

from fastapi import Request

from supabase import Client, create_client

from config import get_settings


class DatabaseService:
    """Service for managing Supabase database connections"""

    _instance: Optional["DatabaseService"] = None
    _client: Optional[Client] = None

    def __new__(cls) -> "DatabaseService":
        """Singleton pattern to ensure single database service instance"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def initialize(self) -> Optional[Client]:
        """
        Initialize and return the Supabase client.

        Returns:
            Client: Configured Supabase client instance, or None if not configured

        Raises:
            RuntimeError: If client initialization fails
        """
        settings = get_settings()
        
        if not settings.is_configured:
            import logging
            logging.getLogger(__name__).warning(
                "Supabase configuration missing. Database features will be disabled."
            )
            return None

        try:
            if self._client is None:
                self._client = create_client(
                    settings.supabase_url,
                    settings.supabase_service_role_key
                )
            return self._client
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Supabase client: {str(e)}") from e

    @property
    def client(self) -> Client:
        """
        Get the Supabase client instance.

        Returns:
            Client: The Supabase client instance

        Raises:
            RuntimeError: If client has not been initialized
        """
        if self._client is None:
            raise RuntimeError(
                "Database client not initialized. Call initialize() first."
            )
        return self._client

    def get_client(self) -> Client:
        """
        Get the Supabase client, initializing if necessary.

        Returns:
            Client: The Supabase client instance
        """
        if self._client is None:
            return self.initialize()
        return self._client

    def is_connected(self) -> bool:
        """Check if the database client is initialized and connected"""
        return self._client is not None

    async def close(self) -> None:
        """Close the database connection and cleanup resources"""
        if self._client:
            # Supabase client handles connection pooling automatically
            self._client = None
            DatabaseService._instance = None


# Global database service instance
db_service = DatabaseService()


def get_db_client() -> Client:
    """
    Dependency function to get the database client.

    Returns:
        Client: The Supabase client instance
    """
    return db_service.get_client()


def get_service_db_client() -> Client:
    """Privileged client for authenticated mutations and internal jobs."""
    return db_service.get_client()


def get_public_db_client() -> Client:
    """Anon/RLS-scoped client for public read-only endpoints."""
    from config import get_public_supabase_client
    return get_public_supabase_client()


def get_request_db_client(request: Request) -> Client:
    """Select anon access for reads and service access for protected mutations."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return get_public_db_client()
    return get_service_db_client()
