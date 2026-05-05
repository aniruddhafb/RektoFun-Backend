-- Migration: Add parent_name to markets table
-- Created: 2026-05-05

ALTER TABLE public.markets
ADD COLUMN IF NOT EXISTS parent_name text NULL;
