"""
User service for CRUD operations on the user table.
"""

import logging
from typing import Optional

from supabase import Client

from models.user import UserCreate, UserUpdate, UserResponse

logger = logging.getLogger(__name__)


class UserService:
    """Service for managing user operations with Supabase"""

    def __init__(self, db_client: Client):
        self.db = db_client
        self.table = "user"

    async def create_user(self, user_data: UserCreate) -> UserResponse:
        """
        Create a new user in the database.
        
        Args:
            user_data: User data to create
            
        Returns:
            UserResponse: Created user data
            
        Raises:
            Exception: If database operation fails
        """
        try:
            data = user_data.model_dump(exclude_unset=True)
            result = self.db.table(self.table).insert(data).execute()
            
            if not result.data:
                raise Exception("Failed to create user - no data returned")
            
            created_user = result.data[0]
            logger.info(f"Created user with ID: {created_user['id']}")
            return UserResponse(**created_user)
            
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise

    async def get_user(self, user_id: int) -> Optional[UserResponse]:
        """
        Get a user by ID.
        
        Args:
            user_id: The user ID to look up
            
        Returns:
            UserResponse if found, None otherwise
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("id", user_id)
                .execute()
            )
            
            if not result.data:
                return None
            
            return UserResponse(**result.data[0])
            
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            raise

    async def get_user_by_pubkey(self, pubkey: str) -> Optional[UserResponse]:
        """
        Get a user by their Solana public key.
        
        Args:
            pubkey: The Solana public key to look up
            
        Returns:
            UserResponse if found, None otherwise
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("pubkey", pubkey)
                .execute()
            )
            
            if not result.data:
                return None
            
            return UserResponse(**result.data[0])
            
        except Exception as e:
            logger.error(f"Error fetching user by pubkey {pubkey}: {e}")
            raise

    async def get_user_by_email(self, email: str) -> Optional[UserResponse]:
        """
        Get a user by email.
        
        Args:
            email: The email to look up
            
        Returns:
            UserResponse if found, None otherwise
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("email", email)
                .execute()
            )
            
            if not result.data:
                return None
            
            return UserResponse(**result.data[0])
            
        except Exception as e:
            logger.error(f"Error fetching user by email {email}: {e}")
            raise

    async def list_users(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> list[UserResponse]:
        """
        List users with pagination.
        
        Args:
            limit: Maximum number of users to return
            offset: Number of users to skip
            
        Returns:
            List of UserResponse objects
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .range(offset, offset + limit - 1)
                .execute()
            )
            
            return [UserResponse(**user) for user in result.data]
            
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            raise

    async def update_user(
        self,
        user_id: int,
        user_data: UserUpdate
    ) -> Optional[UserResponse]:
        """
        Update a user by ID.
        
        Args:
            user_id: The user ID to update
            user_data: Updated user data
            
        Returns:
            UserResponse if updated, None if user not found
            
        Raises:
            Exception: If database operation fails
        """
        try:
            data = user_data.model_dump(exclude_unset=True, exclude_none=True)
            
            if not data:
                logger.warning("No data provided for user update")
                return await self.get_user(user_id)
            
            result = (
                self.db.table(self.table)
                .update(data)
                .eq("id", user_id)
                .execute()
            )
            
            if not result.data:
                return None
            
            updated_user = result.data[0]
            logger.info(f"Updated user with ID: {user_id}")
            return UserResponse(**updated_user)
            
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {e}")
            raise

    async def delete_user(self, user_id: int) -> bool:
        """
        Delete a user by ID.
        
        Args:
            user_id: The user ID to delete
            
        Returns:
            True if deleted, False if user not found
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .delete()
                .eq("id", user_id)
                .execute()
            )
            
            if result.data:
                logger.info(f"Deleted user with ID: {user_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            raise

    async def count_users(self) -> int:
        """
        Get total count of users.
        
        Returns:
            Total number of users
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*", count="exact")
                .limit(0)
                .execute()
            )
            
            return result.count or 0
            
        except Exception as e:
            logger.error(f"Error counting users: {e}")
            raise


def get_user_service(db_client: Client) -> UserService:
    """
    Factory function to create a UserService instance.
    
    Args:
        db_client: The Supabase client
        
    Returns:
        UserService instance
    """
    return UserService(db_client)