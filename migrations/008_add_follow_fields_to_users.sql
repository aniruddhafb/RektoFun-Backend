-- Migration: add follow system columns to users
-- Description: Adds followers/following arrays for social graph features.

ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS followers TEXT[] NULL DEFAULT '{}'::TEXT[];

ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS following TEXT[] NULL DEFAULT '{}'::TEXT[];
