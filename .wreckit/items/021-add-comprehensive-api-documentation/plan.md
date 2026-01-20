# Add comprehensive API documentation Implementation Plan

## Overview
Create comprehensive API documentation for the AutoDev HTTP API server to enable users to understand and integrate with the API effectively. The API server currently exists but lacks user-facing documentation, making integration difficult.

## Current State Analysis

### What Exists Now
- **API Server Implementation**: `/Users/simo/Projects/autodev/internal/api/`
  - `server.go` (79 lines) - HTTP server lifecycle management with Config struct
  - `router.go` (28 lines) - Chi router with middleware stack
  - `server_test.go` (284 lines) - Comprehensive lifecycle tests
  - `router_test.go` (20 lines) - Basic endpoint tests
- **Entry Point**: `/Users/simo/Projects/autodev/cmd/api/main.go` (58 lines)
- **Single Endpoint**: `GET /healthz` returning `{"status": "ok"}`
- **Middleware Stack**: RequestID, RealIP, Logger, Recoverer
- **Configuration**: Bind address, timeouts via Config struct and `APRD_API_ADDR` env var

### What's Missing
- No user-facing API documentation
- No integration examples
- No configuration guide for the API server
- No explanation of API's role in the system
- README.md doesn't mention the API server
- ARCHITECTURE.md only briefly mentions it in one line

### Key Constraints Discovered
- **API is minimal**: Only health check endpoint exists currently
- **Early-stage design**: Dependencies struct is empty, designed for future expansion
- **No authentication**: Currently open, no auth middleware
- **Stability unclear**: API design may change as it's early-stage
- **Chi router v5.0.10**: Already in dependencies, used for routing

### Patterns to Follow
- **Documentation Style**: Match `docs/ARCHITECTURE.md` and `docs/OPERATIONS.md`
  - Use clear hierarchy (## Main sections, ### Subsections)
  - Include code examples with syntax highlighting
  - Use tables for configuration options and endpoints
  - Add file:line references for implementation details
- **Go Documentation**: Maintain existing godoc comments on all exports
- **Markdown Standards**: Repo uses Markdown for all documentation

## Desired End State

### Specification
1. **New API Documentation File**: `/Users/simo/Projects/autodev/docs/API.md`
   - Overview section explaining the API's purpose
   - Quick Start guide with runnable examples
   - Endpoints Reference with detailed documentation for `/healthz`
   - Configuration section with all Config fields and env vars
   - Integration Examples in Go, curl, and Python
   - Architecture section explaining API's role
   - Future Expansion section documenting extensibility patterns

2. **Updated README.md**: Add API server section with link to API.md

3. **Updated ARCHITECTURE.md**: Expand the brief API mention (line 64) to link to API.md

4. **Enhanced Code Documentation**: Add package-level godoc comment to `internal/api/`

### Verification
- API.md follows same structure and style as ARCHITECTURE.md and OPERATIONS.md
- All code examples are accurate and tested
- All Config fields documented with types and defaults
- File references included with line numbers
- Links between documentation files work
- README mentions the API server

## What We're NOT Doing

- **NOT adding new API endpoints** - Only documenting existing `/healthz` endpoint
- **NOT implementing authentication** - Documenting current state (no auth)
- **NOT creating OpenAPI/Swagger spec** - Using Markdown (current repo standard)
- **NOT integrating with config system** - Documenting current direct configuration
- **NOT adding API versioning** - Documenting current single-version API
- **NOT adding monitoring/metrics endpoints** - Only documenting what exists
- **NOT changing API behavior** - Documentation-only changes

## Implementation Approach

The implementation is divided into 4 phases, each independently testable:

1. **Phase 1**: Create comprehensive API.md documentation
2. **Phase 2**: Update README.md to reference the API
3. **Phase 3**: Update ARCHITECTURE.md to expand API section
4. **Phase 4**: Add package-level godoc comment

This approach minimizes risk by:
- Starting with the main deliverable (API.md)
- Each phase can be independently verified
- Can stop after any phase if needed
- No code changes, only documentation

---

## Phase 1: Create API.md Documentation

### Overview
Create the main API documentation file following existing documentation patterns.

### Changes Required:

#### 1. Create API Documentation File
**File**: `/Users/simo/Projects/autodev/docs/API.md`
**Changes**: New file with comprehensive API documentation

**Structure**:
```markdown
# AutoDev HTTP API

## Overview
[What the API is for, current state, stability note]

## Quick Start
[How to build and run the API server]

## Endpoints Reference
### GET /healthz
[Request/response examples, status codes]

## Configuration
[Server config options, env vars, defaults table]

## Integration Examples
### Go
### curl
### Python
[Code examples for each]

## Architecture
[How API fits into the system, middleware stack]

## Development
[How to add new endpoints, testing]

## Future Expansion
[Extensibility pattern, Dependencies struct]
```

**Key Content**:
1. **Overview**: Explain API is optional REST server for external control, currently experimental with single health check endpoint
2. **Quick Start**: Build and run commands, default port `:8080`, env var `APRD_API_ADDR`
3. **Endpoints**: Document `/healthz` with method, path, response body, headers, example curl command
4. **Configuration**: Table with Config fields (Addr, ReadTimeout, WriteTimeout, IdleTimeout), types, defaults, env var overrides
5. **Integration Examples**:
   - Go: Using `http.Client` to call `/healthz`
   - curl: `curl http://localhost:8080/healthz`
   - Python: Using `requests` library
6. **Architecture**: Middleware stack (RequestID, RealIP, Logger, Recoverer), chi router, graceful shutdown pattern
7. **Development**: How to add endpoints (edit `router.go`), how to add dependencies (use Dependencies struct), testing patterns
8. **Future Expansion**: Document empty Dependencies struct designed for future dependency injection, potential endpoints (status, config, runner control)

**Style Guidelines**:
- Use `##` for main sections, `###` for subsections
- Code blocks with language tags: ```go, ```bash, ```python
- Tables for configuration: | Field | Type | Default | Description |
- File references: `internal/api/server.go:14-19`
- Link to ARCHITECTURE.md for system context
- Include stability disclaimer: "The API is currently experimental and may change"

### Success Criteria:

#### Automated Verification:
- [ ] File created at `/Users/simo/Projects/autodev/docs/API.md`
- [ ] Markdown is valid (no syntax errors)
- [ ] All code examples are syntactically correct
- [ ] All file references are accurate (file:line format)
- [ ] Internal links work (if any)

#### Manual Verification:
- [ ] Documentation follows same structure as ARCHITECTURE.md and OPERATIONS.md
- [ ] All Config fields from `server.go:14-19` are documented
- [ ] Environment variable `APRD_API_ADDR` from `main.go:16` is documented
- [ ] All middleware from `router.go:13-16` are listed
- [ ] Integration examples are accurate and runnable
- [ ] Stability disclaimer included
- [ ] Links to other docs (ARCHITECTURE.md, OPERATIONS.md) work

**Note**: Complete automated verification, then pause for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Update README.md

### Overview
Add API server section to README with link to comprehensive documentation.

### Changes Required:

#### 1. Update README.md
**File**: `/Users/simo/Projects/autodev/README.md`
**Changes**: Add API server section after existing features

**Add section** (after line 100, after "Live Feed at a Glance" section):
```markdown
## HTTP API Server

AutoDev includes an optional HTTP API server for external control and monitoring.
The API is currently experimental with a single health check endpoint.

See [docs/API.md](docs/API.md) for comprehensive API documentation including:
- Quick start guide
- Endpoints reference
- Configuration options
- Integration examples

**Quick start:**
```bash
make build
./bin/api
# Server runs on http://localhost:8080
curl http://localhost:8080/healthz
```
```

**Placement**: After "Live Feed at a Glance" section (around line 100), before "Requirements" section

**Content**: Brief overview, link to API.md, quick example

### Success Criteria:

#### Automated Verification:
- [ ] README.md updated
- [ ] Markdown is valid
- [ ] Link to docs/API.md is correct
- [ ] Code example is syntactically correct

#### Manual Verification:
- [ ] Section placement is logical (after Live Feed, before Requirements)
- [ ] Content is concise (doesn't duplicate API.md)
- [ ] Link works when clicked
- [ ] Code example is accurate and runnable

**Note**: Complete automated verification, then pause for manual confirmation before proceeding to Phase 3.

---

## Phase 3: Update ARCHITECTURE.md

### Overview
Expand the brief API server mention in ARCHITECTURE.md to link to comprehensive documentation.

### Changes Required:

#### 1. Expand API Section in ARCHITECTURE.md
**File**: `/Users/simo/Projects/autodev/docs/ARCHITECTURE.md`
**Changes**: Expand line 64 to full section with link

**Current content** (line 63-64):
```markdown
└── api/             # Optional REST API server
    └── server.go    # HTTP server for external control
```

**Replace with**:
```markdown
└── api/             # Optional REST API server
    ├── server.go    # HTTP server lifecycle and configuration
    ├── router.go    # Chi router with middleware and endpoints
    └── server_test.go# Server lifecycle tests
```

**Add new section** after "Python Agent Harness" section (after line 143, before "Data Flow" section):
```markdown
## HTTP API Server

The API server provides an optional REST interface for external control and monitoring.
It is built with the [chi v5](https://github.com/go-chi/chi) router and includes:

- **Middleware Stack**: RequestID, RealIP, Logger, Recoverer
- **Graceful Shutdown**: SIGINT/SIGTERM handling with 5-second timeout
- **Configuration**: Bind address, read/write/idle timeouts
- **Extensibility**: Dependencies struct for future dependency injection

**Current Endpoints:**
- `GET /healthz` - Health check returning `{"status": "ok"}`

See [API.md](./API.md) for complete API documentation including:
- Endpoints reference with request/response examples
- Configuration options and environment variables
- Integration examples in Go, curl, and Python
- Development guide for adding new endpoints

**Architecture:**
```text
┌─────────────────────────────────────┐
│         cmd/api/main.go             │
│    (Server binary entry point)      │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     internal/api/server.go          │
│  (Server lifecycle & Config)        │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│     internal/api/router.go          │
│  (Chi router + middleware)          │
│  ┌────────────────────────────────┐ │
│  │ Middleware:                    │ │
│  │ - RequestID                    │ │
│  │ - RealIP                       │ │
│  │ - Logger                       │ │
│  │ - Recoverer                    │ │
│  └────────────────────────────────┘ │
│  ┌────────────────────────────────┐ │
│  │ Endpoints:                     │ │
│  │ GET /healthz                   │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

**Key Design Decisions:**
- **Chi Router**: Lightweight, idiomatic Go HTTP router
- **Middleware-first**: Cross-cutting concerns handled at router level
- **Empty Dependencies**: Designed for future DI (runner control, config access)
- **No Authentication**: Currently open, may add auth middleware in future
```

### Success Criteria:

#### Automated Verification:
- [ ] ARCHITECTURE.md updated
- [ ] Markdown is valid
- [ ] Link to ./API.md is correct
- [ ] ASCII diagram is properly formatted

#### Manual Verification:
- [ ] New section placement is logical (after Python Agent Harness, before Data Flow)
- [ ] Content doesn't duplicate API.md, just summarizes
- [ ] Link works when clicked
- [ ] ASCII diagram renders correctly
- [ ] File references (server.go, router.go) are accurate

**Note**: Complete automated verification, then pause for manual confirmation before proceeding to Phase 4.

---

## Phase 4: Add Package-level Godoc Comment

### Overview
Add a package-level godoc comment to `internal/api/` to improve Go documentation.

### Changes Required:

#### 1. Add Package Documentation
**File**: `/Users/simo/Projects/autodev/internal/api/server.go`
**Changes**: Add package comment at top of file (before `package api`)

**Add at line 1** (before `package api`):
```go
// Package api provides an optional HTTP API server for external control and monitoring.
//
// The server is built with the chi v5 router and includes a standard middleware stack
// (RequestID, RealIP, Logger, Recoverer). It currently exposes a single health check
// endpoint: GET /healthz.
//
// # Quick Start
//
//	import "github.com/SimoKiihamaki/autodev/internal/api"
//
//	cfg := api.Config{Addr: ":8080"}
//	server := api.NewServer(cfg, api.Dependencies{})
//	go server.Start()
//
// # Configuration
//
// The server accepts configuration via the Config struct:
//   - Addr: Bind address (default: ":8080")
//   - ReadTimeout: Maximum duration for reading requests (default: 5s)
//   - WriteTimeout: Maximum duration for writing responses (default: 5s)
//   - IdleTimeout: Maximum time to wait for next request (default: 60s)
//
// Bind address can also be configured via the APRD_API_ADDR environment variable
// when using the cmd/api binary.
//
// # Server Lifecycle
//
// The server supports graceful shutdown with a configurable context timeout:
//
//	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
//	defer cancel()
//	if err := server.Shutdown(ctx); err != nil {
//	    log.Fatalf("Shutdown failed: %v", err)
//	}
//
// # Adding New Endpoints
//
// To add new endpoints, modify the newRouter function in router.go. The Dependencies
// struct is currently empty and designed for future dependency injection (e.g., runner
// control, config access, log streaming).
//
// # Stability
//
// The API is currently experimental and may change as the system evolves.
// For the latest API documentation, see docs/API.md.
package api
```

**Note**: This is a standard Go package comment that will appear in `godoc` output.

### Success Criteria:

#### Automated Verification:
- [ ] Package comment added to server.go
- [ ] Comment is valid Go syntax
- [ ] Comment includes all sections (overview, quick start, config, lifecycle, adding endpoints, stability)
- [ ] Code examples are syntactically correct

#### Manual Verification:
- [ ] `go doc github.com/SimoKiihamaki/autodev/internal/api` displays the comment
- [ ] Comment style matches Go documentation conventions
- [ ] Links/references to docs/API.md are accurate
- [ ] Code examples are accurate and runnable

**Note**: Complete all verification. This is the final phase.

---

## Testing Strategy

### Documentation Testing:

#### 1. Link Verification
- Verify all internal links work (README.md → docs/API.md, ARCHITECTURE.md → docs/API.md)
- Verify external links (chi router v5) are accessible

#### 2. Code Example Testing
Test all code examples to ensure they work:
- **bash/curl examples**: Run commands and verify output
- **Go examples**: Verify code compiles (if adding godoc, run `go build` on examples)
- **Python examples**: Verify syntax is correct

#### 3. Accuracy Verification
Cross-reference all documentation with source code:
- Config fields: `internal/api/server.go:14-19`
- Middleware: `internal/api/router.go:13-16`
- Environment variable: `cmd/api/main.go:16`
- Default values: `internal/api/server.go:11` (DefaultAPIAddr)

#### 4. Style Consistency
- Compare structure with ARCHITECTURE.md and OPERATIONS.md
- Verify heading hierarchy (## for main, ### for subsections)
- Verify table formatting
- Verify code block language tags

### Manual Testing Steps:

1. **Read through API.md**
   - Check for clarity and completeness
   - Verify all sections are present
   - Check code examples are understandable

2. **Test quick start commands**
   ```bash
   make build
   ./bin/api
   # In another terminal:
   curl http://localhost:8080/healthz
   # Should return: {"status":"ok"}
   ```

3. **Verify documentation links**
   - Click link from README.md to docs/API.md
   - Click link from ARCHITECTURE.md to docs/API.md
   - Verify all sections are linked correctly

4. **Check godoc**
   ```bash
   go doc github.com/SimoKiihamaki/autodev/internal/api
   # Should display package comment
   ```

5. **Compare with existing docs**
   - Style matches ARCHITECTURE.md
   - Style matches OPERATIONS.md
   - Tables are formatted consistently
   - Code examples use same style

## Migration Notes

Not applicable - this is documentation-only with no code changes.

## References

- Research: `/Users/simo/Projects/autodev/.wreckit/items/021-add-comprehensive-api-documentation/research.md`
- API server implementation: `/Users/simo/Projects/autodev/internal/api/server.go`
- Router implementation: `/Users/simo/Projects/autodev/internal/api/router.go`
- API binary entry point: `/Users/simo/Projects/autodev/cmd/api/main.go`
- Architecture documentation: `/Users/simo/Projects/autodev/docs/ARCHITECTURE.md`
- Operations documentation: `/Users/simo/Projects/autodev/docs/OPERATIONS.md`
- Chi router v5: https://github.com/go-chi/chi
