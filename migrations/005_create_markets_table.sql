-- Migration: Create markets table
-- Created: 2026-05-01

CREATE TABLE IF NOT EXISTS public.markets (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text NOT NULL,
  description text NULL,
  image text NULL,
  icon text NULL,
  parent_id uuid NULL,
  market_type text NOT NULL,
  resolution_source text NULL,
  config jsonb NULL,
  total_volume bigint NULL DEFAULT 0,
  is_active boolean NULL DEFAULT true,
  created_at timestamp with time zone NULL DEFAULT now(),
  updated_at timestamp with time zone NULL DEFAULT now(),
  CONSTRAINT markets_pkey PRIMARY KEY (id),
  CONSTRAINT markets_name_unique UNIQUE (name),
  CONSTRAINT markets_slug_key UNIQUE (slug),
  CONSTRAINT markets_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES markets (id) ON DELETE CASCADE
);

-- Create index on parent_id for better query performance
CREATE INDEX IF NOT EXISTS idx_markets_parent_id ON public.markets (parent_id);

-- Create index on market_type for filtering
CREATE INDEX IF NOT EXISTS idx_markets_market_type ON public.markets (market_type);

-- Create index on is_active for filtering
CREATE INDEX IF NOT EXISTS idx_markets_is_active ON public.markets (is_active);

-- Create index on slug for faster lookups
CREATE INDEX IF NOT EXISTS idx_markets_slug ON public.markets (slug);
