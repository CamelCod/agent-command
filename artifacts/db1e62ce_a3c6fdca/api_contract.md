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
