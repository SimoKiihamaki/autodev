# Research: Create GitHub CI/CD workflow

**Date**: 2025-01-19
**Item**: 007-create-github-cicd-workflow

## Research Question
Lack of CI/CD means no automated testing or validation when pull requests are submitted.

**Motivation:** Enables automated quality checks on all PRs, improving code quality and catching issues early.

**Success criteria:**
- Create .github/workflows/ci.yml
- Run make ci on push and pull_request
- Test on Ubuntu latest with Go 1.23

**Technical constraints:**
- Create .github/workflows/ci.yml
- Configure to run on push and pull_request events
- Use actions/setup-go@v5 with Go 1.23

**Signals:** priority: critical

## Summary

The autodev project is a PRD-to-PR automation system consisting of a Go-based TUI frontend (~13,227 lines of Go code across 6 packages) and a Python-based agent harness. The project currently has no CI/CD automation despite having comprehensive tooling defined in the Makefile.

The project requires:
1. **Go 1.23** (as specified in go.mod:3) for the TUI frontend
2. **Python 3.10+** (as specified in tools/auto_prd/pyproject.toml:6) for the agent harness
3. Multiple linting and testing tools already configured in the Makefile

The `make ci` target (Makefile:35) already orchestrates all necessary checks: `lint`, `test`, `test-go-race`, and `typecheck-lenient`. This makes the CI workflow straightforward - it needs to install dependencies and run this single command.

Key findings:
- No existing `.github/workflows/` directory exists
- The Makefile provides a complete CI pipeline that just needs to be automated
- Both Go (33 test files) and Python (21 test files) components need testing
- Tools like golangci-lint, ruff, and uv are already used locally
- The project uses github.com/SimoKiihamaki/autodev as its remote repository

## Current State Analysis

### Existing Implementation

**No CI/CD infrastructure exists:**
- The `.github` directory (/.github) contains only documentation (copilot-instructions.md and instructions/)
- No workflows directory or GitHub Actions configurations are present
- The project relies on local development workflows using make commands

**Complete local CI pipeline exists in Makefile:**
- `make ci` (Makefile:35) - runs all checks: `lint test test-go-race typecheck-lenient`
- `make lint` (Makefile:39) - runs both Go and Python linting
- `make test` (Makefile:51) - runs Go tests
- `make lint-go` (Makefile:42) - runs golangci-lint
- `make lint-py` (Makefile:46) - runs ruff on tools/auto_prd/
- `make test-go-race` (Makefile:58) - runs Go tests with race detector
- `make typecheck-lenient` (Makefile:85) - runs mypy in lenient mode (doesn't fail build)

### Key Files

- **Makefile:1-88** - Complete build and CI automation
  - Line 35: `ci` target that runs all checks
  - Line 42-44: Go linting with golangci-lint
  - Line 46-48: Python linting with ruff
  - Line 54-56: Go testing
  - Line 58-60: Go race detector testing
  - Line 85-87: Lenient type checking (non-blocking)

- **go.mod:1-47** - Go module definition
  - Line 3: Specifies Go 1.23.0 as minimum version
  - Module: github.com/SimoKiihamaki/autodev

- **tools/auto_prd/pyproject.toml:1-72** - Python project configuration
  - Line 6: Requires Python >=3.10
  - Line 27-30: Test dependencies (pytest>=7.0, pytest-xdist>=3.0)
  - Line 40-58: Ruff linting configuration
  - Line 67-70: Mypy configuration with test file overrides

- **Test coverage:**
  - 33 Go test files across cmd/ and internal/ packages
  - 21 Python test files in tools/auto_prd/tests/ and tools/tests/
  - Examples: internal/api/router_test.go:1-21, cmd/aprd/main_test.go:1-49

- **.codacy/codacy.yaml:1-16** - External CI service configuration
  - Already configured with Go 1.23.0, Python 3.11.11, and various linters
  - This suggests the project values automated quality checks but lacks native GitHub Actions

## Technical Considerations

### Dependencies

**Go dependencies:**
- Go 1.23 (required by go.mod:3)
- golangci-lint (used in Makefile:44)
- goimports (used in Makefile:72 for fmt target)
- Standard Go toolchain (go test, go build, etc.)

**Python dependencies:**
- Python 3.10+ (required by tools/auto_prd/pyproject.toml:6)
- uv package manager (used in Makefile:64 for Python tests)
- ruff (used in Makefile:48 for Python linting)
- mypy (used in Makefile:82 for type checking)
- pytest (test runner specified in pyproject.toml:28)

**GitHub Actions:**
- actions/setup-go@v5 (required by task constraints)
- actions/setup-python or similar for Python environment
- actions/checkout for repository checkout

### Patterns to Follow

**Existing conventions observed in the codebase:**

1. **Makefile-driven automation** - All CI commands are centralized in Makefile
   - The CI workflow should leverage `make ci` rather than duplicating commands
   - This ensures consistency between local and CI environments

2. **Dual-language project structure**
   - Go code in root (cmd/, internal/)
   - Python code in tools/ directory
   - Both need testing in CI

3. **Lenient type checking policy** (Makefile:85-87)
   - Type checks use `|| true` to avoid blocking during rollout
   - CI should follow this pattern initially

4. **Comprehensive testing approach**
   - Go tests with race detector (Makefile:58-60)
   - Separate test targets for Go and Python
   - Linting for both languages

5. **GitHub repository structure**
   - Repository: github.com/SimoKiihamaki/autodev
   - Main branch: master (confirmed via git branch)
   - Active development with recent commits

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Go version mismatch** | High | The project specifies Go 1.23.0 in go.mod:3, but the local development environment has Go 1.25.0. The CI workflow must use exactly Go 1.23.x to match the module requirement. Use `actions/setup-go@v5` with `go-version: '1.23'` as specified in task constraints. |
| **Python tool installation complexity** | Medium | Python tests require `uv`, `ruff`, and `mypy`. These may not be pre-installed. The workflow must install these tools or use the existing .venv in tools/. Recommendation: Install uv and use it to manage Python dependencies. |
| **Path-dependent commands** | Medium | The Makefile uses relative paths like `cd $(TOOLS_DIR)` (Makefile:48, 64, 77, 82, 87). CI workflow must run from the repository root. Use `working-directory: .` or explicit path handling. |
| **Missing golangci-lint configuration** | Low | No `.golangci.yml` found in project root. golangci-lint will use default configuration. Consider adding a config file if default settings are too strict/lenient. |
| **Python virtual environment** | Low | The tools/.venv/ directory exists but is in .gitignore. CI must recreate this environment. Use `uv` or standard `python -m venv` to create environment. |
| **Race condition in tests** | Low | The `make test-go-race` target (Makefile:58) runs tests with race detector. These tests may be flaky in CI. Consider increasing test timeout or making race tests optional if they prove unreliable. |
| **typecheck-lenient non-blocking** | Low | The typecheck-lenient target (Makefile:85-87) uses `|| true`, meaning it won't fail the build. This is intentional but reduces CI effectiveness. Document this clearly in the workflow. |

## Recommended Approach

Based on research findings, here's the recommended implementation strategy:

### 1. Create GitHub Actions Workflow

**File:** `.github/workflows/ci.yml`

**Structure:**
```yaml
name: CI

on:
  push:
    branches: [ master, main ]
  pull_request:
    branches: [ master, main ]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout code
      uses: actions/checkout@v4

    - name: Set up Go
      uses: actions/setup-go@v5
      with:
        go-version: '1.23'

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - name: Install Go tools
      run: |
        go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest
        go install golang.org/x/tools/cmd/goimports@latest

    - name: Install Python tools
      run: |
        pip install uv
        cd tools && uv sync

    - name: Run CI
      run: make ci
```

### 2. Key Design Decisions

**Trigger events:**
- Run on `push` to master/main branches
- Run on `pull_request` to master/main branches
- This ensures all changes are validated before merging

**Go version:**
- Use exactly 1.23 to match go.mod:3 requirement
- Despite local env using 1.25, CI should match module specification

**Python version:**
- Use 3.11 (stable, >= 3.10 requirement from pyproject.toml:6)
- Matches the .codacy configuration (.codacy/codacy.yaml:6)

**Tool installation:**
- Install golangci-lint and goimports via `go install`
- Install uv package manager, then use it to sync Python dependencies
- This mirrors local development workflow

**Command execution:**
- Run `make ci` which orchestrates all checks
- This maintains consistency with local development
- Single command is easier to maintain than duplicating logic in YAML

### 3. Validation Strategy

**Phase 1 - Basic workflow:**
- Create .github/workflows/ci.yml
- Trigger on push and pull_request
- Install dependencies and run make ci

**Phase 2 - Monitor and adjust:**
- Watch first few CI runs for failures
- Adjust timeouts if needed (especially for race tests)
- Add job-specific optimizations if CI is slow

**Phase 3 - Enhancements (future):**
- Add caching for Go modules and Python packages
- Add build artifact uploads
- Consider separate jobs for Go and Python if parallelization helps
- Add status badges to README.md

## Open Questions

1. **Go version pinning:** Should the workflow use `go-version: '1.23'` or `go-version: '1.23.x'`? The task constraint specifies "Go 1.23" without precision level. Recommendation: Use `'1.23'` to get the latest 1.23.x patch version.

2. **Python dependency management:** The tools directory has a .venv/ that's gitignored. Should CI:
   - Option A: Create fresh venv and install from pyproject.toml
   - Option B: Use uv sync to recreate the environment
   - Recommendation: Use Option B (uv sync) as it's what Makefile:64 implies

3. **Branch protection:** Once CI is working, should branch protection rules be configured to require CI checks before merging? This is outside the current task scope but worth considering.

4. **golangci-lint configuration:** No .golangci.yml exists. Should one be added to ensure CI uses the same configuration as local development, or are defaults acceptable? This may be needed if default linters are too strict.

5. **Race test reliability:** The test-go-race target may be flaky in CI. Should it be made optional or allowed to fail? Recommendation: Keep it initially, monitor results, and adjust if needed.

6. **Type checking strictness:** The typecheck-lenient target (Makefile:87) uses `|| true` to avoid blocking. Should CI eventually enforce strict type checking? This is a gradual migration strategy noted in the Makefile comment.
