"""DIA Data price fetcher for crypto assets."""

from __future__ import annotations

import httpx

# Native asset address used by DIA for L1 coins
_NATIVE_ADDRESS = "0x0000000000000000000000000000000000000000"
_DIA_BASE_URL = "https://api.diadata.org/v1/assetQuotation"


async def get_asset_price(asset_name: str) -> float | None:
    """
    Fetch the current USD price for a crypto asset from the DIA Data API.

    The DIA API path uses the full asset/blockchain name directly, which is
    exactly what challenges.asset_name stores (e.g. "Bitcoin", "Ethereum",
    "Solana"). No mapping needed.

    Args:
        asset_name: Full asset name as stored in challenges.asset_name,
                    e.g. "Bitcoin", "Ethereum", "Solana".

    Returns:
        The current price as a float, or None if the request fails.

    Example:
        price = await get_asset_price("Bitcoin")
        # GET https://api.diadata.org/v1/assetQuotation/Bitcoin/0x000...
        # → 79548.0
    """
    if not asset_name:
        print("[DIA] asset_name is empty, cannot fetch price.")
        return None

    url = f"{_DIA_BASE_URL}/{asset_name}/{_NATIVE_ADDRESS}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            price = data.get("Price")
            if price is None:
                print(f"[DIA] No 'Price' field in response for asset_name={asset_name}: {data}")
                return None
            return float(price)
    except httpx.HTTPStatusError as exc:
        print(f"[DIA] HTTP error fetching price for asset_name={asset_name}: {exc.response.status_code} {exc}")
        return None
    except Exception as exc:
        print(f"[DIA] Unexpected error fetching price for asset_name={asset_name}: {exc}")
        return None
