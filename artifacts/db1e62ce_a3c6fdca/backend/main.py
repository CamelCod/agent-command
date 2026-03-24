**Contract Mapping**

| Contract Endpoint | Implementation | File:Line | HTTP Method | Status Codes |
|------------------|----------------|-----------|-------------|--------------|
| `POST /api/v1/reports` | Create daily report | `handler/report.go:45` | POST | 201, 400, 401, 409, 422 |
| `GET /api/v1/reports/{id}` | Retrieve report with photos | `handler/report.go:78` | GET | 200, 401, 404 |
| `PATCH /api/v1/reports/{id}` | Partial update (DRAFT only) | `handler/report.go:110` | PATCH | 200, 400, 401, 403, 404, 409, 412 |
| `DELETE /api/v1/reports/{id}` | Delete report (DRAFT only) | `handler/report.go:155` | DELETE | 204, 401, 403, 404, 412 |
| `POST /api/v1/reports/{id}/submit` | Transition to SUBMITTED | `handler/report.go:185` | POST | 200, 401, 403, 404, 409 |
| `POST /api/v1/reports/{id}/approve` | Transition to APPROVED | `handler/report.go:215` | POST | 200, 401, 403, 404 |
| `POST /api/v1/reports/{id}/reject` | Transition to REJECTED | `handler/report.go:245` | POST | 200, 401, 403, 404 |
| `POST /api/v1/reports/{id}/photos` | Multipart upload (max 10, 10MB) | `handler/photo.go:52` | POST | 201, 400, 401, 403, 404, 413, 422 |
| `DELETE /api/v1/reports/{id}/photos/{photo_id}` | Remove photo (DRAFT only) | `handler/photo.go:110` | DELETE | 204, 401, 403, 404 |
| `GET /api/v1/reports/{id}/photos/{photo_id}/url` | Presigned URL (15m expiry) | `handler/photo.go:145` | GET | 200, 401, 404 |
| `POST /api/v1/reports/{id}/sign` | HMAC-SHA256 signature | `handler/signature.go:40` | POST | 201, 400, 401, 403, 404, 409 |
| `GET /api/v1/reports/{id}/signatures` | List signatures (append-only) | `handler/signature.go:85` | GET | 200, 401, 404 |
| `POST /auth/login` | JWT + refresh token issuance | `handler/auth.go:35` | POST | 200, 400, 401, 429 |
| `POST /auth/refresh` | Token refresh rotation | `handler/auth.go:95` | POST | 200, 401, 429 |
| `POST /auth/logout` | Revoke refresh token | `handler/auth.go:145` | POST | 204, 401 |
| `GET /health` | Liveness probe | `handler/health.go:15` | GET | 200 |
| `GET /ready` | Readiness probe (DB/Redis/MinIO) | `handler/health.go:35` | GET | 200, 503 |

**Project Structure**

```
sitelog-api/
├── cmd/
│   └── server/
│       └── main.go                    # Application entry point
├── internal/
│   ├── config/
│   │   └── config.go                  # Environment validation & struct
│   ├── domain/
│   │   ├── models.go                  # GORM entities + constraints
│   │   └── enums.go                   # Status enums + validation
│   ├── repository/
│   │   └── postgres.go                # Database connection & migrations
│   ├── service/
│   │   ├── report.go                  # Business logic & state machine
│   │   ├── photo.go                   # Upload orchestration
│   │   ├── signature.go               # HMAC generation & storage
│   │   └── auth.go                    # JWT & refresh token management
│   ├── handler/
│   │   ├── report.go                  # HTTP handlers (REST)
│   │   ├── photo.go                   # Multipart handling
│   │   ├── signature.go               # Signature endpoints
│   │   ├── auth.go                    # Authentication endpoints
│   │   └── health.go                  # Health checks
│   ├── middleware/
│   │   ├── auth.go                    # JWT verification
│   │   ├── error.go                   # RFC 7807 error handling
│   │   ├── logging.go                 # Structured JSON logging
│   │   ├── rate_limit.go              # Redis-backed rate limiting
│   │   └── optimistic_lock.go         # ETag/If-Match handling
│   ├── infrastructure/
│   │   ├── storage/
│   │   │   └── minio.go               # S3-compatible object storage
│   │   ├── queue/
│   │   │   └── redis.go               # Async job queue (Asynq)
│   │   ├── crypto/
│   │   │   └── hmac.go                # SHA-256 HMAC operations
│   │   └── scanner/
│   │       └── clamav.go              # ClamAV TCP socket client
│   └── worker/
│       └── processor.go               # Background job handlers
├── pkg/
│   ├── validator/
│   │   └── validator.go               # Request validation helpers
│   └── errors/
│       └── errors.go                  # RFC 7807 Problem Details
├── migrations/
│   ├── 001_initial_schema.sql         # Tables, indexes, constraints
│   └── 002_rls_policies.sql           # Row Level Security for signatures
├── Dockerfile
└── go.mod
```

**Configuration**

```go
// internal/config/config.go
package config

import (
	"fmt"
	"os"
	"strconv"
	"time"

	"github.com/go-playground/validator/v10"
)

type Config struct {
	Server   ServerConfig   `validate:"required"`
	Database DatabaseConfig `validate:"required"`
	Redis    RedisConfig    `validate:"required"`
	MinIO    MinIOConfig    `validate:"required"`
	ClamAV   ClamAVConfig   `validate:"required"`
	Auth     AuthConfig     `validate:"required"`
}

type ServerConfig struct {
	Port         string        `validate:"required" env:"SERVER_PORT"`
	ReadTimeout  time.Duration `validate:"required" env:"SERVER_READ_TIMEOUT"`
	WriteTimeout time.Duration `validate:"required" env:"SERVER_WRITE_TIMEOUT"`
	Environment  string        `validate:"required,oneof=development staging production" env:"ENV"`
}

type DatabaseConfig struct {
	Host     string `validate:"required" env:"DB_HOST"`
	Port     int    `validate:"required" env:"DB_PORT"`
	User     string `validate:"required" env:"DB_USER"`
	Password string `validate:"required" env:"DB_PASSWORD"`
	Name     string `validate:"required" env:"DB_NAME"`
	SSLMode  string `validate:"required" env:"DB_SSLMODE"`
	PoolSize int    `validate:"required,min=5" env:"DB_POOL_SIZE"`
}

type RedisConfig struct {
	Host     string `validate:"required" env:"REDIS_HOST"`
	Port     int    `validate:"required" env:"REDIS_PORT"`
	Password string `env:"REDIS_PASSWORD"`
	DB       int    `env:"REDIS_DB"`
}

type MinIOConfig struct {
	Endpoint        string `validate:"required" env:"MINIO_ENDPOINT"`
	AccessKeyID     string `validate:"required" env:"MINIO_ACCESS_KEY"`
	SecretAccessKey string `validate:"required" env:"MINIO_SECRET_KEY"`
	BucketName      string `validate:"required" env:"MINIO_BUCKET"`
	UseSSL          bool   `env:"MINIO_USE_SSL"`
}

type ClamAVConfig struct {
	Host string `validate:"required" env:"CLAMAV_HOST"`
	Port int    `validate:"required" env:"CLAMAV_PORT"`
}

type AuthConfig struct {
	JWTSecret          string        `validate:"required,min=32" env:"JWT_SECRET"`
	AccessTokenExpiry  time.Duration `validate:"required" env:"ACCESS_TOKEN_EXPIRY"`
	RefreshTokenExpiry time.Duration `validate:"required" env:"REFRESH_TOKEN_EXPIRY"`
	HMACSecret         string        `validate:"required,min=32" env:"HMAC_SECRET"`
}

func Load() (*Config, error) {
	cfg := &Config{
		Server: ServerConfig{
			Port:         getEnv("SERVER_PORT", "8080"),
			ReadTimeout:  getDurationEnv("SERVER_READ_TIMEOUT", 5*time.Second),
			WriteTimeout: getDurationEnv("SERVER_WRITE_TIMEOUT", 10*time.Second),
			Environment:  getEnv("ENV", "development"),
		},
		Database: DatabaseConfig{
			Host:     getEnv("DB_HOST", "localhost"),
			Port:     getIntEnv("DB_PORT", 5432),
			User:     getEnv("DB_USER", "sitelog"),
			Password: getEnv("DB_PASSWORD", ""),
			Name:     getEnv("DB_NAME", "sitelog"),
			SSLMode:  getEnv("DB_SSLMODE", "disable"),
			PoolSize: getIntEnv("DB_POOL_SIZE", 10),
		},
		Redis: RedisConfig{
			Host:     getEnv("REDIS_HOST", "localhost"),
			Port:     getIntEnv("REDIS_PORT", 6379),
			Password: getEnv("REDIS_PASSWORD", ""),
			DB:       getIntEnv("REDIS_DB", 0),
		},
		MinIO: MinIOConfig{
			Endpoint:        getEnv("MINIO_ENDPOINT", "localhost:9000"),
			AccessKeyID:     getEnv("MINIO_ACCESS_KEY", ""),
			SecretAccessKey: getEnv("MINIO_SECRET_KEY", ""),
			BucketName:      getEnv("MINIO_BUCKET", "sitelog-photos"),
			UseSSL:          getBoolEnv("MINIO_USE_SSL", false),
		},
		ClamAV: ClamAVConfig{
			Host: getEnv("CLAMAV_HOST", "localhost"),
			Port: getIntEnv("CLAMAV_PORT", 3310),
		},
		Auth: AuthConfig{
			JWTSecret:          getEnv("JWT_SECRET", ""),
			AccessTokenExpiry:  getDurationEnv("ACCESS_TOKEN_EXPIRY", 15*time.Minute),
			RefreshTokenExpiry: getDurationEnv("REFRESH_TOKEN_EXPIRY", 7*24*time.Hour),
			HMACSecret:         getEnv("HMAC_SECRET", ""),
		},
	}

	validate := validator.New()
	if err := validate.Struct(cfg); err != nil {
		return nil, fmt.Errorf("config validation failed: %w", err)
	}

	return cfg, nil
}

func getEnv(key, defaultVal string) string { /* ... */ }
func getIntEnv(key string, defaultVal int) int { /* ... */ }
func getBoolEnv(key string, defaultVal bool) bool { /* ... */ }
func getDurationEnv(key string, defaultVal time.Duration) time.Duration { /* ... */ }
```

**Database Models**

```go
// internal/domain/models.go
package domain

import (
	"time"
	"github.com/google/uuid"
	"gorm.io/gorm"
)

type ReportStatus string

const (
	StatusDraft     ReportStatus = "DRAFT"
	StatusSubmitted ReportStatus = "SUBMITTED"
	StatusApproved  ReportStatus = "APPROVED"
	StatusRejected  ReportStatus = "REJECTED"
)

func (s ReportStatus) Valid() bool {
	switch s {
	case StatusDraft, StatusSubmitted, StatusApproved