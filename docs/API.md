# AutoDev HTTP API

## Overview

The AutoDev HTTP API server provides an optional REST interface for external control and monitoring of the AutoDev system. It is built with the [chi v5](https://github.com/go-chi/chi) router and includes a standard middleware stack for request logging, panic recovery, and request tracking.

**Current State:** The API is currently **experimental** and may change as the system evolves. It exposes a single health check endpoint with plans for future expansion including status monitoring, configuration management, and runner control.

**Architecture:** The API server is designed as an optional component that can run independently of the TUI (`cmd/aprd`). It uses a lightweight middleware-first approach with an empty `Dependencies` struct designed for future dependency injection.

## Quick Start

### Building and Running

```bash
# Build the API server
make build

# Run with default configuration (:8080)
./bin/api

# Run with custom bind address
APRD_API_ADDR=:9090 ./bin/api

# Run with specific interface
APRD_API_ADDR=localhost:8080 ./bin/api
```

### Testing the Endpoint

```bash
# Test the health check endpoint
curl http://localhost:8080/healthz

# Response
{"status":"ok"}
```

### Building from Source

```bash
# Clone and build
git clone https://github.com/SimoKiihamaki/autodev.git
cd autodev
make build

# The binary will be at ./bin/api
```

## Endpoints Reference

### GET /healthz

Health check endpoint that returns the API server status.

**Request:**

```http
GET /healthz HTTP/1.1
Host: localhost:8080
```

**Response:**

```http
HTTP/1.1 200 OK
Content-Type: application/json
Date: Mon, 20 Jan 2026 00:00:00 GMT
Content-Length: 16

{"status":"ok"}
```

**Status Codes:**

- `200 OK` - Server is healthy and accepting requests

**Example:**

```bash
curl -i http://localhost:8080/healthz
```

**Response Headers:**

- `Content-Type: application/json` - Response body is JSON
- `X-Request-ID` - Unique request identifier (added by middleware)
- `Date` - Response timestamp

**Implementation:** `internal/api/router.go:23-28`

## Configuration

### Server Configuration

The API server accepts configuration via the `Config` struct:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `Addr` | `string` | `:8080` | Bind address for the HTTP server. Use `:8080` for all interfaces, `localhost:8080` for local only, or `0.0.0.0:8080` for explicit all-interfaces binding |
| `ReadTimeout` | `time.Duration` | `5s` | Maximum duration for reading the entire request, including the body |
| `WriteTimeout` | `time.Duration` | `5s` | Maximum duration for writing the response |
| `IdleTimeout` | `time.Duration` | `60s` | Maximum time to wait for the next request when keep-alives are enabled |

**Implementation:** `internal/api/server.go:14-19`

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `APRD_API_ADDR` | Override the default bind address | `APRD_API_ADDR=:9090 ./bin/api` |

**Implementation:** `cmd/api/main.go:16`

### Configuration Example

```go
package main

import (
    "github.com/SimoKiihamaki/autodev/internal/api"
    "time"
)

func main() {
    cfg := api.Config{
        Addr:         ":8080",
        ReadTimeout:  10 * time.Second,
        WriteTimeout: 10 * time.Second,
        IdleTimeout:  120 * time.Second,
    }
    deps := api.Dependencies{}
    server := api.NewServer(cfg, deps)

    // Start server (typically in a goroutine)
    go server.Start()
}
```

## Integration Examples

### Go

```go
package main

import (
    "encoding/json"
    "fmt"
    "io"
    "net/http"
)

type HealthResponse struct {
    Status string `json:"status"`
}

func main() {
    resp, err := http.Get("http://localhost:8080/healthz")
    if err != nil {
        panic(err)
    }
    defer resp.Body.Close()

    body, err := io.ReadAll(resp.Body)
    if err != nil {
        panic(err)
    }

    var health HealthResponse
    if err := json.Unmarshal(body, &health); err != nil {
        panic(err)
    }

    fmt.Printf("API Status: %s\n", health.Status)
    // Output: API Status: ok
}
```

### curl

```bash
# Basic request
curl http://localhost:8080/healthz

# With headers
curl -i http://localhost:8080/healthz

# Pretty-print JSON
curl http://localhost:8080/healthz | jq

# Check response headers
curl -I http://localhost:8080/healthz
```

### Python

```python
import requests

def check_health(base_url="http://localhost:8080"):
    """Check the API server health status."""
    try:
        response = requests.get(f"{base_url}/healthz")
        response.raise_for_status()
        data = response.json()
        print(f"API Status: {data['status']}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    health = check_health()
    # Output: API Status: ok
```

### Node.js (TypeScript)

```typescript
interface HealthResponse {
  status: string;
}

async function checkHealth(baseUrl: string = 'http://localhost:8080'): Promise<HealthResponse | null> {
  try {
    const response = await fetch(`${baseUrl}/healthz`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json() as HealthResponse;
    console.log(`API Status: ${data.status}`);
    return data;
  } catch (error) {
    console.error('Error:', error);
    return null;
  }
}

checkHealth();
// Output: API Status: ok
```

## Architecture

### Component Structure

```text
┌─────────────────────────────────────┐
│         cmd/api/main.go             │
│    (Server binary entry point)      │
│  - Signal handling (SIGINT/SIGTERM) │
│  - Graceful shutdown (5s timeout)   │
│  - Environment variable config      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     internal/api/server.go          │
│  (Server lifecycle & Config)        │
│  - Server construction              │
│  - Start/StartListener methods      │
│  - Shutdown with context            │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     internal/api/router.go          │
│  (Chi router + middleware)          │
│                                     │
│  ┌────────────────────────────────┐ │
│  │ Middleware Stack:              │ │
│  │ - RequestID (X-Request-ID)     │ │
│  │ - RealIP (X-Forwarded-For)     │ │
│  │ - Logger (stdout logging)      │ │
│  │ - Recoverer (panic recovery)   │ │
│  └────────────────────────────────┘ │
│                                     │
│  ┌────────────────────────────────┐ │
│  │ Endpoints:                     │ │
│  │ GET /healthz                   │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### Middleware Stack

The API server uses chi v5 middleware for cross-cutting concerns:

| Middleware | Purpose | Header/Effect |
|------------|---------|---------------|
| `RequestID` | Unique request tracking | Adds `X-Request-ID` header to all responses |
| `RealIP` | Client IP extraction | Reads from `X-Forwarded-For` or `X-Real-IP` |
| `Logger` | Request logging | Logs method, path, status, duration to stdout |
| `Recoverer` | Panic recovery | Catches panics and returns 500 Internal Server Error |

**Implementation:** `internal/api/router.go:13-16`

### Server Lifecycle

1. **Startup**
   - Create `Config` with address and timeouts
   - Create empty `Dependencies` struct (for future expansion)
   - Call `api.NewServer()` to construct the server
   - Start server in goroutine with `server.Start()`

2. **Request Handling**
   - Middleware chain processes each request
   - Router matches route and calls handler
   - Handler processes request and writes response
   - Middleware completes (logging, etc.)

3. **Graceful Shutdown**
   - Receive SIGINT or SIGTERM signal
   - Create shutdown context with 5-second timeout
   - Call `server.Shutdown(ctx)` to complete active requests
   - Exit program

**Implementation:** `cmd/api/main.go:26-57`

### Key Design Decisions

#### Chi Router

The API uses [chi v5](https://github.com/go-chi/chi), a lightweight, idiomatic Go HTTP router.

**Benefits:**
- Composable middleware design
- Net/http `ServeMux` compatibility
- URL parameters and wildcard support
- No external dependencies beyond standard library

#### Middleware-First Architecture

Cross-cutting concerns are handled at the router level using chi middleware:

```go
r.Use(middleware.RequestID)
r.Use(middleware.RealIP)
r.Use(middleware.Logger)
r.Use(middleware.Recoverer)
```

This pattern ensures all requests pass through the same middleware stack.

#### Empty Dependencies Struct

The `Dependencies` struct is currently empty:

```go
type Dependencies struct{}
```

**Purpose:** Designed for future dependency injection when adding endpoints that need:
- Runner control (start/stop automation)
- Config access (read/write configuration)
- Log streaming (tail log files)
- Status monitoring (check TUI state, runner status)

**Implementation:** `internal/api/server.go:22`

#### No Authentication

The API currently has no authentication middleware. All endpoints are publicly accessible.

**Future Consideration:** Authentication may be added using chi middleware such as:
- API key validation
- JWT token validation
- Basic auth
- OAuth2

## Development

### Adding New Endpoints

To add a new endpoint to the API:

1. **Define the handler function** in `internal/api/router.go`:

```go
func statusHandler(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusOK)
    _ = json.NewEncoder(w).Encode(map[string]string{
        "status": "running",
        "version": "1.0.0",
    })
}
```

2. **Register the route** in the `newRouter()` function:

```go
func newRouter(_ Dependencies) http.Handler {
    r := chi.NewRouter()
    r.Use(middleware.RequestID)
    r.Use(middleware.RealIP)
    r.Use(middleware.Logger)
    r.Use(middleware.Recoverer)

    r.Get("/healthz", healthHandler)
    r.Get("/status", statusHandler)  // New endpoint

    return r
}
```

3. **Add dependencies** (if needed) to the `Dependencies` struct:

```go
type Dependencies struct {
    Runner *runner.Runner
    Config *config.Config
}
```

4. **Update the server initialization** to pass dependencies:

```go
deps := api.Dependencies{
    Runner: runnerInstance,
    Config: configInstance,
}
server := api.NewServer(cfg, deps)
```

### Testing

The API server includes comprehensive tests:

```bash
# Run all API tests
go test ./internal/api/...

# Run with coverage
go test -cover ./internal/api/...

# Run with race detector
go test -race ./internal/api/...
```

**Test Files:**
- `internal/api/server_test.go` - Server lifecycle tests (284 lines)
- `internal/api/router_test.go` - Endpoint tests (20 lines)

### Testing Endpoints Manually

```bash
# Start the server
./bin/api

# In another terminal, test endpoints
curl http://localhost:8080/healthz

# Check response headers
curl -i http://localhost:8080/healthz

# View request ID
curl -v http://localhost:8080/healthz 2>&1 | grep X-Request-ID
```

### Running in Development

```bash
# Build and run
make build
./bin/api

# Or use make run (if defined)
make run

# Run with custom address
APRD_API_ADDR=localhost:9090 ./bin/api

# Run with verbose logging
APRD_API_ADDR=:8080 ./bin/api 2>&1 | tee api.log
```

## Future Expansion

### Planned Endpoints

The following endpoints are planned for future releases:

#### Status Monitoring

```http
GET /status
```

Returns the current status of the AutoDev system including:
- TUI state
- Runner status
- Active automation session
- Feature progress

#### Configuration Management

```http
GET /config
PUT /config
```

Read and update the AutoDev configuration.

#### Runner Control

```http
POST /runner/start
POST /runner/stop
GET /runner/status
```

Control the Python automation subprocess.

#### Log Streaming

```http
GET /logs/stream
```

Server-sent events (SSE) stream of log output.

### Extensibility Pattern

The `Dependencies` struct provides a clean dependency injection pattern for future expansion:

```go
// Future Dependencies struct
type Dependencies struct {
    Runner  *runner.Runner      // For runner control endpoints
    Config  *config.Config      // For config management
    Logger  *zap.Logger         // For structured logging
    Tracker *tracker.Tracker    // For progress tracking
}
```

This pattern allows:
- Testable code (inject mock dependencies)
- Clear dependency graph
- Flexible endpoint implementation
- No global state

### Versioning Strategy

Future API versions may use the `/api/v1/` prefix:

```text
/api/v1/healthz
/api/v1/status
/api/v1/config
```

Current endpoints (`/healthz`) will continue to work for backward compatibility.

## Troubleshooting

### Common Issues

#### "Address already in use"

```bash
# Check if port is in use
lsof -i :8080

# Use different port
APRD_API_ADDR=:8081 ./bin/api
```

#### "Connection refused"

```bash
# Verify server is running
ps aux | grep api

# Check server logs
./bin/api 2>&1 | tee api.log
```

#### "Timeout waiting for response"

```bash
# Increase timeouts in Config
cfg := api.Config{
    ReadTimeout:  30 * time.Second,
    WriteTimeout: 30 * time.Second,
}
```

### Debug Mode

Enable verbose logging:

```bash
# Run with verbose output
APRD_API_ADDR=:8080 ./bin/api 2>&1 | tee debug.log

# Check request logs in output
tail -f debug.log
```

### Health Check Failures

If the health check endpoint returns errors:

1. **Check server is running:**
   ```bash
   curl http://localhost:8080/healthz
   ```

2. **Verify no firewall blocking:**
   ```bash
   telnet localhost 8080
   ```

3. **Check server logs for errors:**
   ```bash
   ./bin/api 2>&1 | grep error
   ```

## Additional Resources

- **Architecture:** See [ARCHITECTURE.md](./ARCHITECTURE.md) for system architecture
- **Operations:** See [OPERATIONS.md](./OPERATIONS.md) for operational guidance
- **Chi Router:** [github.com/go-chi/chi](https://github.com/go-chi/chi)
- **Go HTTP Server:** [net/http documentation](https://pkg.go.dev/net/http)

## Stability Disclaimer

**The API is currently experimental and may change as the system evolves.**

While we strive to maintain backward compatibility, breaking changes may occur in minor releases. We recommend:

1. Pinning to a specific API version in production
2. Reviewing changelog for API changes before upgrading
3. Testing integrations thoroughly after updates
4. Providing feedback on API design and use cases

For the latest API documentation and updates, see [docs/API.md](./API.md).
