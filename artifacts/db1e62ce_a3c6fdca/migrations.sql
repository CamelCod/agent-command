```sql
-- ============================================================
-- MIGRATION 001: FOUNDATION
-- Description: Organizations, users, sites, and assignments
-- Dependencies: None
-- ============================================================

BEGIN;

-- Organizations (Multi-tenancy root)
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL CHECK (char_length(name) <= 255),
    tax_id TEXT,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT org_name_not_empty CHECK (name <> '')
);

-- Users (Supervisors, Managers, Workers)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('SUPERVISOR', 'MANAGER', 'ADMIN', 'WORKER')),
    first_name TEXT NOT NULL CHECK (char_length(first_name) <= 100),
    last_name TEXT NOT NULL CHECK (char_length(last_name) <= 100),
    phone TEXT CHECK (phone IS NULL OR char_length(phone) <= 20),
    encrypted_password TEXT NOT NULL,
    email_verified_at TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT user_email_unique_per_org UNIQUE (org_id, email),
    CONSTRAINT user_email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT user_name_not_empty CHECK (first_name <> '' AND last_name <> '')
);

-- Construction Sites
CREATE TABLE IF NOT EXISTS sites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (char_length(name) <= 255),
    project_code TEXT,
    location_address TEXT,
    geo_latitude DECIMAL(10,8) CHECK (geo_latitude BETWEEN -90 AND 90),
    geo_longitude DECIMAL(11,8) CHECK (geo_longitude BETWEEN -180 AND 180),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'COMPLETED')),
    start_date DATE,
    expected_end_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT site_code_unique_per_org UNIQUE (org_id, project_code),
    CONSTRAINT site_dates_logical CHECK (expected_end_date IS NULL OR start_date IS NULL OR expected_end_date >= start_date)
);

-- Site Assignments (Many-to-Many with role context)
CREATE TABLE IF NOT EXISTS site_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_on_site TEXT NOT NULL DEFAULT 'WORKER' CHECK (role_on_site IN ('SUPERVISOR', 'FOREMAN', 'WORKER', 'SAFETY_OFFICER')),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_active_assignment UNIQUE (site_id, user_id),
    CONSTRAINT assignment_dates_logical CHECK (revoked_at IS NULL OR revoked_at >= assigned_at)
);

-- Indexes for Migration 001
CREATE INDEX IF NOT EXISTS idx_users_org_lookup ON users(org_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_users_email_lookup ON users(email) WHERE deleted_at