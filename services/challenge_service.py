"""
Challenge service for CRUD operations on the challenge table.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from supabase import Client

from models.challenge import ChallengeCreate, ChallengeUpdate, ChallengeResponse, ChallengeStatus
from services.category_service import CategoryService

logger = logging.getLogger(__name__)


class ChallengeService:
    """Service for managing challenge operations with Supabase"""

    def __init__(self, db_client: Client):
        self.db = db_client
        self.table = "challenge"

    async def create_challenge(self, challenge_data: ChallengeCreate) -> ChallengeResponse:
        """
        Create a new challenge in the database.
        
        Args:
            challenge_data: Challenge data to create
            
        Returns:
            ChallengeResponse: Created challenge data
            
        Raises:
            Exception: If database operation fails
        """
        try:
            data = challenge_data.model_dump(exclude_unset=True, mode="json")
            result = self.db.table(self.table).insert(data).execute()
            
            if not result.data:
                raise Exception("Failed to create challenge - no data returned")
            
            created_challenge = result.data[0]
            logger.info(f"Created challenge with ID: {created_challenge['id']}")

            if created_challenge.get("category"):
                try:
                    CategoryService(self.db).increment_challenges_count(created_challenge["category"])
                except Exception as e:
                    logger.warning(f"Failed to increment challenges_count for category '{created_challenge['category']}': {e}")

            return ChallengeResponse(**created_challenge)
            
        except Exception as e:
            logger.error(f"Error creating challenge: {e}")
            raise

    async def get_challenge(self, challenge_id: int) -> Optional[ChallengeResponse]:
        """
        Get a challenge by ID.
        
        Args:
            challenge_id: The challenge ID to look up
            
        Returns:
            ChallengeResponse if found, None otherwise
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("id", challenge_id)
                .execute()
            )
            
            if not result.data:
                return None
            
            return ChallengeResponse(**result.data[0])
            
        except Exception as e:
            logger.error(f"Error fetching challenge {challenge_id}: {e}")
            raise

    async def increment_views(self, challenge_id: int) -> Optional[int]:
        """Atomically increment and return a challenge's view count."""
        try:
            result = self.db.rpc(
                "increment_challenge_views",
                {"p_challenge_id": challenge_id},
            ).execute()

            data = result.data
            if isinstance(data, list):
                if not data:
                    return None
                data = data[0]
            if isinstance(data, dict):
                data = data.get("views")
            if data is None:
                return None

            return int(data)
        except Exception as e:
            logger.error(f"Error incrementing views for challenge {challenge_id}: {e}")
            raise

    async def get_challenges_by_creator(self, creator_id: int) -> list[ChallengeResponse]:
        """
        Get all challenges created by a specific user.
        
        Args:
            creator_id: The user ID of the creator
            
        Returns:
            List of ChallengeResponse objects
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("creator", creator_id)
                .execute()
            )
            
            return [ChallengeResponse(**challenge) for challenge in result.data]
            
        except Exception as e:
            logger.error(f"Error fetching challenges by creator {creator_id}: {e}")
            raise

    async def get_challenges_by_status(self, status: ChallengeStatus) -> list[ChallengeResponse]:
        """
        Get all challenges with a specific status.
        
        Args:
            status: The challenge status to filter by
            
        Returns:
            List of ChallengeResponse objects
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("status", status.value)
                .execute()
            )
            
            return [ChallengeResponse(**challenge) for challenge in result.data]
            
        except Exception as e:
            logger.error(f"Error fetching challenges by status {status}: {e}")
            raise

    async def get_challenges_by_category(self, category: str) -> list[ChallengeResponse]:
        """
        Get all challenges belonging to a specific category (case-insensitive exact match).

        Args:
            category: The category name to filter by

        Returns:
            List of ChallengeResponse objects

        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*, creator_details:user!challenge_creator_fkey(*)")
                .ilike("category", category)
                .execute()
            )

            return [ChallengeResponse(**challenge) for challenge in result.data]

        except Exception as e:
            logger.error(f"Error fetching challenges by category {category}: {e}")
            raise

    async def list_challenges(
        self,
        limit: int = 100,
        offset: int = 0,
        resolution_source: str | None = None,
    ) -> list[ChallengeResponse]:
        """
        List challenges with pagination.
        
        Args:
            limit: Maximum number of challenges to return
            offset: Number of challenges to skip
            
        Returns:
            List of ChallengeResponse objects
            
        Raises:
            Exception: If database operation fails
        """
        try:
            query = self.db.table(self.table).select(
                "*, creator_details:user!challenge_creator_fkey(*)"
            )
            if resolution_source:
                query = query.ilike("resolution_source", resolution_source)
            result = query.range(offset, offset + limit - 1).execute()

            return [ChallengeResponse(**challenge) for challenge in result.data]

        except Exception as e:
            logger.error(f"Error listing challenges: {e}")
            raise

    async def update_challenge(
        self,
        challenge_id: int,
        challenge_data: ChallengeUpdate
    ) -> Optional[ChallengeResponse]:
        """
        Update a challenge by ID.
        
        Args:
            challenge_id: The challenge ID to update
            challenge_data: Updated challenge data
            
        Returns:
            ChallengeResponse if updated, None if challenge not found
            
        Raises:
            Exception: If database operation fails
        """
        try:
            data = challenge_data.model_dump(exclude_unset=True, exclude_none=True, mode="json")
            
            if not data:
                logger.warning("No data provided for challenge update")
                return await self.get_challenge(challenge_id)
            
            result = (
                self.db.table(self.table)
                .update(data)
                .eq("id", challenge_id)
                .execute()
            )
            
            if not result.data:
                return None
            
            updated_challenge = result.data[0]
            logger.info(f"Updated challenge with ID: {challenge_id}")
            return ChallengeResponse(**updated_challenge)
            
        except Exception as e:
            logger.error(f"Error updating challenge {challenge_id}: {e}")
            raise

    async def delete_challenge(self, challenge_id: int) -> bool:
        """
        Delete a challenge by ID.
        
        Args:
            challenge_id: The challenge ID to delete
            
        Returns:
            True if deleted, False if challenge not found
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .delete()
                .eq("id", challenge_id)
                .execute()
            )

            if result.data:
                logger.info(f"Deleted challenge with ID: {challenge_id}")

                deleted_challenge = result.data[0]
                if deleted_challenge.get("category"):
                    try:
                        CategoryService(self.db).decrement_challenges_count(deleted_challenge["category"])
                    except Exception as e:
                        logger.warning(f"Failed to decrement challenges_count for category '{deleted_challenge['category']}': {e}")

                return True

            return False
            
        except Exception as e:
            logger.error(f"Error deleting challenge {challenge_id}: {e}")
            raise

    async def count_challenges(self, resolution_source: str | None = None) -> int:
        """
        Get total count of challenges.
        
        Returns:
            Total number of challenges
            
        Raises:
            Exception: If database operation fails
        """
        try:
            query = self.db.table(self.table).select("*", count="exact")
            if resolution_source:
                query = query.ilike("resolution_source", resolution_source)
            result = query.execute()
            
            return result.count or 0
            
        except Exception as e:
            logger.error(f"Error counting challenges: {e}")
            raise

    async def update_challenge_status(
        self,
        challenge_id: int,
        new_status: ChallengeStatus,
        end_price: float = None,
        final_price: float = None
    ) -> Optional[ChallengeResponse]:
        """
        Update the status of a challenge.
        
        Args:
            challenge_id: The ID of the challenge to update
            new_status: The new status value
            end_price: Optional end price when completing a challenge (deprecated, use final_price)
            final_price: Optional final price when completing a challenge
            
        Returns:
            ChallengeResponse if updated, None if challenge not found
            
        Raises:
            ValueError: If status transition is invalid
            Exception: If database operation fails
        """
        try:
            # Get current challenge
            challenge = await self.get_challenge(challenge_id)
            if not challenge:
                return None
            
            # Validate status transition
            valid_transitions = {
                ChallengeStatus.OPEN: [ChallengeStatus.PENDING_RESOLUTION, ChallengeStatus.RESOLVED, ChallengeStatus.CANCELLED, ChallengeStatus.EXPIRED],
                ChallengeStatus.PENDING_RESOLUTION: [ChallengeStatus.RESOLVED, ChallengeStatus.CANCELLED],
                ChallengeStatus.RESOLVED: [],
                ChallengeStatus.EXPIRED: [],
                ChallengeStatus.CANCELLED: [ChallengeStatus.OPEN],
            }
            
            current_status = ChallengeStatus(challenge.status)
            
            if new_status not in valid_transitions.get(current_status, []):
                raise ValueError(
                    f"Invalid status transition from {current_status.value} to {new_status.value}"
                )
            
            # Prepare update data
            update_data = {"status": new_status.value}
            price_to_use = final_price if final_price is not None else end_price
            if new_status == ChallengeStatus.RESOLVED and price_to_use is not None:
                update_data["final_price"] = round(price_to_use)
            if new_status == ChallengeStatus.RESOLVED:
                update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
            
            # Update in database
            result = (
                self.db.table(self.table)
                .update(update_data)
                .eq("id", challenge_id)
                .execute()
            )
            
            if not result.data:
                return None
            
            updated_challenge = result.data[0]
            logger.info(f"Updated challenge {challenge_id} status to {new_status.value}")
            return ChallengeResponse(**updated_challenge)
            
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Error updating challenge status for {challenge_id}: {e}")
            raise

    async def get_expired_open_challenges(self) -> list[dict]:
        """
        Get all OPEN challenges that have passed their expiry timestamp.
        These challenges should transition to PENDING_RESOLUTION.
        
        Returns:
            List of challenge dictionaries that have expired
            
        Raises:
            Exception: If database operation fails
        """
        try:
            from datetime import datetime, timezone
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("status", ChallengeStatus.OPEN.value)
                .lt("expiry", datetime.now(timezone.utc).isoformat())
                .execute()
            )
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Error fetching expired open challenges: {e}")
            raise

    async def get_active_challenges_raw(self) -> list[dict]:
        """
        Get all active challenges as raw dictionaries.
        Used by the challenge monitor service.
        
        Returns:
            List of challenge dictionaries
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("status", ChallengeStatus.OPEN.value)
                .execute()
            )
            
            return result.data or []
            
        except Exception as e:
            logger.error(f"Error fetching active challenges: {e}")
            raise


def get_challenge_service(db_client: Client) -> ChallengeService:
    """
    Factory function to create a ChallengeService instance.
    
    Args:
        db_client: The Supabase client
        
    Returns:
        ChallengeService instance
    """
    return ChallengeService(db_client)
