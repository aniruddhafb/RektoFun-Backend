"""
Challenge service for CRUD operations on the challenge table.
"""

import logging
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from supabase import Client

from models.challenge import (
    ChallengeAvailabilityResponse,
    ChallengeCreate,
    ChallengeUpdate,
    ChallengeResponse,
    ChallengeStatus,
    ResolutionMethod,
)
from services.category_service import CategoryService

logger = logging.getLogger(__name__)

PRICE_DIFFERENCE_RATIO = 0.05
RESOLUTION_DIFFERENCE = timedelta(days=2)
EXPIRY_GRACE = timedelta(hours=3)

# Challenge cards need only these columns. In particular, avoid returning every
# user column (email, referrals, followers, earnings, etc.) for every card.
CHALLENGE_LIST_SELECT = """id,views,statement,ticker,trading_pair,target,initial_bet,pool_size,
resolution_source,metadata,creator,resolution_method,participants,status,mode,result,direction,
expiry,resolution_date,final_price,category,bet_info,created_at,resolved_at,
creator_details:user!challenge_creator_fkey(id,created_at,username,pubkey,profile_image,twitter_username,user_type)""".replace("\n", "")


class DuplicateChallengeError(ValueError):
    def __init__(self, availability: ChallengeAvailabilityResponse):
        super().__init__(availability.reason or "A similar challenge already exists")
        self.availability = availability


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _canonical_statement(value: str | None) -> str:
    # Casing, punctuation and repeated whitespace should not make a statement unique.
    return " ".join(re.findall(r"\w+", (value or "").casefold(), flags=re.UNICODE))


def _challenge_search_filter(value: str) -> str | None:
    """Build a safe PostgREST OR filter using columns that exist in challenge."""
    # Slash is useful for trading pairs (BTC/USDC) and is safe in filter values.
    term = re.sub(r"[^\w\s/]", " ", value.strip(), flags=re.UNICODE)
    term = " ".join(term.split())
    if not term:
        return None
    return (
        f"statement.ilike.%{term}%,ticker.ilike.%{term}%,"
        f"trading_pair.ilike.%{term}%,category.ilike.%{term}%"
    )


def _resolution_time(challenge: dict) -> datetime | None:
    composer = (challenge.get("metadata") or {}).get("composer") or {}
    value = composer.get("resolves_at")
    if value:
        try:
            return _utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
        except (TypeError, ValueError):
            pass
    value = challenge.get("resolution_date")
    if not value:
        return None
    try:
        parsed = date.fromisoformat(str(value))
        return datetime.combine(parsed, time.min, tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


class ChallengeService:
    """Service for managing challenge operations with Supabase"""

    def __init__(self, db_client: Client):
        self.db = db_client
        self.table = "challenge"
        self._visibility_columns_available: bool | None = None

    def has_visibility_columns(self) -> bool:
        """Allow old deployments to keep serving public challenges pre-migration."""
        if self._visibility_columns_available is None:
            try:
                self.db.table(self.table).select("visibility").limit(1).execute()
                self._visibility_columns_available = True
            except Exception:
                self._visibility_columns_available = False
                logger.warning(
                    "Direct challenge columns are unavailable; run migration 003_add_direct_challenges.sql"
                )
        return self._visibility_columns_available

    def with_category_images(self, challenges: list[dict]) -> list[dict]:
        """Attach current display profiles and configured artwork to API rows."""
        profile_ids = {
            entry.get("id")
            for challenge in challenges
            for entry in ((challenge.get("bet_info") or {}).get("highest_bet") or {}).values()
            if isinstance(entry, dict) and entry.get("id") is not None
        }
        profile_ids.update(
            challenge.get("challenged_user_id")
            for challenge in challenges
            if challenge.get("challenged_user_id") is not None
        )
        if profile_ids:
            profiles = self.db.table("user").select(
                "id,created_at,username,pubkey,profile_image,twitter_username,user_type"
            ).in_("id", list(profile_ids)).execute().data or []
            profiles_by_id = {str(profile["id"]): profile for profile in profiles}
            for challenge in challenges:
                challenged_user = profiles_by_id.get(str(challenge.get("challenged_user_id")))
                if challenged_user:
                    challenge["challenged_user_details"] = challenged_user
                highest_bets = ((challenge.get("bet_info") or {}).get("highest_bet") or {})
                for side, snapshot in highest_bets.items():
                    if not isinstance(snapshot, dict):
                        continue
                    current = profiles_by_id.get(str(snapshot.get("id")))
                    if current:
                        # Keep bet-specific data but never serve stale identity
                        # fields captured when the position was first placed.
                        highest_bets[side] = {**snapshot, **current}

        category_names = {
            str(value).strip().casefold()
            for challenge in challenges
            for value in (
                challenge.get("category"),
                challenge.get("trading_pair"),
                challenge.get("ticker"),
            )
            if value
        }
        if not category_names:
            return challenges

        categories = self.db.table("category").select(
            "category,parent_category,metadata"
        ).execute().data or []
        category_by_name = {
            str(category.get("category") or "").strip().casefold(): category
            for category in categories
        }

        def base_asset(value: object) -> str:
            name = str(value or "").strip().casefold()
            return name.split("/", 1)[0].strip()

        category_by_base_asset = {
            base_asset(category.get("category")): category
            for category in categories
            if "/" in str(category.get("category") or "")
        }

        def image_for(category: dict | None) -> str | None:
            metadata = (category or {}).get("metadata") or {}
            image = metadata.get("image_url") or metadata.get("category_image")
            return image if isinstance(image, str) and image.strip() else None

        for challenge in challenges:
            # A broad challenge category such as "Crypto" may have a more
            # specific category row named after its pair, e.g. "DOGE/USDC".
            trading_pair = challenge.get("trading_pair")
            asset_name = base_asset(trading_pair) or base_asset(challenge.get("ticker"))
            candidate_names = (
                trading_pair,
                challenge.get("ticker"),
            )
            category = None
            image = None
            for candidate_name in candidate_names:
                candidate = category_by_name.get(
                    str(candidate_name or "").strip().casefold()
                )
                candidate_image = image_for(candidate)
                if candidate_image:
                    category = candidate
                    image = candidate_image
                    break
                if category is None and candidate:
                    category = candidate
            if not image and asset_name:
                asset_category = category_by_base_asset.get(asset_name)
                asset_image = image_for(asset_category)
                if asset_category:
                    category = asset_category
                if asset_image:
                    image = asset_image
            if not image:
                broad_category = category_by_name.get(
                    str(challenge.get("category") or "").strip().casefold()
                )
                broad_image = image_for(broad_category)
                if broad_category:
                    category = broad_category
                if broad_image:
                    image = broad_image
            visited: set[str] = set()
            while not image and category and category.get("parent_category"):
                parent_name = str(category["parent_category"]).strip().casefold()
                if parent_name in visited:
                    break
                visited.add(parent_name)
                category = category_by_name.get(parent_name)
                image = image_for(category)
            if image:
                challenge["category_image"] = image
        return challenges

    async def check_availability(self, challenge_data: ChallengeCreate) -> ChallengeAvailabilityResponse:
        """Apply duplicate rules against currently active challenges."""
        now = datetime.now(timezone.utc)
        result = (
            self.db.table(self.table)
            .select("id,statement,ticker,trading_pair,target,resolution_method,resolution_source,status,expiry,resolution_date,metadata")
            .in_("status", [ChallengeStatus.OPEN.value, ChallengeStatus.PENDING_RESOLUTION.value])
            .execute()
        )
        active = []
        for item in result.data or []:
            try:
                expiry = _utc(datetime.fromisoformat(str(item.get("expiry")).replace("Z", "+00:00")))
            except (TypeError, ValueError):
                continue
            if expiry > now:
                active.append((item, expiry))

        is_price = challenge_data.resolution_method == ResolutionMethod.PRICE_FEED or (
            str(challenge_data.resolution_source or "").upper() == "PRICE_FEED"
        )
        conflicts: list[tuple[dict, datetime]] = []

        if is_price:
            asset = (challenge_data.ticker or challenge_data.trading_pair or "").split("/", 1)[0].strip().upper()
            proposed_target = challenge_data.target
            proposed_resolution = _resolution_time(challenge_data.model_dump(mode="json"))
            for existing, expiry in active:
                existing_asset = (existing.get("ticker") or existing.get("trading_pair") or "").split("/", 1)[0].strip().upper()
                if not asset or existing_asset != asset or expiry - now <= EXPIRY_GRACE:
                    continue
                existing_target = existing.get("target")
                price_is_different = (
                    proposed_target is not None
                    and existing_target is not None
                    and float(existing_target) != 0
                    and abs(float(proposed_target) - float(existing_target)) / abs(float(existing_target)) >= PRICE_DIFFERENCE_RATIO
                )
                existing_resolution = _resolution_time(existing)
                time_is_different = (
                    proposed_resolution is not None
                    and existing_resolution is not None
                    and abs(proposed_resolution - existing_resolution) >= RESOLUTION_DIFFERENCE
                )
                if not price_is_different and not time_is_different:
                    conflicts.append((existing, expiry))
            reason = "A similar price challenge already exists for this asset. Change the target by at least 5% or the resolution time by at least 2 days."
            available_at = max((expiry - EXPIRY_GRACE for _, expiry in conflicts), default=None)
        else:
            statement = _canonical_statement(challenge_data.statement)
            conflicts = [(item, expiry) for item, expiry in active if statement and _canonical_statement(item.get("statement")) == statement]
            reason = "The same statement challenge already exists."
            available_at = max((expiry for _, expiry in conflicts), default=None)

        return ChallengeAvailabilityResponse(
            allowed=not conflicts,
            reason=reason if conflicts else None,
            available_at=available_at,
            conflicting_challenge_ids=[int(item["id"]) for item, _ in conflicts],
        )

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
            availability = await self.check_availability(challenge_data)
            if not availability.allowed:
                raise DuplicateChallengeError(availability)
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

            return ChallengeResponse(**self.with_category_images([created_challenge])[0])
            
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
            
            return ChallengeResponse(**self.with_category_images([result.data[0]])[0])
            
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
        creator_id: int | None = None,
        open_first: bool = False,
        status_filter: ChallengeStatus | None = None,
        expiring_soon: bool = False,
        search: str | None = None,
        joinable: bool = False,
        visibility_filter: str | None = None,
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
            has_visibility_columns = self.has_visibility_columns()
            list_select = CHALLENGE_LIST_SELECT
            if has_visibility_columns:
                list_select = f"{list_select},visibility,challenged_user_id,invitation_status"

            def apply_visibility_scope(query):
                if not has_visibility_columns:
                    return query
                if visibility_filter:
                    return query.eq("visibility", visibility_filter)
                # Pending direct invitations stay private. Once accepted, the
                # battle is live and becomes viewable in public discovery.
                if creator_id is None:
                    return query.or_(
                        "visibility.eq.PUBLIC,and(visibility.eq.DIRECT,invitation_status.eq.ACCEPTED)"
                    )
                return query

            def build_query():
                query = apply_visibility_scope(
                    self.db.table(self.table).select(list_select)
                )
                if resolution_source:
                    query = query.ilike("resolution_source", resolution_source)
                if creator_id is not None:
                    query = query.eq("creator", creator_id)
                if status_filter is not None:
                    query = query.eq("status", status_filter.value)
                if expiring_soon:
                    query = query.eq("status", ChallengeStatus.OPEN.value).gt(
                        "expiry", datetime.now(timezone.utc).isoformat()
                    )
                if joinable:
                    query = query.eq("status", ChallengeStatus.OPEN.value).gt(
                        "expiry", datetime.now(timezone.utc).isoformat()
                    ).or_("mode.neq.PVP,bet_info->highest_bet->TEAM_B.is.null")
                if search:
                    search_filter = _challenge_search_filter(search)
                    if search_filter:
                        query = query.or_(search_filter)
                return query

            if not open_first or status_filter is not None or expiring_soon or joinable:
                query = build_query()
                order_column = "expiry" if expiring_soon else "created_at"
                result = query.order(order_column, desc=not expiring_soon).range(
                    offset, offset + limit - 1
                ).execute()
                return [ChallengeResponse(**challenge) for challenge in self.with_category_images(result.data or [])]

            # Preserve status priority across page boundaries. Challenges within
            # each status are ordered newest first.
            status_order = [
                ChallengeStatus.OPEN,
                ChallengeStatus.PENDING_RESOLUTION,
                ChallengeStatus.RESOLVED,
                ChallengeStatus.EXPIRED,
                ChallengeStatus.CANCELLED,
            ]
            rows: list[dict] = []
            skipped = 0
            for challenge_status in status_order:
                count_query = apply_visibility_scope(
                    self.db.table(self.table).select("id", count="exact")
                )
                if resolution_source:
                    count_query = count_query.ilike("resolution_source", resolution_source)
                if creator_id is not None:
                    count_query = count_query.eq("creator", creator_id)
                if search:
                    search_filter = _challenge_search_filter(search)
                    if search_filter:
                        count_query = count_query.or_(search_filter)
                count_result = count_query.eq("status", challenge_status.value).limit(1).execute()
                status_count = count_result.count or 0

                if offset >= skipped + status_count:
                    skipped += status_count
                    continue

                group_offset = max(0, offset - skipped)
                group_limit = min(limit - len(rows), status_count - group_offset)
                group_result = build_query().eq("status", challenge_status.value).order(
                    "created_at", desc=True
                ).range(group_offset, group_offset + group_limit - 1).execute()
                rows.extend(group_result.data or [])
                skipped += status_count
                if len(rows) >= limit:
                    break

            return [ChallengeResponse(**challenge) for challenge in self.with_category_images(rows)]

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

    async def count_challenges(
        self,
        resolution_source: str | None = None,
        creator_id: int | None = None,
        status_filter: ChallengeStatus | None = None,
        expiring_soon: bool = False,
        search: str | None = None,
        joinable: bool = False,
        visibility_filter: str | None = None,
    ) -> int:
        """
        Get total count of challenges.
        
        Returns:
            Total number of challenges
            
        Raises:
            Exception: If database operation fails
        """
        try:
            has_visibility_columns = self.has_visibility_columns()
            query = self.db.table(self.table).select("*", count="exact")
            if visibility_filter and has_visibility_columns:
                query = query.eq("visibility", visibility_filter)
            elif has_visibility_columns and creator_id is None:
                query = query.or_(
                    "visibility.eq.PUBLIC,and(visibility.eq.DIRECT,invitation_status.eq.ACCEPTED)"
                )
            if resolution_source:
                query = query.ilike("resolution_source", resolution_source)
            if creator_id is not None:
                query = query.eq("creator", creator_id)
            if status_filter is not None:
                query = query.eq("status", status_filter.value)
            if expiring_soon:
                query = query.eq("status", ChallengeStatus.OPEN.value).gt(
                    "expiry", datetime.now(timezone.utc).isoformat()
                )
            if joinable:
                query = query.eq("status", ChallengeStatus.OPEN.value).gt(
                    "expiry", datetime.now(timezone.utc).isoformat()
                ).or_("mode.neq.PVP,bet_info->highest_bet->TEAM_B.is.null")
            if search:
                search_filter = _challenge_search_filter(search)
                if search_filter:
                    query = query.or_(search_filter)
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
                update_data["final_price"] = price_to_use
            if new_status == ChallengeStatus.RESOLVED:
                update_data["resolved_at"] = datetime.now(timezone.utc).isoformat()
                if price_to_use is not None and challenge.target is not None:
                    direction = str(challenge.direction or "").upper()
                    creator_wins = price_to_use >= challenge.target if direction.endswith("UP") else price_to_use <= challenge.target
                    update_data["result"] = "TEAM_A" if creator_wins else "TEAM_B"
            
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
            if new_status == ChallengeStatus.RESOLVED:
                from services.notification_service import get_notification_service
                await get_notification_service(self.db).notify_pvp_winner(updated_challenge)
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
