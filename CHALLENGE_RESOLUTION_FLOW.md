# Challenge Auto-Resolution Flow

## Overview

When a **crypto challenge** is created, a one-shot job is automatically scheduled to fire at `expire_time`. At that moment, the system fetches the live price from the **DIA Data API**, compares it against the challenge's `target_price`, and resolves the challenge as **YES** or **NO**.

Only challenges whose market has `parent_name = "crypto"` are auto-resolved. Markets follow a parent-child hierarchy — the parent market is named `"crypto"`, and child markets (Bitcoin, Ethereum, Solana, etc.) reference it via `parent_name = "crypto"`. All other markets (IPL, FIFA, etc.) are skipped.

---

## Components

| File | Role |
|---|---|
| `services/dia_price.py` | Fetches live USD price from DIA API using `asset_name` |
| `services/challenge_scheduler.py` | APScheduler wrapper — schedules & runs resolution jobs |
| `services/scheduler_registry.py` | Singleton registry to share the scheduler across modules |
| `main.py` | Starts/stops the scheduler on app startup/shutdown |
| `routes/challenges.py` | Schedules a job after a new challenge is created |

---

## Flow Diagram

```
POST /challenges
      │
      ▼
1. Insert challenge row into Supabase
      │
      ▼
2. Create challenge_side (challenger) + position
      │
      ▼
3. _maybe_schedule_resolution()
      │
      ├─ Lookup markets table: does market.parent_name == "crypto"?
      │       │
      │       ├─ NO  → skip, return (non-crypto child markets not auto-resolved)
      │       │
      │       └─ YES ↓
      │
      ▼
4. scheduler.schedule_challenge(challenge_id, expire_time)
      │
      └─ APScheduler registers a one-shot DateTrigger job
         Job ID: "resolve_{challenge_id}"
         Fires at: expire_time (UTC)


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    [ at expire_time ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

5. APScheduler fires → _resolve_challenge(challenge_id)
      │
      ▼
6. Fetch challenge row from Supabase
      │
      ├─ Not found → skip
      ├─ status == "resolved" or "cancelled" → skip (already done)
      └─ asset_name missing → mark resolution_status = "failed"
      │
      ▼
7. Set resolution_status = "fetching" in Supabase
      │
      ▼
8. GET https://api.diadata.org/v1/assetQuotation/{asset_name}/0x000...
      │
      ├─ Request fails / price missing → mark resolution_status = "failed"
      │
      └─ Success: price = e.g. 79548.00
      │
      ▼
9. Determine outcome:
      price >= target_price  →  outcome = "YES"
      price <  target_price  →  outcome = "NO"
      target_price is None   →  outcome = "N/A"
      │
      ▼
10. Update challenge row in Supabase:
      status             = "resolved"
      resolution_status  = "resolved"
      resolved_at        = <now UTC>
      result             = {
                             "outcome":        "YES" | "NO" | "N/A",
                             "price_at_expiry": 79548.00,
                             "target_price":    100000,
                             "source":          "diadata.org",
                             "resolved_at":     "2025-12-31T23:59:59Z"
                           }
```

---

## Startup Recovery

If the server **restarts** while challenges are still pending, no jobs are lost.

On startup (`lifespan` in `main.py`), `ChallengeScheduler.start()` runs a recovery task:

```
App starts
    │
    ▼
Query Supabase:
  SELECT id, expire_time, category
  FROM challenges
  WHERE status = 'open' AND expire_time > now()
    │
    ▼
For each row:
  - Check if market.parent_name == "crypto"
  - If yes → schedule_challenge(id, expire_time)
    │
    ▼
All pending crypto challenges are re-registered with APScheduler
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Market is not crypto | Job is never scheduled — silently skipped |
| Challenge already resolved/cancelled | Job fires but exits immediately |
| DIA API returns error / timeout | `resolution_status = "failed"`, `result = {"error": "..."}` |
| `asset_name` is missing on challenge | `resolution_status = "failed"`, `result = {"error": "no asset_name"}` |
| Server restarts before expire_time | Recovery on startup re-schedules the job |
| Same challenge scheduled twice | Duplicate check via job ID prevents double-scheduling |

---

## Data Fields Used

| Field | Source | Purpose |
|---|---|---|
| `challenges.asset_name` | e.g. `"Bitcoin"` | Used as the DIA API blockchain name |
| `challenges.target_price` | e.g. `100000` | Compared against live price to determine YES/NO |
| `challenges.expire_time` | e.g. `"2025-12-31T23:59:59Z"` | When the resolution job fires |
| `challenges.ticker` | e.g. `"BTC"` | Stored on the challenge but not used for price fetch |
| `markets.parent_name` | e.g. `"crypto"` | Gate: only markets whose parent is "crypto" are auto-resolved |

---

## Adding a New Crypto Asset

No code changes needed. As long as:
1. The child market row has `parent_name = "crypto"` (pointing to the parent crypto market)
2. The challenge has `asset_name` set to the exact blockchain name DIA uses (e.g. `"Ethereum"`, `"Solana"`, `"BinanceSmartChain"`)

...the system will automatically resolve it.

You can verify the correct `asset_name` by checking:
```
https://api.diadata.org/v1/assetQuotation/{asset_name}/0x0000000000000000000000000000000000000000
```
