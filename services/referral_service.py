"""Referral commission accounting for successfully settled PVP challenges."""

import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


class ReferralService:
    def __init__(self, db):
        self.db = db

    def credit_pvp_participant(self, challenge_id: int, participant_wallet: str, pool_size) -> bool:
        """Credit one participant's referrer once. The database RPC is atomic/idempotent."""
        try:
            pool = Decimal(str(pool_size or 0))
        except (InvalidOperation, ValueError):
            logger.warning("Invalid pool size for referral credit on challenge %s", challenge_id)
            return False

        if pool <= 0 or not participant_wallet:
            return False

        result = self.db.rpc(
            "credit_referral_commission",
            {
                "p_challenge_id": challenge_id,
                "p_participant_wallet": participant_wallet,
                "p_pool_size": str(pool),
            },
        ).execute()
        credited = bool(result.data)
        if credited:
            logger.info("Referral commission credited for challenge %s", challenge_id)
        return credited
