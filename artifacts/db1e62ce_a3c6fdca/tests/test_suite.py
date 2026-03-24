**PROBE ANALYSIS: CONSTRUCTION DAILY REPORTING SYSTEM**
**Domain Entities Identified**: `DailyReport`, `PhotoAttachment`, `DigitalSignature`, `Site`, `User`, `ReportStatus` (DRAFT/SUBMITTED/APPROVED/REJECTED), `AuditLog`
**API Surface**: 15 endpoints, 47 distinct status code/method combinations
**Frontend Surface**: 11 React components, 4 custom hooks with optimistic updates
**Output Budget**: ~800 lines projected. Sectional delivery initiated.

---

## 1. TEST INVENTORY TABLE

| Module | Type | Files Tested | Test Count | Coverage Target |
|--------|------|--------------|------------|-----------------|
| **Domain Logic** | Unit | `domain/models.go`, `domain/enums.go` | 24 | 95% |
| **Report Service** | Unit | `service/report.go` | 18 | 90% |
| **Signature Service** | Unit | `service/signature.go` | 12 | 100% |
| **Photo Validation** | Unit | `service/photo_validator.go` | 16 | 88% |
| **Status Transitions** | Property | `domain/state_machine.go` | 50 (fast-check) | 100% branches |
| **HTTP Handlers** | Integration | `handler/*.go` (all 15 endpoints) | 89 | 85% |
| **Database Repository** | Integration | `repository/report_repo.go` | 22 | 80% |
| **React Hooks** | Unit | `app/_hooks/*.ts` | 14 | 90% |
| **UI Components** | Unit | `components/report-*.tsx` | 28 | 75% |
| **Critical Flows** | E2E | `e2e/critical-flows.spec.ts` | 6 | N/A |
| **Offline Sync** | E2E | `e2e/offline.spec.ts` | 4 | N/A |
| **Load/Stress** | Performance | `k6/load-suite.js` | 3 | N/A |

**Total Estimated Tests**: 286

[CONTINUED]

---

## 2. BACKEND UNIT TESTS (Go)

### 2.1 Domain Models & State Machine (`domain/models_test.go`)

```go
package domain_test

import (
	"testing"
	"time"
	"math/rand"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"fast-check"
	"sitelog-api/internal/domain"
)

func TestReportStatusTransitions(t *testing.T) {
	tests := []struct {
		name      string
		from      domain.ReportStatus
		to        domain.ReportStatus
		allowed   bool
		operator  domain.UserRole
	}{
		{"DRAFT to SUBMITTED by supervisor", domain.DRAFT, domain.SUBMITTED, true, domain.SUPERVISOR},
		{"DRAFT to SUBMITTED by worker", domain.DRAFT, domain.SUBMITTED, false, domain.WORKER},
		{"SUBMITTED to APPROVED by manager", domain.SUBMITTED, domain.APPROVED, true, domain.MANAGER},
		{"SUBMITTED to APPROVED by supervisor", domain.SUBMITTED, domain.APPROVED, false, domain.SUPERVISOR},
		{"SUBMITTED to REJECTED by manager", domain.SUBMITTED, domain.REJECTED, true, domain.MANAGER},
		{"APPROVED to DRAFT (tamper attempt)", domain.APPROVED, domain.DRAFT, false, domain.SUPERVISOR},
		{"REJECTED to DRAFT (correction)", domain.REJECTED, domain.DRAFT, true, domain.SUPERVISOR},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			report := &domain.DailyReport{
				ID:        "test-123",
				Status:    tt.from,
				Version:   1,
				UpdatedAt: time.Now(),
			}
			
			err := report.TransitionTo(tt.to, tt.operator)
			if tt.allowed {
				require.NoError(t, err)
				assert.Equal(t, tt.to, report.Status)
				assert.Equal(t, 2, report.Version) // Optimistic locking bump
			} else {
				require.Error(t, err)
				assert.ErrorIs(t, err, domain.ErrInvalidTransition)
			}
		})
	}
}

// Property-based: Random state sequences should never reach invalid states
func TestReportStatusProperties(t *testing.T) {
	fc.Assert(t, fc.QuickCheck(func(seq []int) bool {
		report := &domain.DailyReport{Status: domain.DRAFT}
		states := []domain.ReportStatus{domain.DRAFT, domain.SUBMITTED, domain.APPROVED, domain.REJECTED}
		
		for _, idx := range seq {
			if idx < 0 || idx >= len(states) { continue }
			target := states[idx%len(states)]
			// Try transition (ignore errors, just check invariants)
			_ = report.TransitionTo(target, domain.SUPERVISOR)
			
			// Invariant: Once APPROVED, never DRAFT
			if report.Status == domain.APPROVED && target == domain.DRAFT {
				return false
			}
		}
		return true
	}, &fc.Config{MaxSuccess: 1000}))
}

func TestPhotoValidation_ConstructionEdgeCases(t *testing.T) {
	tests := []struct {
		name        string
		size        int64
		contentType string
		exifData    map[string]interface{}
		wantErr     error
	}{
		{"Valid JPEG", 5*1024*1024, "image/jpeg", map[string]interface{}{"DateTime": "2024:01:15"}, nil},
		{"Oversized (10MB+1)", 10*1024*1024 + 1, "image/jpeg", nil, domain.ErrFileTooLarge},
		{"Invalid format HEIC", 2*1024*1024, "image/heic", nil, domain.ErrInvalidFormat},
		{"Corrupted EXIF", 3*1024*1024, "image/jpeg", map[string]interface{}{"GPS": "invalid"}, domain.ErrCorruptedMetadata},
		{"Zero bytes", 0, "image/jpeg", nil, domain.ErrEmptyFile},
		{"Null content type", 1024, "", nil, domain.ErrInvalidFormat},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			photo := &domain.Photo{
				Size:        tt.size,
				ContentType: tt.contentType,
				ExifData:    tt.exifData,
			}
			err := photo.Validate()
			assert.ErrorIs(t, err, tt.wantErr)
		})
	}
}

func TestWeatherLog_BoundaryConditions(t *testing.T) {
	// OSHA requires records for extreme conditions
	tests := []struct {
		temp    float64
		wind    float64
		valid   bool
		oshaFlag bool
	}{
		{-40.0, 10.0, true, true},   // Extreme cold
		{50.0, 5.0, true, true},     // Extreme heat
		{20.0, 100.0, true, true},   // High wind (crane operations)
		{-50.0, 10.0, false, false}, // Below absolute minimum
		{60.0, 10.0, false, false},  // Above human survival
		{20.0, -5.0, false, false},  // Negative wind speed (data corruption)
	}

	for _, tt := range tests {
		t.Run(fmt.Sprintf("Temp%.1f_Wind%.1f", tt.temp, tt.wind), func(t *testing.T) {
			w := domain.WeatherLog{
				TemperatureC: tt.temp,
				WindSpeedKmh: tt.wind,
				RecordedAt:   time.Now(),
			}
			
			err := w.Validate()
			if tt.valid {
				require.NoError(t, err)
				assert.Equal(t, tt.oshaFlag, w.RequiresOSHAAlert())
			} else {
				require.Error(t, err)
			}
		})
	}
}
```

### 2.2 HMAC-SHA256 Signature Service (`service/signature_test.go`)

```go
package service_test

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"testing"
	"sitelog-api/internal/service"
)

func TestSignatureService_GenerateHMAC(t *testing.T) {
	svc := service.NewSignatureService("test-secret-key-32bytes-long")
	
	t.Run("Deterministic output", func(t *testing.T) {
		reportID := "report-123"
		payload := []byte("worker-attendance-data")
		
		sig1, err := svc.Sign(reportID, payload)
		require.NoError(t, err)
		
		sig2, err := svc.Sign(reportID, payload)
		require.NoError(t, err)
		
		assert.Equal(t, sig1.Signature, sig2.Signature)
		assert.Equal(t, "HMAC-SHA256", sig1.Algorithm)
		assert.WithinDuration(t, time.Now(), sig1.Timestamp, time.Second)
	})

	t.Run("Tamper detection", func(t *testing.T) {
		reportID := "report-456"
		payload := []byte("original-data")
		
		sig, _ := svc.Sign(reportID, payload)
		
		// Mutate payload
		payload[0] ^= 0xFF
		
		valid, err := svc.Verify(reportID, payload, sig.Signature)
		require.NoError(t, err)
		assert.False(t, valid, "Modified payload should fail verification")
	})

	t.Run("Different reports different signatures", func(t *testing.T) {
		payload := []byte("same-payload")
		
		sig1, _ := svc.Sign("report-A", payload)
		sig2, _ := svc.Sign("report-B", payload)
		
		assert.NotEqual(t, sig1.Signature, sig2.Signature, "Different report IDs must produce different signatures")
	})
}

// Mutation testing readiness: Changing == to != should fail tests
func TestSignatureService_VerifyMutationResistance(t *testing.T) {
	svc := service.NewSignatureService("secret")
	payload := []byte("test")
	sig, _ := svc.Sign("r1", payload)
	
	// Test should fail if implementation incorrectly compares strings
	valid, err := svc.Verify("r1", payload, sig.Signature)
	require.NoError(t, err)
	assert.True(t, valid, "Valid signature must be accepted")
}
```

[CONTINUED]

---

## 3. BACKEND INTEGRATION TESTS (Go + Testcontainers)

### 3.1 Full API Contract Suite (`integration/handler_test.go`)

```go
package integration_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/suite"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/modules/postgres"
	"github.com/testcontainers/testcontainers-go/wait"
	"sitelog-api/internal/config"
	"sitelog-api/internal/domain"
	"sitelog-api/internal/handler"
	"sitelog-api/internal/repository"
	"sitelog-api/internal/service"
)

type HandlerIntegrationSuite struct {
	suite.Suite
	pgContainer    *postgres.PostgresContainer
	minioContainer testcontainers.Container
	router         *gin.Engine
	db             *gorm.DB
	redisClient    *redis.Client
}

func (s *HandlerIntegrationSuite) SetupSuite() {
	ctx := context.Background()
	
	// Start PostgreSQL with migrations
	pg, err := postgres.Run(ctx, "postgres:15-alpine",
		postgres.WithDatabase("sitelog_test"),
		postgres.WithUsername("test"),
		postgres.WithPassword("test"),
		testcontainers.WithWaitStrategy(wait.ForLog("database system is ready to accept connections")),
	)
	s.Require().NoError(err)
	s.pgContainer = pg
	
	connStr, _ := pg.ConnectionString(ctx)
	db, err := gorm.Open(postgres.Open(connStr), &gorm.Config{})
	s.Require().NoError(err)
	s.db = db
	
	// Auto-migrate
	db.AutoMigrate(&domain.DailyReport{}, &domain.Photo{}, &domain.Signature{})
	
	// Setup handlers
	reportRepo := repository.NewReportRepository(db)
	photoRepo := repository.NewPhotoRepository(db)
	sigRepo := repository.NewSignatureRepository(db)
	
	reportSvc := service.NewReportService(reportRepo)
	photoSvc := service.NewPhotoService(photoRepo, nil) // MinIO mocked
	sigSvc := service.NewSignatureService("test-secret")
	
	reportHandler := handler.NewReportHandler(reportSvc)
	photoHandler := handler.NewPhotoHandler(photoSvc)
	sigHandler := handler.NewSignatureHandler(sigSvc)
	
	gin.SetMode(gin.TestMode)
	r := gin.New()
	
	// Routes matching contract
	v1 := r.Group("/api/v1")
	{
		v1.POST("/reports", reportHandler.Create)
		v1.GET("/reports/:id", reportHandler.Get)
		v1.PATCH("/reports/:id", reportHandler.Patch)
		v1.DELETE("/reports/:id", reportHandler.Delete)
		v1.POST("/reports/:id/submit", reportHandler.Submit)
		v1.POST("/reports/:id/approve", reportHandler.Approve)
		v1.POST("/reports/:id/reject", reportHandler.Reject)
		v1.POST("/reports/:id/photos", photoHandler.Upload)
		v1.DELETE("/reports/:id/photos/:photo_id", photoHandler.Delete)
		v1.GET("/reports/:id/photos/:photo_id/url", photoHandler.GetURL)
		v1.POST("/reports/:id/sign", sigHandler.Sign)
		v1.GET("/reports/:id/signatures", sigHandler.List)
	}
	
	s.router = r
}

func (s *HandlerIntegrationSuite) TearDownSuite() {
	ctx := context.Background()
	if s.pgContainer != nil {
		s.pgContainer.Terminate(ctx)
	}
}

func (s *HandlerIntegrationSuite) SetupTest() {
	// Clean tables before each test
	s.db.Exec("TRUNCATE photos, signatures, daily_reports CASCADE")
}

// Test POST /api/v1/reports (201, 400, 401, 409, 422)
func (s *HandlerIntegrationSuite) TestCreateReport() {
	s.Run("201 Created - Valid report", func() {
		req := map[string]interface{}{
			"site_id":     "site-123",
			"report_date": "2024-