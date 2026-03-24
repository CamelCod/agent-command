# PRD: SiteLog API - Construction Daily Reporting System

## 1. Product Vision
A REST API that digitizes construction daily field reports with immutable photo documentation and auditable supervisor approval workflows to replace paper-based site reporting and ensure OSHA-compliant record retention.

## 2. Target Users

**Primary User: Site Supervisor**
- **Problem**: Currently spends 45+ minutes daily on paper forms, risks losing photos, and faces delays getting physical signatures for official records.
- **Value**: Creates structured reports in <5 minutes with permanent photo evidence and instant digital sign-off.

**Secondary Users**: 
- **Project Managers**: Need real-time visibility into multi-site progress without physical site visits.
- **Safety Officers**: Require tamper-proof audit trails for OSHA inspections and incident investigations.
- **Field Workers**: Need to submit photo evidence without learning complex software.

## 3. Core Features (MVP)

### Feature 1: Daily Report CRUD
**User Story**: As a Site Supervisor, I want to create a structured daily report so that project progress is documented consistently and searchable.

**Acceptance Criteria**:
- Endpoint accepts: `site_id`, `report_date`, `weather_temp`, `weather_conditions` (enum: clear/cloudy/rain/snow/wind), `crew_count` (integer), `work_completed` (text, max 5000 chars), `safety_incidents` (text, optional), `equipment_used` (array of strings)
- System validates `site_id` exists and user has WRITE permission for that site
- Enforces unique constraint: one report per `site_id` + `report_date` combination; returns 409 Conflict if duplicate
- Automatically sets `created_at` and `updated_at` timestamps server-side (UTC)
- Returns 201 Created with `report_id` (UUIDv4) and full report object on success
- Supports partial updates (PATCH) only when report status is `DRAFT`

### Feature 2: Photo Upload & Security Processing
**User Story**: As a Site Supervisor, I want to attach photos to daily reports so that visual progress and safety conditions are permanently documented without exposing sensitive metadata.

**Acceptance Criteria**:
- Accepts `multipart/form-data` POST with maximum 10 files per request, 10MB per file
- Validates MIME type strictly: `image/jpeg` or `image/png` only; rejects 400 for other formats
- Strips ALL EXIF metadata (GPS coordinates, camera serial numbers, timestamps) using ImageMagick before storage
- Queues file for async virus scanning (ClamAV); if infected, quarantines file, deletes upload, and returns 422 with error message
- Stores files in S3-compatible object storage with UUIDv4 filename (no original filenames in storage keys)
- Associates photos to `report_id` in database with `original_filename` preserved for display only
- Generates presigned GET URLs (15-minute expiry) for retrieval; never exposes direct storage URLs
- Soft delete only: photos marked `is_deleted=true` but retained for 7-year compliance period

### Feature 3: Supervisor Sign-off Workflow
**User Story**: As a Site Supervisor, I want to digitally sign off on completed reports so that they become immutable legal records with non-repudiation guarantees.

**Acceptance Criteria**:
- Implements strict state machine: `DRAFT` → `SUBMITTED` → `APPROVED` or `REJECTED` (no skipping states)
- Only users with `SUPERVISOR` role can execute `DRAFT` → `SUBMITTED` transition
- Report becomes read-only (immutable content) once moved to `SUBMITTED`; returns 403 for any edit attempts
- Approval requires matching `supervisor_id` to report creator or explicit admin delegation record
- Generates cryptographic signature: SHA-256 HMAC of (`report_id` + `content_hash` + `timestamp` + `supervisor_id` + `ip_address`)
- Stores signature, `signed_at` timestamp, and `ip_address` in separate `signatures` table (append-only)
- Rejection requires mandatory `rejection_reason` text (minimum 10 characters) and returns report to `DRAFT` status
- Implements optimistic locking: requires `If-Match` header with ETag; returns 409 if concurrent modification detected
- Prevents double-approval: idempotent approval endpoint returns 200 for duplicate requests with identical signature

### Feature 4: Role-Based Access Control (RBAC)
**User Story**: As a Project Manager, I want to control who can view or modify reports so that sensitive construction data remains secure and compartmentalized by site.

**Acceptance Criteria**:
- JWT-based authentication (RS256 algorithm) with access tokens (1-hour expiry) and refresh tokens (7-day expiry, single-use rotation)
- Three distinct roles: `VIEWER` (read-only assigned sites), `SUPERVISOR` (read/write assigned sites), `ADMIN` (full access, user management)
- Site-scoped permissions: all endpoints validate user has active assignment to `site_id` in request; returns 403 if unauthorized
- Middleware validates JWT signature and role claims before every endpoint access
- Returns 401 for missing/invalid tokens, 403 for valid token but insufficient permissions, 404 (not 403) for resources outside user's site scope (security through obscurity)
- User-site assignments stored in join table; changes take effect immediately (no cached permissions)

### Feature 5: Report Retrieval & Filtering
**User Story**: As a Project Manager, I want to query historical reports so that I can track project progress and generate compliance documentation.

**Acceptance Criteria**:
- GET endpoint requires `site_id` filter (mandatory) plus optional: `start_date`, `end_date`, `status` (enum), `super