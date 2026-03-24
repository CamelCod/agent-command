# Architecture: TaskFlow REST API

## 1. Requirements Traceability Matrix

| PRD Requirement (Quoted) | Technical Component | Implementation Details |
|-------------------------|---------------------|------------------------|
| "Passwords hashed using bcrypt (cost factor 12)" | `internal/auth/service.go` | `bcrypt.GenerateFromPassword(password, 12)` |
| "JWT access token (HS256 algorithm, 24-hour expiry)" | `internal/middleware/jwt.go` | `jwt.SigningMethodHS256`, `exp: time.Now().Add(24h)` |
| "