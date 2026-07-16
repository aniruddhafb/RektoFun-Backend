"""
Challenge Monitor Service for real-time price tracking and status updates.

This service monitors active challenges via WebSocket connections to Binance
and updates challenge statuses when:
1. Target prices are reached (immediate resolution)
2. Resolution date is reached (scheduled resolution)
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, date

import aiohttp

from services.binance_ws_client import (
    get_binance_ws_client,
    PriceUpdate,
    start_binance_ws_client,
    stop_binance_ws_client,
)
from services.challenge_service import ChallengeService
from services.category_service import CategoryService
from services.database import get_db_client
from models.challenge import ChallengeStatus, ChallengeBase

logger = logging.getLogger(__name__)

CRYPTO_PARENT_CATEGORY = "Crypto"


class ChallengeMonitorService:
    """
    Service that monitors active challenges and updates their status
    when target prices are hit via real-time WebSocket price feeds
    or when resolution_date is reached.
    
    IMPORTANT: Uses symbol-to-challenges mapping to support multiple challenges
    sharing the same trading pair. Only unsubscribes from WebSocket when
    the last challenge for a symbol is removed.
    """

    def __init__(self):
        self._active_challenges: Dict[int, dict] = {}
        # Map: symbol -> set of challenge_ids using that symbol
        self._symbol_challenges: Dict[str, Set[int]] = {}
        self._lock = asyncio.Lock()
        self._challenge_service = None
        self._category_service = None
        self._ws_client = None

    def _get_challenge_service(self) -> ChallengeService:
        """Lazy initialization of challenge service"""
        if self._challenge_service is None:
            db_client = get_db_client()
            self._challenge_service = ChallengeService(db_client)
        return self._challenge_service

    def _get_category_service(self) -> CategoryService:
        """Lazy initialization of category service"""
        if self._category_service is None:
            self._category_service = CategoryService(get_db_client())
        return self._category_service

    def _is_crypto_category(self, category_name: Optional[str]) -> bool:
        """
        Check whether a challenge's category is the "Crypto" parent category
        itself or a child of it. Only such challenges should be tracked on
        the Binance WebSocket (e.g. sports categories reuse the same
        price-target monitoring fields with non-Binance symbols like team
        names).
        """
        if not category_name:
            return False
        if category_name == CRYPTO_PARENT_CATEGORY:
            return True
        category = self._get_category_service().get_category_by_name(category_name)
        if not category:
            return False
        return category.get("parent_category") == CRYPTO_PARENT_CATEGORY

    async def start(self):
        """Start the challenge monitor service"""
        logger.info("Starting Challenge Monitor Service...")
        
        # Start the WebSocket client
        await start_binance_ws_client()
        self._ws_client = get_binance_ws_client()
        
        # Load and monitor existing active challenges
        await self._load_active_challenges()
        
        logger.info("Challenge Monitor Service started")

    async def stop(self):
        """Stop the challenge monitor service"""
        logger.info("Stopping Challenge Monitor Service...")
        
        async with self._lock:
            self._active_challenges.clear()
            self._symbol_challenges.clear()
        
        await stop_binance_ws_client()
        self._ws_client = None
        logger.info("Challenge Monitor Service stopped")

    async def _load_active_challenges(self):
        """Load OPEN challenges from database and start monitoring them"""
        try:
            service = self._get_challenge_service()
            challenges = await service.get_active_challenges_raw()
            
            for challenge in challenges:
                await self._monitor_challenge(challenge)
                
            logger.info(f"Loaded and monitoring {len(challenges)} active challenges")
            
        except Exception as e:
            logger.error(f"Error loading active challenges: {e}")

    async def _monitor_challenge(self, challenge: ChallengeBase):
        """
        Start monitoring a challenge for price targets.
        Only monitors challenges that haven't reached their resolution_date yet.
        
        Args:
            challenge: Challenge data dictionary
        """
        challenge_id = challenge["id"]
        ticker = challenge["ticker"]
        target = challenge["target"]
        direction = challenge["direction"]
        resolution_date = challenge.get("resolution_date")
        category = challenge.get("category")

        # Only track assets on Binance for challenges under the "Crypto" parent category
        if not self._is_crypto_category(category):
            logger.info(
                f"Challenge {challenge_id} category '{category}' is not under parent "
                f"'{CRYPTO_PARENT_CATEGORY}', skipping Binance monitoring"
            )
            return

        # Check if challenge has already reached resolution_date
        if resolution_date:
            res_date = resolution_date if isinstance(resolution_date, date) else datetime.fromisoformat(resolution_date).date()
            if res_date < date.today():
                logger.info(f"Challenge {challenge_id} resolution_date {res_date} has passed, skipping monitoring")
                return
        
        # Get trading pair from database and normalize to Binance symbol format
        # e.g. "BTC/USDC" -> "BTCUSDC"
        raw_trading_pair = challenge.get("trading_pair")
        symbol = raw_trading_pair.replace("/", "").upper() if raw_trading_pair else None

        onchain_meta = (challenge.get("metadata") or {}).get("onchain") or {}

        async with self._lock:
            self._active_challenges[challenge_id] = {
                "challenge_id": challenge_id,
                "ticker": ticker,
                "trading_pair": symbol,
                "raw_trading_pair": raw_trading_pair,
                "target": target,
                "direction": direction,
                "resolution_date": resolution_date,
                "created_at": challenge.get("created_at"),
                "mode": challenge.get("mode"),
                "challenge_pda": onchain_meta.get("challenge_pda"),
                "creator_wallet": onchain_meta.get("creator_wallet"),
                "challenger_wallet": onchain_meta.get("challenger_wallet"),
                "pool_size": challenge.get("pool_size"),
            }
            
            # Track which challenges use this symbol
            if symbol:
                if symbol not in self._symbol_challenges:
                    self._symbol_challenges[symbol] = set()
                self._symbol_challenges[symbol].add(challenge_id)
                
                # Subscribe only if this is the first challenge for this symbol
                is_first_for_symbol = len(self._symbol_challenges[symbol]) == 1
            else:
                is_first_for_symbol = False
        
        # Subscribe to price updates only for new symbols
        if symbol and is_first_for_symbol:
            logger.info(f"Subscribing to price updates for symbol: {symbol}")
            await self._ws_client.subscribe(
                symbol=symbol,
                callback=lambda price_update, sym=symbol: self._on_price_update(sym, price_update)
            )
        
        logger.info(f"Started monitoring challenge {challenge_id}: {symbol} -> {target} ({direction})")

    async def _on_price_update(self, symbol: str, price_update: PriceUpdate):
        """
        Handle price update from WebSocket for a symbol.
        Fans out to all challenges using this symbol.
        
        Args:
            symbol: The trading pair symbol
            price_update: Price update data
        """
        try:
            async with self._lock:
                # Get all challenges using this symbol
                challenge_ids = self._symbol_challenges.get(symbol, set()).copy()
            
            # Process each challenge in parallel
            tasks = [
                self._process_price_update_for_challenge(cid, price_update)
                for cid in challenge_ids
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Error processing price update for {symbol}: {e}")

    async def _process_price_update_for_challenge(self, challenge_id: int, price_update: PriceUpdate):
        """
        Check if a price update hits the target for a specific challenge.
        
        Args:
            challenge_id: The challenge being monitored
            price_update: Price update data
        """
        try:
            async with self._lock:
                challenge_data = self._active_challenges.get(challenge_id)
                # logger.info(f"challenge data log: {challenge_data}")
                if not challenge_data:
                    return  # Challenge no longer active
                
                target = challenge_data["target"]
                direction = challenge_data["direction"]
                current_price = price_update.price
            # Check if target is hit
            target_hit = False
            
            if direction == "UP":
                # Target hit when price goes above or equals target
                if current_price >= target:
                    target_hit = True
            else:  # direction == "DOWN"
                # Target hit when price goes below or equals target
                if current_price <= target:
                    target_hit = True
            
            if target_hit:
                logger.info(f"\033[32mTarget hit for challenge {challenge_id}: "
                          f"price={current_price}, target={target}\033[0m")
                await self._resolve_challenge_immediately(challenge_id, current_price)
                
        except Exception as e:
            logger.error(f"Error processing price update for challenge {challenge_id}: {e}")

    async def _resolve_challenge_immediately(self, challenge_id: int, hit_price: float):
        """
        Resolve a challenge immediately when target is hit.
        Sets status to RESOLVED with final_price.
        
        Args:
            challenge_id: The challenge to resolve
            hit_price: The price at which target was hit
        """
        challenge_data = None
        symbol = None
        should_unsubscribe = False
        try:
            async with self._lock:
                challenge_data = self._active_challenges.pop(challenge_id, None)
                if not challenge_data:
                    return  # Already completed or removed

                symbol = challenge_data.get("trading_pair")
                if symbol:
                    # Remove from symbol mapping
                    if symbol in self._symbol_challenges:
                        self._symbol_challenges[symbol].discard(challenge_id)
                        # Check if this was the last challenge for this symbol
                        should_unsubscribe = len(self._symbol_challenges[symbol]) == 0
                        if should_unsubscribe:
                            del self._symbol_challenges[symbol]

            # Update challenge status in database. This is the only step that can
            # legitimately be retried — everything after it is best-effort against
            # an already-committed RESOLVED row, so it must not trigger a re-add.
            service = self._get_challenge_service()
            resolved_challenge = await service.update_challenge_status(
                challenge_id=challenge_id,
                new_status=ChallengeStatus.RESOLVED,
                final_price=hit_price
            )
        except ValueError as e:
            # Invalid transition (e.g. already RESOLVED via another path) is
            # terminal, not transient — retrying will never succeed, so drop
            # the challenge from monitoring instead of re-adding it.
            logger.error(f"Error resolving challenge {challenge_id}: {e}")
            return
        except Exception as e:
            logger.error(f"Error resolving challenge {challenge_id}: {e}")
            # Re-add to active challenges since the DB update itself failed
            if challenge_data:
                async with self._lock:
                    self._active_challenges[challenge_id] = challenge_data
                    if symbol:
                        if symbol not in self._symbol_challenges:
                            self._symbol_challenges[symbol] = set()
                        self._symbol_challenges[symbol].add(challenge_id)
            return

        # From here on, the DB row is already RESOLVED — settlement, unsubscribe,
        # and logging are best-effort and must never re-queue the challenge.
        try:
            # Settle on-chain — creator_wins is always True when target is hit
            # (hitting the target validates the creator's direction prediction).
            # Read onchain fields from the row just fetched from the DB rather
            # than the in-memory cache: challenger_wallet is only cached at
            # monitor-start time (creation), and set_challenger_wallet() only
            # patches the cache in the process that happened to handle the
            # join request — under Mangum/serverless each invocation can be a
            # separate process, so that update may never reach the instance
            # that ends up resolving the challenge. The freshly-updated DB row
            # is the source of truth.
            fresh_onchain = (getattr(resolved_challenge, "metadata", None) or {}).get("onchain") or {}
            challenge_pda = fresh_onchain.get("challenge_pda") or challenge_data.get("challenge_pda")
            creator_wallet = fresh_onchain.get("creator_wallet") or challenge_data.get("creator_wallet")
            challenger_wallet = fresh_onchain.get("challenger_wallet") or challenge_data.get("challenger_wallet")
            mode = (getattr(resolved_challenge, "mode", None) or challenge_data.get("mode") or "PVP")

            if mode == "PVP" and not challenger_wallet:
                # PVP challenge with no challenger is still Open on-chain — the
                # settle_challenge instruction requires Active status, so skip.
                logger.info(
                    f"Challenge {challenge_id} is PVP with no challenger — "
                    f"skipping on-chain settlement (no pot to distribute)"
                )
            elif challenge_pda and creator_wallet:
                await self._call_settlement_service(
                    challenge_id=challenge_id,
                    challenge_pda=challenge_pda,
                    creator_wallet=creator_wallet,
                    challenger_wallet=challenger_wallet,
                    winner_wallet=creator_wallet,
                    creator_wins=True,
                    mode=mode,
                )
            else:
                logger.warning(
                    f"Challenge {challenge_id} missing challenge_pda or creator_wallet — "
                    f"skipping on-chain settlement"
                )

            # Unsubscribe only if this was the last challenge for this symbol
            if symbol and should_unsubscribe and self._ws_client:
                await self._ws_client.unsubscribe(symbol)
                logger.info(f"Unsubscribed from {symbol} - no more challenges using it")

            logger.info(f"Challenge {challenge_id} resolved immediately at price {hit_price}")

        except Exception as e:
            logger.error(f"Error settling challenge {challenge_id} on-chain after DB resolve: {e}")

    async def _call_settlement_service(
        self,
        challenge_id: int,
        challenge_pda: str,
        creator_wallet: str,
        challenger_wallet: str | None,
        winner_wallet: str,
        creator_wins: bool,
        mode: str,
    ) -> bool:
        """
        POST to the settlement service to settle the challenge on-chain.
        Failures are logged but do NOT affect the DB status.
        """
        from config import get_settings
        settings = get_settings()
        settlement_url = settings.settlement_service_url.rstrip("/")
        if not settlement_url:
            logger.warning(
                f"SETTLEMENT_API not configured — skipping on-chain settlement for challenge {challenge_id}"
            )
            return False
        settlement_secret = settings.settlement_api_secret
        if not settlement_secret:
            logger.warning(
                f"SETTLEMENT_API_SECRET not configured — skipping on-chain settlement for "
                f"challenge {challenge_id} rather than calling the settlement service unauthenticated"
            )
            return False

        # TEAM (mode "TEAM" or "MULTI"): settlement API expects creator for both
        # challenger and winner; individual winners claim via claim_winnings separately.
        is_team = mode != "PVP"
        challenger_pubkey = creator_wallet if is_team else (challenger_wallet or creator_wallet)
        winner_pubkey = creator_wallet if is_team else winner_wallet

        payload = {
            "challengePda": challenge_pda,
            "creatorPubkey": creator_wallet,
            "challengerPubkey": challenger_pubkey,
            "winnerPubkey": winner_pubkey,
            "creatorWins": creator_wins,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{settlement_url}/settle-challenge",
                    json=payload,
                    headers={"x-settlement-api-key": settlement_secret},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    body = await resp.json()
                    if resp.status == 200 and body.get("success"):
                        logger.info(
                            f"On-chain settlement succeeded for challenge {challenge_id}: "
                            f"tx={body.get('signature')}"
                        )
                        if mode == "PVP":
                            from services.referral_service import ReferralService
                            challenge = self._get_challenge_service().db.table("challenge").select("pool_size").eq("id", challenge_id).single().execute()
                            pool_size = (challenge.data or {}).get("pool_size")
                            referral_service = ReferralService(self._get_challenge_service().db)
                            referral_service.credit_pvp_participant(
                                challenge_id, creator_wallet, pool_size
                            )
                            if challenger_wallet:
                                referral_service.credit_pvp_participant(
                                    challenge_id, challenger_wallet, pool_size
                                )
                        return True
                    else:
                        logger.error(
                            f"Settlement service rejected challenge {challenge_id}: "
                            f"status={resp.status} body={body}"
                        )
        except Exception as exc:
            logger.error(f"Settlement service call failed for challenge {challenge_id}: {exc}")
        return False

    async def handle_expired_challenges(self):
        """
        Handle challenges where expiry date has passed.
        When expiry is reached:
        - No new bets can be placed (this is handled by frontend/API validation)
        - Challenge continues monitoring until resolution_date
        
        This method can be called periodically to log or perform any
        expiry-related cleanup if needed in the future.
        """
        try:
            service = self._get_challenge_service()
            from datetime import datetime, timezone

            # Get challenges where expiry has passed but still OPEN
            result = (
                service.db.table("challenge")
                .select("*")
                .eq("status", ChallengeStatus.OPEN.value)
                .lt("expiry", datetime.now(timezone.utc).isoformat())
                .execute()
            )
            
            expired_challenges = result.data or []
            for challenge in expired_challenges:
                challenge_id = challenge["id"]
                expiry = challenge.get("expiry")
                resolution_date = challenge.get("resolution_date")
                logger.info(f"Challenge {challenge_id} betting closed (expired {expiry}), "
                          f"continues monitoring until resolution_date {resolution_date}")
                
        except Exception as e:
            logger.error(f"Error handling expired challenges: {e}")

    async def resolve_challenges_by_date(self):
        """
        Resolve all OPEN challenges where resolution_date has been reached.
        This fetches the current price and resolves the challenge.
        
        This method should be called on the resolution_date (e.g., via pg_cron daily).
        Challenges that didn't hit their target will be resolved with the current price.
        """
        try:
            from datetime import date
            
            service = self._get_challenge_service()
            
            # Get OPEN and RESOLVED challenges where resolution_date <= today.
            # RESOLVED challenges were resolved early (target hit); they still
            # need on-chain settlement called now that resolves_at has been reached.
            result = (
                service.db.table("challenge")
                .select("*")
                .in_("status", [ChallengeStatus.OPEN.value, ChallengeStatus.RESOLVED.value])
                .lte("resolution_date", date.today().isoformat())
                .execute()
            )
            
            challenges_to_resolve = result.data or []
            logger.info(f"Found {len(challenges_to_resolve)} challenges ready for resolution")
            
            # Get unique normalized symbols for price fetching
            # Normalize trading_pair from DB (e.g. "BTC/USDC" -> "BTCUSDC") to match Binance format
            raw_to_symbol = {
                c["trading_pair"]: c["trading_pair"].replace("/", "").upper()
                for c in challenges_to_resolve
                if c.get("trading_pair")
            }
            symbols = list(set(raw_to_symbol.values()))

            # Fetch current prices for all symbols
            current_prices = {}
            for symbol in symbols:
                try:
                    price = await self._get_current_price(symbol)
                    if price:
                        current_prices[symbol] = price
                except Exception as e:
                    logger.error(f"Error fetching price for {symbol}: {e}")
            
            # Resolve / settle each challenge
            for challenge in challenges_to_resolve:
                challenge_id = challenge["id"]
                challenge_status = challenge.get("status")
                raw_trading_pair = challenge.get("trading_pair")
                symbol = raw_to_symbol.get(raw_trading_pair) if raw_trading_pair else None

                # Stop monitoring this challenge (only relevant for OPEN ones still in memory).
                # RESOLVED challenges were already removed from _active_challenges at
                # _resolve_challenge_immediately time, so pop() is a safe no-op for them.
                should_unsubscribe = False
                async with self._lock:
                    challenge_data = self._active_challenges.pop(challenge_id, None)
                    if challenge_data and symbol:
                        if symbol in self._symbol_challenges:
                            self._symbol_challenges[symbol].discard(challenge_id)
                            if len(self._symbol_challenges[symbol]) == 0:
                                should_unsubscribe = True
                                del self._symbol_challenges[symbol]

                if challenge_status == ChallengeStatus.OPEN.value:
                    # Target was never hit — resolve with current market price
                    final_price = current_prices.get(symbol)
                    if final_price is None:
                        logger.warning(f"No current price for {symbol}, challenge {challenge_id} will remain OPEN")
                        # Re-add to monitoring only for OPEN challenges
                        if challenge_data:
                            async with self._lock:
                                self._active_challenges[challenge_id] = challenge_data
                                if symbol:
                                    if symbol not in self._symbol_challenges:
                                        self._symbol_challenges[symbol] = set()
                                    self._symbol_challenges[symbol].add(challenge_id)
                        continue

                    try:
                        await service.update_challenge_status(
                            challenge_id=challenge_id,
                            new_status=ChallengeStatus.RESOLVED,
                            final_price=final_price
                        )
                        logger.info(f"Resolved challenge {challenge_id} on resolution_date with final_price={final_price}")
                    except Exception as e:
                        logger.error(f"Error resolving challenge {challenge_id}: {e}")
                        # Re-add to monitoring on DB failure
                        if challenge_data:
                            async with self._lock:
                                self._active_challenges[challenge_id] = challenge_data
                                if symbol:
                                    if symbol not in self._symbol_challenges:
                                        self._symbol_challenges[symbol] = set()
                                    self._symbol_challenges[symbol].add(challenge_id)
                        continue

                    # Determine winner from direction vs final price
                    direction = challenge.get("direction", "")
                    target = challenge.get("target", 0)
                    creator_wins = (final_price >= target) if direction == "UP" else (final_price <= target)

                else:
                    # Already RESOLVED — target was hit early; use stored final_price
                    final_price = challenge.get("final_price")
                    if final_price is None:
                        logger.warning(f"Challenge {challenge_id} is RESOLVED but missing final_price, skipping settlement")
                        continue
                    # Creator's direction was validated when target was hit
                    creator_wins = True

                # Unsubscribe from WebSocket if this was the last challenge for the symbol
                if should_unsubscribe and symbol:
                    await self._ws_client.unsubscribe(symbol)
                    logger.info(f"Unsubscribed from {symbol} - no more challenges using it")

                # Settle on-chain via the settlement service
                onchain_meta = (challenge.get("metadata") or {}).get("onchain") or {}
                challenge_pda = onchain_meta.get("challenge_pda")
                creator_wallet = onchain_meta.get("creator_wallet")
                challenger_wallet = onchain_meta.get("challenger_wallet")
                mode = challenge.get("mode") or "PVP"
                winner_wallet = creator_wallet if creator_wins else (challenger_wallet or creator_wallet)

                if mode == "PVP" and not challenger_wallet:
                    # PVP challenge with no challenger is still Open on-chain — cannot settle.
                    logger.info(
                        f"Challenge {challenge_id} is PVP with no challenger — "
                        f"skipping on-chain settlement (no pot to distribute)"
                    )
                elif challenge_pda and creator_wallet:
                    await self._call_settlement_service(
                        challenge_id=challenge_id,
                        challenge_pda=challenge_pda,
                        creator_wallet=creator_wallet,
                        challenger_wallet=challenger_wallet,
                        winner_wallet=winner_wallet,
                        creator_wins=creator_wins,
                        mode=mode,
                    )
                else:
                    logger.warning(
                        f"Challenge {challenge_id} missing challenge_pda or creator_wallet — "
                        f"skipping on-chain settlement"
                    )
                    
        except Exception as e:
            logger.error(f"Error in resolve_challenges_by_date: {e}")

    async def resolve_challenge_by_id(
        self,
        challenge_id: int,
        creator_wins: bool | None = None,
        final_price: float | None = None,
    ) -> dict:
        """Resolve and settle one due challenge from the admin workflow."""
        from datetime import date, datetime, timezone

        service = self._get_challenge_service()
        challenge = await service.get_challenge(challenge_id)
        if not challenge:
            raise ValueError("Challenge not found")
        if challenge.status not in (
            ChallengeStatus.OPEN.value,
            ChallengeStatus.RESOLVED.value,
        ):
            raise ValueError(f"Challenge status {challenge.status} cannot be resolved")
        if not challenge.resolution_date or challenge.resolution_date > date.today():
            raise ValueError("Challenge resolution date has not been reached")

        bet_info = challenge.bet_info or {}
        team_b_count = (
            (bet_info.get("team_count") or {}).get("TEAM_B") or {}
        ).get("total_bets", 0)
        team_b_highest_bet = (bet_info.get("highest_bet") or {}).get("TEAM_B")
        onchain_metadata = (challenge.metadata or {}).get("onchain") or {}
        if not team_b_count and not team_b_highest_bet and not onchain_metadata.get("challenger_wallet"):
            raise ValueError("Challenge cannot be resolved because no opponent joined")

        resolution_method = str(challenge.resolution_method or "").upper()
        resolution_source = str(challenge.resolution_source or "").upper()
        is_price_feed = resolution_method.endswith("PRICE_FEED") or resolution_source == "PRICE_FEED"

        if challenge.status == ChallengeStatus.OPEN.value:
            if is_price_feed:
                raw_pair = challenge.trading_pair or ""
                symbol = raw_pair.replace("/", "").upper()
                if not symbol:
                    raise ValueError("Price-feed challenge has no trading pair")
                final_price = await self._get_current_price(symbol)
                if final_price is None:
                    raise RuntimeError(f"Could not fetch a current price for {symbol}")
                target = challenge.target
                if target is None:
                    raise ValueError("Price-feed challenge has no target")
                creator_wins = (
                    final_price >= target
                    if str(challenge.direction).upper().endswith("UP")
                    else final_price <= target
                )
            elif creator_wins is None:
                raise ValueError("Manual resolution requires a winning side")

            update_data = {
                "status": ChallengeStatus.RESOLVED.value,
                "result": "TEAM_A" if creator_wins else "TEAM_B",
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
            if final_price is not None:
                update_data["final_price"] = final_price
            result = (
                service.db.table("challenge")
                .update(update_data)
                .eq("id", challenge_id)
                .execute()
            )
            if not result.data:
                raise RuntimeError("Challenge database update failed")
            challenge_data = result.data[0]
        else:
            challenge_data = challenge.model_dump(mode="json")
            if creator_wins is None:
                stored_result = str(challenge.result or "").upper()
                creator_wins = stored_result.endswith("TEAM_A") if stored_result else is_price_feed
            final_price = challenge.final_price

        await self.remove_challenge(challenge_id)

        onchain = (challenge_data.get("metadata") or {}).get("onchain") or {}
        challenge_pda = onchain.get("challenge_pda")
        creator_wallet = onchain.get("creator_wallet")
        challenger_wallet = onchain.get("challenger_wallet")
        mode = challenge_data.get("mode") or "PVP"
        settlement_attempted = False
        settlement_succeeded = False
        settlement_note = None

        if mode == "PVP" and not challenger_wallet:
            settlement_note = "PVP challenge has no challenger; no on-chain pot was settled"
        elif not challenge_pda or not creator_wallet:
            settlement_note = "Missing on-chain challenge PDA or creator wallet"
        else:
            settlement_attempted = True
            winner_wallet = creator_wallet if creator_wins else (challenger_wallet or creator_wallet)
            settlement_succeeded = await self._call_settlement_service(
                challenge_id=challenge_id,
                challenge_pda=challenge_pda,
                creator_wallet=creator_wallet,
                challenger_wallet=challenger_wallet,
                winner_wallet=winner_wallet,
                creator_wins=bool(creator_wins),
                mode=mode,
            )
            if not settlement_succeeded:
                settlement_note = "Database resolved, but on-chain settlement did not succeed"

        return {
            "challenge_id": challenge_id,
            "status": ChallengeStatus.RESOLVED.value,
            "resolution_method": "PRICE_FEED" if is_price_feed else "MANUAL",
            "creator_wins": bool(creator_wins),
            "final_price": final_price,
            "settlement_attempted": settlement_attempted,
            "settlement_succeeded": settlement_succeeded,
            "settlement_note": settlement_note,
        }

    async def _get_current_price(self, symbol: str) -> float | None:
        """
        Get the current price for a trading pair using Binance REST API.
        
        Args:
            symbol: The trading pair symbol (e.g., 'BTCUSDT')
            
        Returns:
            Current price or None if unavailable
        """
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        price = float(data.get("price", 0))
                        return price if price > 0 else None
                    else:
                        logger.warning(f"Failed to fetch price for {symbol}: HTTP {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error getting current price for {symbol}: {e}")
            return None

    async def add_challenge(self, challenge: dict):
        """
        Add a new challenge to monitor.
        Called when a new challenge is created.
        Lazily starts the WebSocket client if it hasn't been started yet.
        
        Args:
            challenge: Challenge data dictionary
        """
        # Lazily start the WS client if the monitor was never formally started
        # (e.g. in a serverless environment where lifespan hooks don't run)
        if self._ws_client is None:
            logger.info("WS client not initialised – starting it now (lazy start)")
            await start_binance_ws_client()
            self._ws_client = get_binance_ws_client()

        await self._monitor_challenge(challenge)
        logger.info(f"Added new challenge {challenge['id']} to monitor")

    async def remove_challenge(self, challenge_id: int):
        """
        Remove a challenge from monitoring.
        Called when a challenge is cancelled or completed externally.
        
        Args:
            challenge_id: The challenge to remove
        """
        symbol = None
        should_unsubscribe = False
        
        async with self._lock:
            challenge_data = self._active_challenges.pop(challenge_id, None)
            
            if challenge_data:
                symbol = challenge_data.get("trading_pair")
                if symbol:
                    # Remove from symbol mapping
                    if symbol in self._symbol_challenges:
                        self._symbol_challenges[symbol].discard(challenge_id)
                        # Unsubscribe only if no more challenges use this symbol
                        if len(self._symbol_challenges[symbol]) == 0:
                            should_unsubscribe = True
                            del self._symbol_challenges[symbol]
        
        if challenge_data:
            if symbol and should_unsubscribe:
                await self._ws_client.unsubscribe(symbol)
                logger.info(f"Unsubscribed from {symbol} - no more challenges using it")
            logger.info(f"Removed challenge {challenge_id} from monitoring")

    def get_active_challenges(self) -> List[dict]:
        """Get list of currently monitored active challenges"""
        return list(self._active_challenges.values())

    async def set_challenger_wallet(self, challenge_id: int, challenger_wallet: str):
        """
        Update the cached challenger_wallet for a challenge already being monitored.

        The onchain metadata is only captured once, when monitoring starts
        (creation time or service boot) — PVP challenges have no challenger
        yet at that point, so this must be called once an opponent joins to
        avoid `_resolve_challenge_immediately` treating the challenge as
        unopposed forever.
        """
        async with self._lock:
            challenge_data = self._active_challenges.get(challenge_id)
            if challenge_data:
                challenge_data["challenger_wallet"] = challenger_wallet


# Global monitor service instance
_challenge_monitor: ChallengeMonitorService | None = None


def get_challenge_monitor() -> ChallengeMonitorService:
    """Get or create the global challenge monitor service"""
    global _challenge_monitor
    if _challenge_monitor is None:
        _challenge_monitor = ChallengeMonitorService()
    return _challenge_monitor


async def start_challenge_monitor():
    """Start the global challenge monitor service"""
    monitor = get_challenge_monitor()
    await monitor.start()


async def stop_challenge_monitor():
    """Stop the global challenge monitor service"""
    global _challenge_monitor
    if _challenge_monitor:
        await _challenge_monitor.stop()
        _challenge_monitor = None


async def monitor_new_challenge(challenge: dict):
    """
    Add a newly created challenge to the monitor.
    Call this when creating a new challenge.
    """
    monitor = get_challenge_monitor()
    await monitor.add_challenge(challenge)


async def stop_monitoring_challenge(challenge_id: int):
    """
    Stop monitoring a challenge.
    Call this when cancelling or deleting a challenge.
    """
    monitor = get_challenge_monitor()
    await monitor.remove_challenge(challenge_id)


async def update_monitored_challenger_wallet(challenge_id: int, challenger_wallet: str):
    """
    Refresh the challenger_wallet for a challenge already being monitored.
    Call this when an opponent joins a PVP challenge.
    """
    monitor = get_challenge_monitor()
    await monitor.set_challenger_wallet(challenge_id, challenger_wallet)
