# Architecture: SiteLog API - Construction Daily Reporting System

## 1. Requirements Traceability Matrix

| PRD Requirement | Technical Component | Implementation Detail |
|----------------|---------------------|----------------------|
| "Endpoint accepts: site_id, report_date..." | API: `POST /api/v1/reports` | Request body schema with validation rules |
| "Enforces unique constraint: one report per site_id + report_date" | Database: `daily_reports` table | Unique index on `(site_id, report_date)` |
| "Supports partial updates (PATCH) only when report status is DRAFT" | API: `PATCH /api/v1/reports/{id}` | Conditional check in service layer, 403 if status != DRAFT |
| "Accepts multipart/form-data POST with max 10 files, 10MB each" | API: `POST /api/v1/reports/{id}/photos` | Middleware validation: `multer` equivalent with limits |
| "Strips ALL EXIF metadata using ImageMagick" | Service: `FileProcessor` (Go worker) | `github.com/barasher/go-exiftool` or ImageMagick binding |
| "Queues file for async virus scanning (ClamAV)" | Queue: `file.processing` stream (Redis) | Consumer calls ClamAV daemon via TCP socket |
| "Stores files in S3-compatible object storage" | Infrastructure: MinIO Cluster | Bucket: `sitelog-photos`, versioning disabled |
| "Generates presigned GET URLs (15-minute expiry)" | API: `GET /api/v1/reports/{id}/photos/{photo_id}/url` | MinIO PresignedGetObject with 15m expiry |
| "Implements strict state machine: DRAFT → SUBMITTED → APPROVED/REJECTED" | Database: `daily_reports.status` + Service layer | CHECK constraint + state transition validation |
| "Generates cryptographic signature: SHA-256 HMAC..." | Service: `SignatureService` | HMAC-SHA256 of canonical JSON payload |
| "Stores signature... in separate signatures table (append-only)" | Database: `signatures` table | INSERT only, no UPDATE/DELETE permissions via RLS |
| "Implements optimistic locking: requires If-Match header" | API: All mutation endpoints | ETag comparison against `reports.version` column |
| "JWT-based authentication (RS256 algorithm)" | Infrastructure: Kong Plugin + Service middleware | `kong-plugin-jwt-signer` with JWKS endpoint |
| "Three distinct roles: VIEWER, SUPERVISOR, ADMIN" | Database: `users.role` enum + Middleware | Casbin or custom RBAC middleware |
| "Site-scoped permissions... returns 404 (not 403) for resources outside scope" | Service: `AuthorizationMiddleware` | Query user_site_assignments before resource lookup |
| "GET endpoint requires site_id filter (mandatory)" | API: `GET /api/v1/reports` | 400 Bad Request if site_id query param missing |

**Flagged Requirements**: None. All PRD requirements implementable with chosen stack.

---

## 2. System Architecture

### C4 Level 3 (Component) Diagram Description

**Container**: SiteLog API Service (Go 1.21)
- **Component**: `AuthMiddleware` - Validates RS256 JWT, extracts claims (user_id, roles), enforces token expiry
- **Component**: `RBACEnforcer` - Queries `user_site_assignments` table for every request, caches in Redis (TTL: 60s)
- **Component**: `ReportController` - Handles CRUD, implements optimistic locking via ETag/If-Match
- **Component**: `PhotoController` - Handles multipart upload, validates MIME types, publishes to processing queue
- **Component**: `SignatureController` - Manages state machine transitions, generates HMAC signatures
- **Component**: `FileProcessor` (Background Worker) - Consumes Redis Streams, strips EXIF with `exiftool`, virus scans with ClamAV, uploads to MinIO
- **Component**: `AuditLogger` - Append-only writes to `signatures` table, structured logging to stdout (JSON)

**Container**: PostgreSQL 15 (Primary + 2 Replicas)
- **Component**: `reports_db` - Main transactional database
- **Component**: `pg_crypto` extension - For UUID generation and hashing functions

**Container**: Redis 7 Cluster
- **Component**: `session_store` - JWT refresh token rotation (single-use)
- **Component**: `rate_limiter` - Sliding window counters per API key
- **Component**: `file_queue` - Redis Stream for async processing

**Container**: MinIO Cluster (S3-compatible)
- **Component**: `photo_storage` - Object storage with WORM (Write Once Read Many) compliance mode for approved reports

**Container**: ClamAV Daemon
- **Component**: `virus_scanner` - TCP socket listener on port 3310, streaming scan interface

### Data Flow: Photo Upload (Critical Path)

1. **Client** → `POST /api/v1/reports/{id}/photos` (multipart/form-data) → **Kong Gateway** (JWT validation, rate limit: 10 req/min)
2. **Kong** → **SiteLog API** → `PhotoController` validates MIME type (magic number check, not extension), file size ≤10MB
3. **API** writes to `photos` table with `status=PENDING`, returns 202 Accepted with `photo_id`
4. **API** publishes message to Redis Stream `file.processing` with `photo_id`, `temp_path`
5. **FileProcessor** worker picks up message:
   - Strips EXIF: `exiftool -all= -overwrite_original temp_file`
   - Virus scan: ClamAV `INSTREAM` command over TCP
   - If clean: Upload to MinIO `sitelog-photos/{uuid}.jpg`, update `photos.status=ACTIVE`, `storage_key={uuid}`
   - If infected: Update `photos.status=QUARANTINED`, delete temp file, emit alert
6. **Client** polls `GET /api/v1/reports/{id}/photos/{photo_id}` until `status=ACTIVE`
7. **Retrieval**: Client calls `GET .../url` endpoint → API generates MinIO presigned URL (15min expiry) → Client fetches directly from MinIO

### External Dependencies & SLAs

| Dependency | SLA Requirement | Failure Mode |
|------------|----------------|--------------|
| PostgreSQL Primary | 99.99% availability | Read replica promotion (automated via Patroni) |
| MinIO | 99.9% availability | Circuit breaker returns 503, queue files locally for retry |
| ClamAV | Best effort (async) | Timeout after 30s, mark for manual review |
| Redis | 99.95% availability | Fallback to in-memory rate limiting (degraded mode) |

---

## 3. Tech Stack Decision Record

### Frontend Layer
**Not applicable** - Pure API service. Clients are mobile apps/web SPA.

### API Gateway Layer
**Chosen**: Kong Gateway 3.5 (OSS)
- **Plugins**: `jwt`, `rate-limiting` (Redis backed), `cors`, `request-transformer`
- **Rejected**: Nginx + Lua (OpenResty) - Lacks native JWKS rotation support; AWS API Gateway - Vendor lock-in, expensive at scale
- **Scale Limit**: 50,000 req/sec per Kong node; horizontally scalable

### Backend Layer
**Chosen**: Go 1.21 (Golang)
- **Framework**: `gin-gonic/gin` (HTTP router) + `uber-go/fx` (dependency injection)
- **ORM**: `gorm.io/gorm` v2 (PostgreSQL dialect)
- **Rejected**: Node.js/TypeScript - Weak compile-time safety for cryptographic operations; Python/Django - GIL limits concurrent file processing throughput; Java/Spring Boot - Memory overhead too high for containerized deployment
- **Scale Limit**: 100,000 concurrent connections per pod (Go routines); CPU-bound on crypto operations (HMAC)

### Database Layer
**Chosen**: PostgreSQL 15.4
- **Extensions**: `pgcrypto`, `uuid-ossp`, `btree_gist`
- **Rejected**: MongoDB - Cannot guarantee ACID for financial/legal audit trails; MySQL 8 - Inferior partial index support for soft-delete queries; CockroachDB - Overkill for single-region deployment
- **Scale Limit**: 10,000 writes/sec on db.r6g.2xlarge; partition `signatures` table by year when exceeding 100M rows

### Cache Layer
**Chosen**: Redis 7.2 (Cluster Mode)
- **Rejected**: Memcached - No persistence for refresh tokens; Hazelcast - Operational complexity
- **Scale Limit**: 1M ops/sec per shard; shard by `user_id` hash slot

### Queue Layer
**Chosen**: Redis Streams (built into Redis 7)
- **Rejected**: RabbitMQ - Additional operational overhead; Kafka - Overkill for <10k messages/day; AWS SQS - Latency too high for EXIF stripping (need <2s processing)
- **Consumer**: `go-redis` XReadGroup with auto-claim for poison pills

### Object Storage
**Chosen**: MinIO 2024 (S3-compatible) or AWS S3
- **Compliance**: S3 Object Lock (WORM) for approved report photos
- **Rejected**: NFS - No presigned URL capability; Ceph - Operational complexity

### Infrastructure
**Chosen**: Kubernetes (EKS 1.28) or GKE
- **Service Mesh**: Linkerd (mTLS between services)
- **Rejected**: ECS Fargate - Cold start latency; Nomad - Smaller ecosystem

---

## 4. API Contract (OpenAPI 3.0)

```yaml
openapi: 3.0.3
info:
  title: SiteLog API
  version: 1.0.0
  description: Construction Daily Reporting System with Immutable Audit Trails

servers:
  - url: https://api.sitelog.io/v1

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: RS256 signed JWT with claims sub, role, sites[]

  schemas:
    Error:
      type: object
      required: [error_code, message, request_id]
      properties:
        error_code:
          type: string
          example: "CONCURRENT_MODIFICATION"
        message:
          type: string
          example: "Resource modified by another request"
        field_details:
          type: array
          items:
            type: object
            properties:
              field:
                type: string
              message:
                type: string
        request_id:
          type: string
          format: uuid
          example: "550e8400-e29b-41d4-a716-446655440000"

    DailyReport:
      type: object
      required: [id, site_id, report_date, status, created_at]
      properties:
        id:
          type: string
          format: uuid
