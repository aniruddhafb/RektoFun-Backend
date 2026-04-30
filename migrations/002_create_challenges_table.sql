-- Migration: create_challenges_table
-- Description: Creates the challenges and challenge_outcomes tables

-- Challenges table
CREATE TABLE IF NOT EXISTS public.challenges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    title text NOT NULL,
    description text,
    category text NOT NULL,
    subcategory text,
    event_type text NOT NULL,
    ticker text,
    created_by text REFERENCES users(wallet_address) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'open',
    resolution_source text,
    resolution_details jsonb,
    expire_time timestamptz NOT NULL,
    resolve_time timestamptz,
    result jsonb,
    metadata jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Challenge outcomes table
CREATE TABLE IF NOT EXISTS public.challenge_outcomes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    challenge_id uuid REFERENCES challenges(id) ON DELETE CASCADE,
    outcome_key text NOT NULL,
    title text NOT NULL,
    metadata jsonb,
    created_at timestamptz DEFAULT now()
);

-- Indexes for challenges
CREATE INDEX IF NOT EXISTS challenges_created_at_idx ON public.challenges (created_at DESC);
CREATE INDEX IF NOT EXISTS challenges_category_idx ON public.challenges (category);
CREATE INDEX IF NOT EXISTS challenges_status_idx ON public.challenges (status);
CREATE INDEX IF NOT EXISTS challenges_expire_time_idx ON public.challenges (expire_time);

-- Indexes for challenge_outcomes
CREATE INDEX IF NOT EXISTS challenge_outcomes_challenge_id_idx ON public.challenge_outcomes (challenge_id);

-- Trigger to auto-update updated_at
DROP TRIGGER IF EXISTS set_challenges_updated_at ON public.challenges;
CREATE TRIGGER set_challenges_updated_at
    BEFORE UPDATE ON public.challenges
    FOR EACH ROW
    EXECUTE FUNCTION public.set_updated_at();
