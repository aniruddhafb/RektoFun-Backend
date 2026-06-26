"""
Position service for CRUD operations on the position table.
"""

import logging
from typing import Optional

from supabase import Client

from models.position import PositionCreate, PositionUpdate, PositionResponse, Side

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
            return PositionResponse(**created_position)
            
        except Exception as e:
            logger.error(f"Error creating position: {e}")
            raise

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
        offset: int = 0
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
            result = (
                self.db.table(self.table)
                .select("*")
                .range(offset, offset + limit - 1)
                .execute()
            )
            
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

    async def count_positions(self) -> int:
        """
        Get total count of positions.
        
        Returns:
            Total number of positions
            
        Raises:
            Exception: If database operation fails
        """
        try:
            result = (
                self.db.table(self.table)
                .select("*", count="exact")
                .execute()
            )
            
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