# Architecture: TaskFlow REST API

## 1. Requirements Traceability Matrix

| PRD Requirement (Quoted) | Technical Component | Implementation Details |
|-------------------------|---------------------|------------------------|
| "Passwords hashed using bcrypt (cost factor 12)" | `internal/auth/service.go` | `bcrypt.GenerateFromPassword(password, 12)` |
| "JWT access token (HS256 algorithm, 24-hour expiry)" | `internal/middleware/jwt.go` | `jwt.SigningMethodHS256`, `exp: time.Now().Add(24h)` |
| "POST /auth/logout invalidates token on client-side" | `internal/handlers/auth.go` | Returns 204 No Content; client discards token |
| "Creator assigned Admin role automatically" | `internal/team/service.go:CreateTeam` | Transaction inserts team + membership with `role='admin'` |
| "Unique 8-character alphanumeric code valid for 7 days" | `internal/team/invite.go` | `rand.AlphaNum(8)`, `expires_at: NOW() + INTERVAL '7 days'` |
| "Users limited to membership in maximum 5 teams" | `internal/middleware/limits.go` | `SELECT COUNT(*) FROM team_memberships WHERE user_id=$1` check |
| "Task status enum: todo, in_progress, done" | `database/schema.sql` | `CREATE TYPE task_status AS ENUM ('todo', 'in_progress', 'done')` |
| "Returns HTTP 404 (not 403) if task exists but user doesn't belong to team" | `internal/middleware/tenant.go` | Verify team membership before querying task; return 404 if unauthorized |
| "Admin can delete any task; Member can delete only tasks they created" | `internal/task/service.go:DeleteTask` | RBAC check: `if role != 'admin' && task.CreatorID != userID` return 403 |
| "All database queries for tasks include mandatory team_id filter" | `internal/task/repository.go` | All methods require `teamID uuid.UUID` parameter; `WHERE team_id=$1` |
| "Team IDs use UUID v4" | `database/schema.sql` | `gen_random_uuid()` (v4) for `teams.id` |
| "Audit log table records user_id, action, team_id, timestamp" | `internal/audit/logger.go` + `database/schema.sql` | Async insert to `audit_logs` table on DELETE/UPDATE/CREATE |
| "DELETE /users/me hard deletes all personal data within 30 days" | `internal/gdpr/service.go` | `ON DELETE CASCADE` on user FKs; cron job purges soft-deleted data after 30 days |
| "GET /teams/{team_id}/tasks returns paginated list (default 20, max 100)" | `internal/handlers/task.go` | `limit := min(100, max(20, parseInt(r.URL.Query().Get("limit"))))` |
| "Returns HTTP 401 for missing or invalid tokens" | `internal/middleware/jwt.go` | `Authorization: Bearer <token>` validation; `www-authenticate: Bearer` header on failure |

**Flagged Requirements**: None. All PRD requirements implementable with Go + PostgreSQL stack.

---

## 2. System Architecture

### C4 Level 3 (Component) Diagram Description

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                      │
│         (cURL, Postman, Mobile Apps, Web Frontends)         │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS/TLS 1.3
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      NGINX Ingress                          │
│   • TLS termination (TLS 1.3 only, HTTP/2 enabled)          │
│   • Rate limiting: 100 req/min per IP (infrastructure layer)│
│   • CORS header injection (configurable origins)            │
└──────────────────────┬──────────────────────┬───────────────┘
                       │                      │
                       ▼                      ▼
┌──────────────────────────────┐    ┌──────────────────────────┐
│    TaskFlow API Service      │    │   PostgreSQL 15 Cluster  │
│   (Go 1.21 + Gin + GORM)     │    │   • Primary (writes)     │
│                              │    │   • 2x Replicas (reads)  │
│  ┌────────────────────────┐  │    │   • Automated failover   │
│  │   HTTP Router (Gin)    │  │    └──────────────────────────┘
│  │   • Request validation │  │              │
│  └──────────┬─────────────┘  │              │ SQL (SSL)
│             │                │              │
│  ┌──────────▼─────────────┐  │    ┌─────────▼──────────┐
│  │   Middleware Stack     │  │    │      Redis 7       │
│  │   • JWT Auth (HS256)   │  │    │   • Invite TTL     │
│  │   • RBAC Enforcement   │  │    │   • Rate limit     │
│  │   • Tenant Isolation   │  │    │     counters       │
│  │   • Audit Logger       │  │    │   • Session cache  │
│  └──────────┬─────────────┘  │    └────────────────────┘
│             │
│  ┌──────────▼─────────────┐
│  │   Business Logic       │
│  │   • Auth Service       │
│  │   • Team Service       │
│  │   • Task Service       │
│  │   • GDPR Service       │
│  └──────────┬─────────────┘
│             │
│  ┌──────────▼─────────────┐
│  │   Repository Layer     │
│  │   • GORM v2            │
│  │   • Connection pooling │
│  │     (max 25 conns)     │
│  └────────────────────────┘
└──────────────────────────────┘
```

### Critical Path Data Flows

**Authentication Flow**:
1. Client `POST /auth/login` → NGINX → Gin Router
2. `AuthHandler.Login` validates email/password against `users` table (bcrypt compare)
3. Generate JWT: `claims := jwt.MapClaims{"sub": user.ID, "email": user.Email, "exp": time.Now().Add(24h)}`
4. Sign with `HS256` using 256-bit secret from Vault
5. Return `{"access_token": "<jwt>", "token_type": "Bearer"}`

**Task Creation Flow**:
1. Client `POST /teams/{team_id}/tasks` with `Authorization: Bearer <jwt>`
2. `JWTMiddleware` validates signature and expiry; extracts `user_id`
3. `TenantMiddleware` verifies `team_id` exists in `team_memberships` for `user_id` (404 if not found)
4. `RBACMiddleware` verifies role allows "task:create" (Members and Admins allowed)
5. `TaskHandler.Create` validates input (title 1-100 chars, description max 2000)
6. `TaskService.Create` executes SQL: `INSERT INTO tasks (id, team_id, title, description, status, creator_id) VALUES (...)`
7. `AuditLogger` asynchronously writes: `INSERT INTO audit_logs (user_id, action, team_id, entity_type, entity_id, timestamp) VALUES (...)`
8. Return 201 with full task object

**Team Deletion Flow (Destructive)**:
1. Client `DELETE /teams/{team_id}`
2. Auth + Tenant + RBAC checks (Admin only)
3. Start PostgreSQL transaction:
   ```sql
   BEGIN;
   DELETE FROM tasks WHERE team_id=$1;
   DELETE FROM team_memberships WHERE team_id=$1;
   DELETE FROM invites WHERE team_id=$1;
   DELETE FROM teams WHERE id=$1;
   COMMIT;
   ```
4. Audit log entry: `action='team:delete', entity_id=<team_id>`
5. Return 204 No Content

### External Dependencies & SLAs

| Dependency | Version/Type | SLA Requirement | Failure Mode |
|------------|-------------|-----------------|--------------|
| PostgreSQL | 15.x Primary-Replica | 99.95% uptime | Read replicas serve GET requests if primary fails; write queue buffers mutations |
| Redis | 7.x Cluster | 99.9% uptime | Invite code generation falls back to PostgreSQL TTL; rate limiting disabled (open) |
| HashiCorp Vault | Enterprise | 99.9% uptime | API startup requires Vault connection; fails fast if secrets unavailable |
| AWS EBS/Azure Disk | SSD gp3/Premium SSD | 99.9% durability | Database volumes encrypted AES-256-XTS; automated daily snapshots |

---

## 3. Tech Stack Decision Record

### Frontend
- **Not Applicable**: REST API only; no frontend code

### API Gateway
- **Chosen**: NGINX Ingress Controller (Kubernetes)
  - Version: 1.25+
  - Justification: Native TLS 1.3 support, efficient reverse proxying, widespread operational knowledge
  - Rejected: Kong (unnecessary complexity for simple routing), AWS API Gateway