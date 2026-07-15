"""
Position service for CRUD operations on the position table.
"""

import logging
from typing import Optional

from supabase import Client

from models.position import PositionCreate, PositionUpdate, PositionResponse, Side
from models.challenge import ChallengeUpdate
from services.challenge_service import get_challenge_service
from services.user_service import get_user_service
from services.category_service import CategoryService
from services.notification_service import get_notification_service

logger = logging.getLogger(__name__)


class PositionService:
    """Service for managing position operations with Supabase"""

    def __init__(self, db_client: Client):
        self.db = db_client
        self.table = "position"

    async def create_position(self, position_data: PositionCreate) -> PositionResponse:
        """
        Create a new position in the database.
        
        Args:
            position_data: Position data to create
            
        Returns:
            PositionResponse: Created position data
            
        Raises:
            Exception: If database operation fails
        """
        try:
            data = position_data.model_dump(exclude_unset=True)
            result = self.db.table(self.table).insert(data).execute()
            
            if not result.data:
                raise Exception("Failed to create position - no data returned")
            
            created_position = result.data[0]
            logger.info(f"Created position with ID: {created_position['id']}")
            position = PositionResponse(**created_position)

            if position.challenge_id and position.side and position.creator:
                await self._update_bet_info(position)
                challenge = await get_challenge_service(self.db).get_challenge(position.challenge_id)
                if challenge and challenge.creator != position.creator:
                    await get_notification_service(self.db).notify_followers(
                        position.creator, position.challenge_id, "challenge_joined"
                    )

            return position

        except Exception as e:
            logger.error(f"Error creating position: {e}")
            raise

    async def _update_bet_info(self, position: PositionResponse) -> None:
        """
        Update the parent challenge's bet_info for this position's side:
        - highest_bet: the largest single bet seen so far on that side
        - team_count: running total_bets (count) and total_amount (sum of bets) on that side
        """
        try:
            challenge_service = get_challenge_service(self.db)
            user_service = get_user_service(self.db)

            challenge = await challenge_service.get_challenge(position.challenge_id)
            if not challenge:
                logger.warning(f"Challenge {position.challenge_id} not found; skipping bet_info update")
                return

            user = await user_service.get_user(position.creator)
            if not user:
                logger.warning(f"User {position.creator} not found; skipping bet_info update")
                return

            bet_info = dict(challenge.bet_info or {})
            side_key = position.side.value
            bet = position.bet or 0

            team_count = dict(bet_info.get("team_count") or {})
            side_count = dict(team_count.get(side_key) or {"total_bets": 0, "total_amount": 0})
            side_count["total_bets"] = side_count.get("total_bets", 0) + 1
            side_count["total_amount"] = side_count.get("total_amount", 0) + bet
            team_count[side_key] = side_count
            bet_info["team_count"] = team_count

            highest_bet = dict(bet_info.get("highest_bet") or {})
            existing = highest_bet.get(side_key)
            if existing is None or bet > existing.get("bet", 0):
                highest_bet[side_key] = {
                    "id": user.id,
                    "username": user.username,
                    "profile_image": user.profile_image,
                    "pubkey": user.pubkey,
                    "bet": bet,
                    "twitter_username": user.twitter_username,
                    "user_type": user.user_type,
                }
                bet_info["highest_bet"] = highest_bet

            # For PVP challenges, the challenger's wallet is only known once
            # they join (the creator sets challenge_pda/creator_wallet at
            # creation, but no one records the opponent's wallet anywhere
            # else). Persist it here so the settlement flow can find it once
            # the target is hit.
            metadata = None
            challenger_wallet = None
            if (
                challenge.mode == "PVP"
                and position.creator != challenge.creator
                and user.pubkey
            ):
                onchain_meta = dict((challenge.metadata or {}).get("onchain") or {})
                if not onchain_meta.get("challenger_wallet"):
                    onchain_meta["challenger_wallet"] = user.pubkey
                    metadata = dict(challenge.metadata or {})
                    metadata["onchain"] = onchain_meta
                    challenger_wallet = user.pubkey

            await challenge_service.update_challenge(
                position.challenge_id,
                ChallengeUpdate(bet_info=bet_info, metadata=metadata)
            )

            if challenger_wallet:
                from services.challenge_monitor_service import update_monitored_challenger_wallet
                await update_monitored_challenger_wallet(position.challenge_id, challenger_wallet)

            if challenge.category and bet:
                CategoryService(self.db).increment_volume(challenge.category, bet)
        except Exception as e:
            logger.error(f"Failed to update bet_info for challenge {position.challenge_id}: {e}")

    async def get_position(self, position_id: int) -> Optional[PositionResponse]:
        """
        Get a position by ID.
        
        Args:
            position_id: The position ID to look up
            
        Returns:
            PositionResponse if found, None otherwise
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("id", position_id)
                .execute()
            )
            
            if not result.data:
                return None
            
            return PositionResponse(**result.data[0])
            
        except Exception as e:
            logger.error(f"Error fetching position {position_id}: {e}")
            raise

    async def get_positions_by_challenge(self, challenge_id: int) -> list[PositionResponse]:
        """
        Get all positions for a specific challenge.
        
        Args:
            challenge_id: The challenge ID to filter by
            
        Returns:
            List of PositionResponse objects
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("challenge_id", challenge_id)
                .execute()
            )
            
            return [PositionResponse(**position) for position in result.data]
            
        except Exception as e:
            logger.error(f"Error fetching positions by challenge {challenge_id}: {e}")
            raise

    async def get_positions_by_creator(self, creator_id: int) -> list[PositionResponse]:
        """
        Get all positions created by a specific user.
        
        Args:
            creator_id: The user ID of the creator
            
        Returns:
            List of PositionResponse objects
            
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
            
            return [PositionResponse(**position) for position in result.data]
            
        except Exception as e:
            logger.error(f"Error fetching positions by creator {creator_id}: {e}")
            raise

    async def get_positions_by_side(self, side: Side) -> list[PositionResponse]:
        """
        Get all positions with a specific side.
        
        Args:
            side: The side to filter by
            
        Returns:
            List of PositionResponse objects
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*")
                .eq("side", side.value)
                .execute()
            )
            
            return [PositionResponse(**position) for position in result.data]
            
        except Exception as e:
            logger.error(f"Error fetching positions by side {side}: {e}")
            raise

    async def list_positions(
        self,
        limit: int = 100,
        offset: int = 0,
        creator_id: int | None = None,
    ) -> list[PositionResponse]:
        """
        List positions with pagination.
        
        Args:
            limit: Maximum number of positions to return
            offset: Number of positions to skip
            
        Returns:
            List of PositionResponse objects
            
        Raises:
            Exception: If database operation fails
        """
        try:
            query = self.db.table(self.table).select("*")
            if creator_id is not None:
                query = query.eq("creator", creator_id)
            result = query.range(offset, offset + limit - 1).execute()
            
            return [PositionResponse(**position) for position in result.data]
            
        except Exception as e:
            logger.error(f"Error listing positions: {e}")
            raise

    async def update_position(
        self,
        position_id: int,
        position_data: PositionUpdate
    ) -> Optional[PositionResponse]:
        """
        Update a position by ID.
        
        Args:
            position_id: The position ID to update
            position_data: Updated position data
            
        Returns:
            PositionResponse if updated, None if position not found
            
        Raises:
            Exception: If database operation fails
        """
        try:
            data = position_data.model_dump(exclude_unset=True, exclude_none=True)
            
            if not data:
                logger.warning("No data provided for position update")
                return await self.get_position(position_id)
            
            result = (
                self.db.table(self.table)
                .update(data)
                .eq("id", position_id)
                .execute()
            )
            
            if not result.data:
                return None
            
            updated_position = result.data[0]
            logger.info(f"Updated position with ID: {position_id}")
            return PositionResponse(**updated_position)
            
        except Exception as e:
            logger.error(f"Error updating position {position_id}: {e}")
            raise

    async def delete_position(self, position_id: int) -> bool:
        """
        Delete a position by ID.
        
        Args:
            position_id: The position ID to delete
            
        Returns:
            True if deleted, False if position not found
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .delete()
                .eq("id", position_id)
                .execute()
            )
            
            if result.data:
                logger.info(f"Deleted position with ID: {position_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting position {position_id}: {e}")
            raise

    async def count_positions(self, creator_id: int | None = None) -> int:
        """
        Get total count of positions.
        
        Returns:
            Total number of positions
            
        Raises:
            Exception: If database operation fails
        """
        try:
            query = self.db.table(self.table).select("*", count="exact")
            if creator_id is not None:
                query = query.eq("creator", creator_id)
            result = query.execute()
            
            return result.count or 0
            
        except Exception as e:
            logger.error(f"Error counting positions: {e}")
            raise


def get_position_service(db_client: Client) -> PositionService:
    """
    Factory function to create a PositionService instance.
    
    Args:
        db_client: The Supabase client
        
    Returns:
        PositionService instance
    """
    return PositionService(db_client)
