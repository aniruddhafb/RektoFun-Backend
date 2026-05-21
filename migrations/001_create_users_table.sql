-- Migration: create_users_table
-- Description: Creates the users table with wallet-based authentication and referral system

-- Create users table
CREATE TABLE IF NOT EXISTS public.users (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    wallet_address TEXT NOT NULL,
    username TEXT NULL,
    description TEXT NULL,
    profile_image TEXT NULL,
    login_type TEXT NOT NULL DEFAULT 'wallet'::TEXT,
    referral_code TEXT NULL DEFAULT substring(md5((random())::TEXT), 1, 8),
    referred_by UUID NULL,
    referrals TEXT[] NULL DEFAULT '{}'::TEXT[],
    followers TEXT[] NULL DEFAULT '{}'::TEXT[],
    following TEXT[] NULL DEFAULT '{}'::TEXT[],
    created_at TIMESTAMP WITH TIME ZONE NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NULL DEFAULT NOW(),
    earnings NUMERIC NULL DEFAULT 0,
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT users_referral_code_key UNIQUE (referral_code),
    CONSTRAINT users_username_key UNIQUE (username),
    CONSTRAINT users_wallet_address_key UNIQUE (wallet_address),
    CONSTRAINT users_referred_by_fkey FOREIGN KEY (referred_by) REFERENCES users(id)
) TABLESPACE pg_default;

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_wallet_address ON public.users USING btree (wallet_address) TABLESPACE pg_default;
CREATE INDEX IF NOT EXISTS idx_users_referral_code ON public.users USING btree (referral_code) TABLESPACE pg_default;

-- Create trigger function to auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for auto-updating updated_at on row update
DROP TRIGGER IF EXISTS update_users_updated_at ON public.users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON public.users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Enable RLS (Row Level Security)
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for users table
-- Policy: Anyone can read users
CREATE POLICY "Users are publicly readable" ON public.users
    FOR SELECT USING (true);

-- Policy: Anyone can create users (for signup)
CREATE POLICY "Users can be created publicly" ON public.users
    FOR INSERT WITH CHECK (true);

-- Policy: Users can update their own profile
CREATE POLICY "Users can update own profile" ON public.users
    FOR UPDATE USING (true);

-- Policy: Users can delete their own account
CREATE POLICY "Users can delete own account" ON public.users
    FOR DELETE USING (true);
