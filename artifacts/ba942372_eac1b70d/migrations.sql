**DATABASE ARCHITECTURE: TaskFlow REST API**
*PostgreSQL 15+ with Redis 7+ | UUID Primary Keys | Soft Delete Pattern*

---

## 1. MIGRATION FILES

### Migration: 001_initial_schema.sql

```sql
-- UP MIGRATION
BEGIN;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Custom ENUM types for type safety
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('admin', 'member');
    CREATE TYPE task_status AS ENUM ('todo', 'in_progress', 'done', 'cancelled');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- 1. USERS TABLE
-- GDPR-compliant with soft delete support
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL, -- bcrypt output storage
    full_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ,
    
    -- Business constraints
    CONSTRAINT users_email_unique UNIQUE (email),
    CONSTRAINT users_email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
);

COMMENT ON TABLE users IS 'User accounts with soft delete for GDPR right to be forgotten';
COMMENT ON COLUMN users.password_hash IS 'bcrypt hash with cost factor 12';

-- 2. TEAMS TABLE
-- Multi-tenant isolation unit
CREATE TABLE IF NOT EXISTS teams (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ,
    
    -- Foreign key with RESTRICT to prevent accidental creator deletion
    CONSTRAINT fk_teams_created_by 
        FOREIGN KEY (created_by) 
        REFERENCES users(id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE
);

COMMENT ON CONSTRAINT fk_teams_created_by ON teams IS 'Prevent deletion of users who created teams; forces data retention or ownership transfer';

-- 3. TEAM MEMBERSHIPS (Junction with attributes)
-- Enforces max 5 teams per user via trigger
CREATE TABLE IF NOT EXISTS team_memberships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id UUID NOT NULL,
    user_id UUID NOT NULL,
    role user_role NOT NULL DEFAULT 'member',
    joined_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Composite unique constraint prevents duplicate memberships
    CONSTRAINT unique_team_membership UNIQUE (team_id, user_id),
    
    -- Cascade delete: If team is deleted, remove all memberships
    CONSTRAINT fk_memberships_team 
        FOREIGN KEY (team_id) 
        REFERENCES teams(id) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE,
    
    -- Cascade delete: If user is hard-deleted, clean up memberships  
    -- Note: Soft deleted users retain memberships for audit trails
    CONSTRAINT fk_memberships_user 
        FOREIGN KEY (user_id) 
        REFERENCES users(id) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE
);

COMMENT ON CONSTRAINT fk_memberships_team ON team_memberships IS 'Cascading team deletion automatically removes all member associations';

-- 4. INVITES
-- 8-character alphanumeric codes with 7-day expiration
CREATE TABLE IF NOT EXISTS invites (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id UUID NOT NULL,
    code VARCHAR(8) NOT NULL,
    created_by UUID,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    used_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Unique active codes only
    CONSTRAINT invites_code_unique UNIQUE (code),
    
    -- Business rule: 8 alphanumeric characters
    CONSTRAINT valid_code_format CHECK (code ~ '^[A-Za-z0-9]{8}$'),
    
    -- Business rule: Expiry must be in the future at creation
    CONSTRAINT valid_expiry CHECK (expires_at > created_at),
    
    -- FK: Delete invites if team deleted
    CONSTRAINT fk_invites_team 
        FOREIGN KEY (team_id) 
        REFERENCES teams(id) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE,
    
    -- FK: Set NULL on creator deletion (anonymize invite history)
    CONSTRAINT fk_invites_creator 
        FOREIGN KEY (created_by) 
        REFERENCES users(id) 
        ON DELETE SET NULL 
        ON UPDATE CASCADE,
    
    -- FK: Set NULL on user deletion (preserve invite, anonymize usage)
    CONSTRAINT fk_invites_used_by 
        FOREIGN KEY (used_by) 
        REFERENCES users(id) 
        ON DELETE SET NULL 
        ON UPDATE CASCADE
);

COMMENT ON COLUMN invites.code IS '8-character alphanumeric invite code (e.g., X7K9pM2q)';
COMMENT ON COLUMN invites.expires_at IS 'Calculated as created_at + INTERVAL 7 days';

-- 5. TASKS
-- Core entity with tenant isolation via team_id
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    team_id UUID NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status task_status NOT NULL DEFAULT 'todo',
    assignee_id UUID,
    created_by UUID NOT NULL,
    due_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ,
    
    -- FK: Cascade delete tasks when team deleted
    CONSTRAINT fk_tasks_team 
        FOREIGN KEY (team_id) 
        REFERENCES teams(id) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE,
    
    -- FK: Set NULL when assignee deleted (unassign task)
    CONSTRAINT fk_tasks_assignee 
        FOREIGN KEY (assignee_id) 
        REFERENCES users(id) 
        ON DELETE SET NULL 
        ON UPDATE CASCADE,
    
    -- FK: RESTRICT deletion of task creators (preserve audit trail)
    -- Alternative: ON DELETE SET NULL if business allows orphaned tasks
    CONSTRAINT fk_tasks_creator 
        FOREIGN KEY (created_by) 
        REFERENCES users(id) 
        ON DELETE RESTRICT 
        ON UPDATE CASCADE,
    
    -- Business constraint: Due date must be in the future or null
    CONSTRAINT valid_due_date CHECK (due_date IS NULL OR