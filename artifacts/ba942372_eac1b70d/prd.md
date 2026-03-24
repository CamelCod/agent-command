# PRD: TaskFlow REST API

## 1. Product Vision
A secure, multi-tenant REST API enabling small teams to create, assign, and track tasks with strict data isolation and simple role-based permissions.

## 2. Target Users
**Primary Users**: Small development teams (3-20 people), indie developers, and project managers building lightweight productivity tools.

**Problem Solved**: Provides a ready-to-integrate backend that eliminates the need to build authentication, team isolation, and permission logic from scratch while preventing cross-tenant data leakage.

## 3. Core Features (MVP)

### Feature 1: JWT Authentication
**User Story**: As a developer, I want to authenticate via email and password so that I can securely access protected resources.

**Acceptance Criteria**:
- `POST /auth/register` accepts unique email and password (minimum 8 characters, 1 number)
- Passwords hashed using bcrypt (cost factor 12) before storage
- `POST /auth/login` returns JWT access token (HS256 algorithm, 24-hour expiry) containing `user_id` and `email`
- `POST /auth/logout` invalidates token on client-side (stateless server)
- Returns HTTP 401 for missing or invalid tokens on protected endpoints

### Feature 2: Team Lifecycle Management
**User Story**: As a user, I want to create teams and invite colleagues so that we can collaborate in isolated workspaces.

**Acceptance Criteria**:
- `POST /teams` creates a team with name (3-50 chars); creator assigned "Admin" role automatically
- `POST /teams/{team_id}/invites` generates unique 8-character alphanumeric code valid for 7 days (Admin only)
- `POST /teams/join` accepts invite code and adds user as "Member" role
- `GET /teams` returns array of teams where user is a member (team_id, name, role, joined_at)
- `DELETE /teams/{team_id}` permanently deletes team and all associated tasks (Admin only, irreversible)
- Users limited to membership in maximum 5 teams (MVP abuse prevention)

### Feature 3: Task CRUD Operations
**User Story**: As a team member, I want to create and manage tasks so that I can track work progress within my team.

**Acceptance Criteria**:
- `POST /teams/{team_id}/tasks` creates task with required `title` (1-100 chars), optional `description` (max 2000 chars), optional `assignee_id` (must be active team member)
- Task `status` enum: `todo`, `in_progress`, `done` (default: `todo`)
- `GET /teams/{team_id}/tasks` returns paginated list (default 20 items/page, max 100) with `created_at` and `updated_at` timestamps
- `GET /teams/{team_id}/tasks/{task_id}` returns full task details including creator_id and assignee_id
- `PATCH /teams/{team_id}/tasks/{task_id}` updates mutable fields (title, description, status, assignee_id)
- `DELETE /teams/{team_id}/tasks/{task_id}` permanently removes task (Admin can delete any; Member can delete only tasks they created)
- Returns HTTP 404 (not 403) if task exists but user doesn't belong to the team (security through obscurity)

### Feature 4: Role-Based Access Control (RBAC)
**User Story**: As a team admin, I want to enforce permissions so that members can only perform authorized actions.

**Acceptance Criteria**:
- Middleware validates JWT presence and signature on all protected routes
- **Admin** permissions: Delete any task, remove team members, generate invite codes, delete team
- **Member** permissions: Create tasks, update any task field, delete own tasks only, view all team tasks
- Attempting admin actions as Member returns HTTP 403 with error code `insufficient_permissions`
- Team ID in URL path validated against user's team membership database join (no orphaned access)

### Feature 5: Multi-Tenant Data Isolation
**User Story**: As a user, I want guaranteed data isolation so that other teams cannot view or modify my team's tasks.

**Acceptance Criteria**:
- All database queries for tasks include mandatory `team_id` filter scoped to authenticated user's memberships
- Foreign key constraints enforce referential integrity between tasks, teams, and users
- Team IDs use UUID v4 (non-sequential) to prevent enumeration attacks
- Database transactions used for team deletion to prevent partial data removal
- Audit log table records `user_id`, `action`, `team_id`, `timestamp` for all destructive operations (create, update, delete)

## 4. Out of Scope (Explicitly Excluded)
- **Real-time Updates**: No WebSocket or Server-Sent Events (SSE); polling only
- **File Attachments**: No image/document upload functionality
- **Task Hierarchy**: No subtasks, dependencies, or parent-child relationships
- **Authentication Providers**: No OAuth2, Google/GitHub SSO, or SAML (email/password only)
- **Notifications**: No email, push, or in-app notifications
- **Advanced Search**: No full-text search, filtering by date ranges, or sorting beyond `created_at DESC`
- **Task Metadata**: No labels, tags, priorities, colors, or custom fields
- **Multiple Assignees**: Tasks assigned to single user only (or unassigned)
- **Team Hierarchy**: Flat team structure only (no sub-teams or departments)
- **API Rate Limiting**: No throttling logic in application layer (assume infrastructure-level protection)
- **Soft Deletes**: Hard delete only (no trash/recycle bin)

## 5. Success Metrics
- **Performance**: 95th percentile latency < 200ms for `GET /teams/{id}/tasks` (up to 100 tasks returned)
- **Security**: Zero cross-team data access incidents verified via penetration testing
- **Reliability**: 99.9% uptime for authentication endpoints over 30-day period
- **Correctness**: 100% of endpoints return RFC 7807 Problem Details format for errors
- **Adoption**: API supports 100 concurrent users per team without performance degradation

## 6. Technical Constraints
- **Architecture**: Stateless REST API only; no GraphQL or gRPC
- **Protocol**: HTTPS/TLS 1.3 required for all communications; HTTP requests rejected
- **Data Format**: JSON request/response bodies with `Content-Type: application/json`
- **Authentication**: JWT (HS256) with 24-hour expiration; no session cookies or refresh tokens
- **Database**: PostgreSQL 14+ required for ACID compliance and row-level security support
- **Containerization**: Must run in Docker container with health check endpoint `GET /health`
- **Compliance**: GDPR Article 17 (Right to Erasure) support—`DELETE /users/me` hard deletes all personal data within 30 days of request
- **CORS**: Configurable allowed origins (default: localhost only for development)
- **Timezones**: All timestamps stored and returned in UTC (ISO 8601 format)