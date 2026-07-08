"""
User service for CRUD operations on the user table.
"""

import logging
import secrets
import string
from typing import Optional

from supabase import Client

from models.user import UserCreate, UserUpdate, UserResponse

logger = logging.getLogger(__name__)


class UserService:
    """Service for managing user operations with Supabase"""

    def __init__(self, db_client: Client):
        self.db = db_client
        self.table = "user"

    def _normalize_referral_code(self, referral_code: str) -> str:
        return referral_code.strip().upper()

    async def _generate_referral_code(self) -> str:
        alphabet = string.ascii_uppercase + string.digits

        for _ in range(10):
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            existing_user = await self.get_user_by_referral_code(code)
            if not existing_user:
                return code

        raise Exception("Failed to generate a unique referral code")

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
            data = user_data.model_dump(exclude_unset=True, exclude_none=True, exclude={"referrer_code"})

            if "referral_code" in data:
                data["referral_code"] = self._normalize_referral_code(data["referral_code"])
            else:
                data["referral_code"] = await self._generate_referral_code()

            data.setdefault("referrals", [])
            result = self.db.table(self.table).insert(data).execute()
            
            if not result.data:
                raise Exception("Failed to create user - no data returned")
            
            created_user = result.data[0]
            logger.info(f"Created user with ID: {created_user['id']}")
            return UserResponse(**created_user)
            
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise

    async def get_user_by_referral_code(self, referral_code: str) -> Optional[UserResponse]:
        """
        Get a user by their referral code.
        """
        try:
            normalized_code = self._normalize_referral_code(referral_code)
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("referral_code", normalized_code)
                .execute()
            )

            if not result.data:
                return None

            return UserResponse(**result.data[0])

        except Exception as e:
            logger.error(f"Error fetching user by referral code {referral_code}: {e}")
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

    async def get_user_by_username(self, username: str) -> Optional[UserResponse]:
        """
        Get a user by username.

        Args:
            username: The username to look up

        Returns:
            UserResponse if found, None otherwise

        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("username", username)
                .execute()
            )

            if not result.data:
                return None

            return UserResponse(**result.data[0])

        except Exception as e:
            logger.error(f"Error fetching user by username {username}: {e}")
            raise

    async def username_exists(self, username: str) -> bool:
        """
        Check whether a username is already taken.

        Args:
            username: The username to check

        Returns:
            True if a user with this username exists, False otherwise

        Raises:
            Exception: If database operation fails
        """
        return await self.get_user_by_username(username) is not None

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

    async def accept_referral(self, new_user_wallet: str, referrer_code: str) -> UserResponse:
        """
        Apply a referral code to a user and record the referred wallet on the referrer.
        """
        try:
            normalized_code = self._normalize_referral_code(referrer_code)
            new_user = await self.get_user_by_pubkey(new_user_wallet)
            if not new_user:
                raise ValueError("User accepting referral was not found")

            referrer = await self.get_user_by_referral_code(normalized_code)
            if not referrer:
                raise ValueError("Referral code not found")

            if new_user.pubkey == referrer.pubkey:
                raise ValueError("You cannot redeem your own referral code")

            if new_user.referred_by:
                raise ValueError("Referral code already redeemed")

            referrals = list(referrer.referrals or [])
            if new_user.pubkey and new_user.pubkey not in referrals:
                referrals.append(new_user.pubkey)

            self.db.table(self.table).update({"referred_by": normalized_code}).eq("id", new_user.id).execute()
            self.db.table(self.table).update({"referrals": referrals}).eq("id", referrer.id).execute()

            updated_user = await self.get_user(new_user.id)
            if not updated_user:
                raise Exception("Failed to load updated user after accepting referral")

            logger.info(f"Accepted referral {normalized_code} for user {new_user.id}")
            return updated_user

        except Exception as e:
            logger.error(f"Error accepting referral: {e}")
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
