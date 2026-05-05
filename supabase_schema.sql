-- Challenges table
create table if not exists public.challenges (
  id uuid not null default gen_random_uuid(),

  -- 🧾 Basic Info
  title text not null,
  description text null,
  category text not null,
  event_type text not null, -- binary, multi_outcome, etc
  ticker text null,

  -- 👤 User
  created_by text null,

  -- ⚙️ Mode
  mode text not null, -- 'pvp' | 'pool'

  -- 💰 Betting Core
  initial_bet integer not null, -- creator's bet (USDC, integer only)

  -- PvP constraints
  min_accept_bet integer null,
  max_accept_bet integer null,

  -- Pool constraints
  min_bet integer not null default 1, -- >= 1 USDC
  bet_unit integer not null default 1, -- enforce integer bets

  total_pool bigint not null default 0,

  -- ⏱️ Timing
  expire_time timestamptz not null,
  resolve_time timestamptz null,
  resolved_at timestamptz null,

  -- 📊 Status
  status text not null default 'open', 
  -- open | locked | resolved | cancelled

  resolution_status text not null default 'pending',
  -- pending | fetching | resolved | failed | disputed

  resolution_mode text not null default 'at_time',
  -- at_time | anytime_before | event_based

  -- 🔮 Oracle Config
  resolution_source text null,
  resolution_config jsonb not null,

  -- 🏁 Result
  result jsonb null,

  -- 🎨 UI / Display
  metadata jsonb null,

  -- 🕒 Timestamps
  created_at timestamptz default now(),
  updated_at timestamptz default now(),

  -- 🔐 Constraints
  constraint challenges_pkey primary key (id),
  constraint challenges_category_fkey 
    foreign key (category) references markets (name),
  constraint challenges_created_by_fkey 
    foreign key (created_by) references users (wallet_address) on delete set null
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

create table if not exists public.markets (
  id uuid not null default gen_random_uuid(),
  name text not null,
  symbol text not null,
  description text null,
  image text null,
  icon text null,
  parent_id uuid null,
  parent_name text null,
  market_type text not null,
  resolution_source text null,
  config jsonb null,
  total_volume bigint null default 0,
  is_active boolean null default true,
  created_at timestamptz null default now(),
  updated_at timestamptz null default now(),
  constraint markets_pkey primary key (id),
  constraint markets_name_unique unique (name),
  constraint markets_slug_key unique (symbol),
  constraint markets_parent_id_fkey foreign key (parent_id) references markets (id) on delete cascade
);

create index if not exists idx_markets_parent_id
    on public.markets (parent_id);

create index if not exists idx_markets_market_type
    on public.markets (market_type);

create index if not exists idx_markets_is_active
    on public.markets (is_active);

create index if not exists idx_markets_slug
    on public.markets (symbol);
