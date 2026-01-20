# Research: Add comprehensive API documentation

**Date**: 2026-01-20
**Item**: 021-add-comprehensive-api-documentation

## Research Question
API components exist but lack documentation, making integration difficult.

**Motivation:** Enables users to understand and integrate with the API effectively.

**Signals:** priority: low

## Summary

The AutoDev project includes a basic HTTP API server (`internal/api/`) built with the chi router, but it currently lacks comprehensive documentation. The API is minimal with only a single `/healthz` endpoint documented in code but not in user-facing documentation. The API server is described in ARCHITECTURE.md as "Optional REST API server" for "external control," but there's no API reference, usage examples, or integration guide.

Based on the codebase analysis, the API documentation should include:
1. **API Reference**: Document the `/healthz` endpoint with request/response examples
2. **Configuration Guide**: Explain how to configure and run the API server (port, timeouts, env vars)
3. **Integration Examples**: Show how to start the server and make requests
4. **Architecture Context**: Explain the API's role as an optional external control interface
5. **Future Expansion**: Document the extensibility pattern for adding new endpoints

The documentation should follow existing patterns in `docs/ARCHITECTURE.md` and `docs/OPERATIONS.md`, using clear structure with code examples and tables where appropriate.

## Current State Analysis

### Existing Implementation

The API server is a minimal HTTP server built with [chi v5](https://github.com/go-chi/chi) with the following characteristics:

**Location**: `/Users/simo/Projects/autodev/internal/api/`

**Files**:
- `server.go` (79 lines) - HTTP server lifecycle management
- `router.go` (28 lines) - Route registration with chi router
- `server_test.go` (284 lines) - Comprehensive server lifecycle tests
- `router_test.go` (20 lines) - Basic endpoint tests

**Current Endpoints**:
1. `GET /healthz` - Health check endpoint returning `{"status": "ok"}`

**Middleware Stack** (from `router.go:13-16`):
- `RequestID` - Unique request ID generation
- `RealIP` - Real IP extraction from headers
- `Logger` - Request logging
- `Recoverer` - Panic recovery

**Configuration** (from `server.go:14-19`):
```go
type Config struct {
    Addr         string          // Bind address (default: ":8080")
    ReadTimeout  time.Duration   // Default: 5 seconds
    WriteTimeout time.Duration   // Default: 5 seconds
    IdleTimeout  time.Duration   // Default: 60 seconds
}
```

**Dependencies** (from `server.go:22`):
```go
type Dependencies struct{}  // Currently empty, designed for future expansion
```

**Entry Point**: `/Users/simo/Projects/autodev/cmd/api/main.go` (58 lines)
- Creates server with `api.NewServer()`
- Configurable via `APRD_API_ADDR` environment variable
- Implements graceful shutdown with signal handling

### Key Files

- `/Users/simo/Projects/autodev/internal/api/server.go:10-79` - Core server implementation with Config struct, Server type, and lifecycle methods
- `/Users/simo/Projects/autodev/internal/api/router.go:1-28` - Router setup with chi middleware and `/healthz` endpoint
- `/Users/simo/Projects/autodev/cmd/api/main.go:1-58` - API server binary entry point
- `/Users/simo/Projects/autodev/go.mod:11` - Chi router dependency declaration
- `/Users/simo/Projects/autodev/docs/ARCHITECTURE.md:64` - Brief mention of API server as optional component

### Current Patterns and Conventions

**Code Documentation Style**:
- Go godoc comments on all exported types and functions (server.go:10-72)
- Test comments explaining rationale (e.g., server_test.go:121 "Can't use t.Parallel() here as we're testing actual server lifecycle")
- Clear struct field documentation in Config type

**Documentation Patterns** (from existing docs):
- `docs/ARCHITECTURE.md` uses Markdown with code blocks, ASCII diagrams, and tables
- `docs/OPERATIONS.md` uses tables for key bindings, environment variables, and settings
- Both use clear section headers with ## and ### levels
- Code examples with bash/shell syntax
- File references in format `path/to/file:line`

**Configuration Pattern**:
- Environment variables use `APRD_` prefix (main.go:16)
- Default values provided when config is empty
- Configuration struct designed for YAML integration (see `internal/config/config.go`)

## Technical Considerations

### Dependencies

**External Dependencies**:
- `github.com/go-chi/chi/v5` v5.0.10 - HTTP router (already in go.mod)
- Standard library `net/http` - HTTP server/client

**Internal Modules**:
- `internal/api` - API server package
- `internal/config` - Configuration system (for future integration)
- Potentially `internal/runner` - For controlling Python subprocess (future endpoints)

### Patterns to Follow

1. **Documentation Structure**: Match `docs/ARCHITECTURE.md` and `docs/OPERATIONS.md`
   - Use clear hierarchy: ## Main sections, ### Subsections
   - Include code examples with syntax highlighting
   - Use tables for configuration options and endpoints
   - Add file:line references for implementation details

2. **Go Documentation Conventions**:
   - Maintain existing godoc comments on all exports
   - Add usage examples in doc comments (following Go example comment format)
   - Consider adding Example functions for godoc (e.g., `ExampleServer_Start`)

3. **API Documentation Best Practices**:
   - Document each endpoint with method, path, parameters, response
   - Include example requests/responses with curl or HTTP syntax
   - Show status codes and error responses
   - Provide integration examples in multiple languages (Go, curl, Python)

4. **Configuration Documentation**:
   - Follow pattern from `docs/OPERATIONS.md:46-85` (config file settings)
   - Document all Config fields with types and defaults
   - Show environment variable overrides
   - Include YAML configuration examples

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| API is minimal/early-stage | Medium | Document current state accurately, indicate future expansion plans |
| API design may change | Medium | Add disclaimer about API stability/versioning |
| Documentation may become outdated | Low | Keep docs close to code (file references), add CI check for doc coverage |
| Unclear use cases for API | Low | Interview stakeholders or add issue tracking for API requirements |
| Missing OpenAPI/Swagger spec | Low | Consider adding swaggo/swag for automated spec generation in future |

## Recommended Approach

Based on research findings, here's the recommended approach:

### Phase 1: Create API Documentation File

**Create**: `/Users/simo/Projects/autodev/docs/API.md`

Include sections:
1. **Overview** - What the API is for, current state
2. **Quick Start** - How to run the API server
3. **Endpoints Reference** - Document `/healthz` endpoint
4. **Configuration** - Server config options and env vars
5. **Integration Examples** - Code examples in Go, curl, Python
6. **Architecture** - How it fits into the system (refer to ARCHITECTURE.md)
7. **Future Expansion** - How to add new endpoints (extensibility)

### Phase 2: Update Existing Documentation

**Update**: `/Users/simo/Projects/autodev/README.md`
- Add section about the API server
- Link to `docs/API.md`

**Update**: `/Users/simo/Projects/autodev/docs/ARCHITECTURE.md:64`
- Expand the brief API server mention
- Link to comprehensive API documentation

### Phase 3: Enhance Code Documentation

**Add to**: `/Users/simo/Projects/autodev/internal/api/`
- Add package-level godoc comment (package api)
- Add example usage in server.go doc comments
- Consider adding Example_test.go files for godoc examples

### Phase 4: Consider Future Enhancements (Out of Scope for Now)

- Add OpenAPI/Swagger specification using swaggo/swag
- Add `/api` prefix to all routes for versioning
- Implement `Dependencies` struct for real dependency injection
- Add endpoints for: status, configuration, log streaming

## Open Questions

1. **API Purpose**: What is the intended use case for the API server?
   - Currently only has health check
   - ARCHITECTURE.md mentions "external control" but no details
   - Should we interview stakeholders to understand requirements?

2. **API Stability**: Should the API be considered:
   - Experimental/internal only?
   - Stable with versioning?
   - This affects documentation tone and backwards compatibility commitments

3. **Future Endpoints**: Are there planned endpoints beyond `/healthz`?
   - Status monitoring (TUI state, runner status)?
   - Configuration management?
   - Triggering automation runs?
   - This should be documented as "Planned" if known

4. **Authentication**: Will the API require authentication?
   - Currently no auth middleware
   - Should document if/when this is added

5. **Documentation Format**: Should we use:
   - Markdown (current repo standard)?
   - OpenAPI/Swagger spec (industry standard)?
   - Both (Markdown generated from spec)?

## Appendix: Code Analysis Details

### Current API Code Structure

```
internal/api/
├── server.go         (79 lines) - Server lifecycle, Config, Server type
├── router.go         (28 lines) - Chi router with /healthz endpoint
├── server_test.go   (284 lines) - Comprehensive lifecycle tests
└── router_test.go    (20 lines) - Basic endpoint test

cmd/api/
└── main.go           (58 lines) - Server binary entry point
```

### Test Coverage

From CODEBASE_ANALYSIS_REPORT.md:
- `internal/api/` coverage: ~30%
- Gaps: Server lifecycle testing (though server_test.go exists)

### Configuration Integration

The API server currently does NOT integrate with the main config system (`internal/config/`):
- Config is passed directly to `api.NewServer()` in cmd/api/main.go
- No YAML configuration support
- Hardcoded default port `:8080` (mentioned in PLAN.md as issue)

### Dependencies Injection Pattern

The `Dependencies` struct is currently empty:
```go
type Dependencies struct{}  // Designed for future DI
```

This suggests the API was designed to be extended with dependencies like:
- Database access
- Config store
- Process runner control
- Logger

### Chi Router Features

The project uses chi v5.0.10 with middleware:
- `middleware.RequestID` - Adds X-Request-ID header
- `middleware.RealIP` - Gets real IP from X-Forwarded-For
- `middleware.Logger` - Logs HTTP requests
- `middleware.Recoverer` - Catches panics

Common chi features NOT currently used:
- `middleware.StripSlashes` - Normalize URL paths
- `middleware.AllowContentType` - Validate Content-Type
- `middleware.Compress` - Gzip compression
- `middleware.Timeout` - Request timeout
- `middleware.Throttle` - Rate limiting

### Health Endpoint Implementation

Current implementation (router.go:23-28):
```go
func healthHandler(w http.ResponseWriter, _ *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusOK)
    _ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}
```

Notes:
- Returns 200 OK always
- JSON response: `{"status": "ok"}`
- No health checks (database, dependencies, etc.)
- Discards encoding error with `_` (common pattern for simple handlers)

### Server Lifecycle

From cmd/api/main.go:26-57:
1. Create server with config
2. Start in goroutine
3. Wait for SIGINT/SIGTERM
4. Shutdown with 5-second timeout
5. Exit

Pattern matches standard Go HTTP server best practices.

### Integration Points

Potential future integration points:
1. **Config System** - `internal/config/config.go`
   - Could add API server config section
   - YAML configuration for port, timeouts, etc.

2. **Runner** - `internal/runner/runner.go`
   - Could expose runner status endpoint
   - Could trigger automation runs via API

3. **TUI** - `internal/tui/model.go`
   - Could expose current state/status
   - Could control TUI via API (headless mode)

4. **Python Harness** - `tools/auto_prd/`
   - Could provide REST interface to Python automation
   - Could expose tracker status, progress, etc.
