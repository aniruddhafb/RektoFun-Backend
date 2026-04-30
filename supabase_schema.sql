-- Challenges table
create table if not exists public.challenges (
  id uuid primary key default gen_random_uuid(),

  title text not null,
  description text,

  category text not null, -- crypto, sports, politics, etc
  subcategory text,       -- btc, football, elections

  event_type text not null, 
  -- binary, multi_outcome, numeric_range

  ticker text, -- optional (BTC, AAPL, etc)

  created_by text references users(wallet_address) on delete set null,

  status text not null default 'open',
  -- open, locked, resolved, cancelled

  resolution_source text, -- API, oracle, manual
  resolution_details jsonb,

  expire_time timestamptz not null, -- no more entries
  resolve_time timestamptz,         -- when outcome known

  result jsonb, -- flexible outcome storage

  metadata jsonb, -- extra config (thresholds, rules)

  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Challenge outcomes table
create table if not exists public.challenge_outcomes (
  id uuid primary key default gen_random_uuid(),
  challenge_id uuid references challenges(id) on delete cascade,

  outcome_key text not null, -- "YES", "NO", "TEAM_A", "100K_PLUS"
  title text not null,

  metadata jsonb,

  created_at timestamptz default now()
);

-- Indexes for challenges
create index if not exists challenges_created_at_idx
    on public.challenges (created_at desc);

create index if not exists challenges_category_idx
    on public.challenges (category);

create index if not exists challenges_status_idx
    on public.challenges (status);

create index if not exists challenges_expire_time_idx
    on public.challenges (expire_time);

-- Indexes for challenge_outcomes
create index if not exists challenge_outcomes_challenge_id_idx
    on public.challenge_outcomes (challenge_id);

-- Trigger to auto-update updated_at
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = timezone('utc', now());
    return new;
end;
$$;

drop trigger if exists set_challenges_updated_at on public.challenges;

create trigger set_challenges_updated_at
before update on public.challenges
for each row
execute function public.set_updated_at();
