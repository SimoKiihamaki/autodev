# Create GitHub CI/CD workflow Implementation Plan

## Overview
Implement a GitHub Actions CI/CD workflow that automatically runs quality checks on all pull requests and pushes to the master branch. The autodev project is a dual-language system (Go 1.23 + Python 3.10+) with comprehensive Makefile-based testing infrastructure that needs to be automated in GitHub Actions.

## Current State Analysis

**Existing Infrastructure:**
- **Makefile** (`/Users/simo/Projects/autodev/Makefile:1-88`) provides complete CI automation:
  - `make ci` (line 35) runs all checks: `lint test test-go-race typecheck-lenient`
  - `make lint` (line 39) runs Go and Python linting
  - `make test` (line 51) runs Go tests
  - `make test-go-race` (line 58) runs Go tests with race detector
  - `make typecheck-lenient` (line 85) runs mypy in non-blocking mode
- **No GitHub Actions workflows exist** - only documentation in `.github/` directory
- **Repository**: `github.com/SimoKiihamaki/autodev` with `master` as main branch
- **Go version**: 1.23.0 specified in `go.mod:3`
- **Python version**: >=3.10 specified in `tools/auto_prd/pyproject.toml:6`

**Test Coverage:**
- 33 Go test files across `cmd/` and `internal/` packages
- 21 Python test files in `tools/auto_prd/tests/` and `tools/tests/`

**Key Dependencies:**
- **Go**: golangci-lint, goimports (standard Go toolchain)
- **Python**: uv package manager, ruff, mypy, pytest

## Desired End State

**Specification:**
1. **Workflow file**: `.github/workflows/ci.yml` created and functional
2. **Triggers**: Runs on:
   - Push to `master` branch
   - Pull requests targeting `master` branch
3. **Environment**: Ubuntu latest with Go 1.23 and Python 3.11
4. **Execution**: Installs all dependencies and runs `make ci`
5. **Outcome**: All quality checks (lint, test, race detection, typecheck) pass automatically

**Verification:**
- Push a commit to GitHub and observe workflow run in Actions tab
- Create a pull request and verify all checks run
- All Makefile CI targets complete successfully in CI environment

### Key Discoveries:
- **Centralized CI command**: The `make ci` target (Makefile:35) already orchestrates all checks, eliminating need to duplicate logic in YAML
- **Path-dependent commands**: Makefile uses `cd $(TOOLS_DIR)` (lines 48, 64, 77, 82, 87), so workflow must run from repository root
- **Lenient type checking**: The `typecheck-lenient` target uses `|| true` (line 87), intentionally non-blocking during rollout
- **Dual-language structure**: Go code in root, Python code in `tools/`, both need testing
- **No branch protection yet**: Master branch currently accepts all commits; CI will provide validation before future branch protection

## What We're NOT Doing

**Explicitly out of scope for this task:**
- ❌ Configuring branch protection rules (requires CI to be proven first)
- ❌ Adding build artifact uploads or releases
- ❌ Creating separate jobs for Go and Python (single job is simpler and adequate)
- ❌ Implementing caching for Go modules or Python packages (can be added later if CI is slow)
- ❌ Adding deployment or staging workflows
- ❌ Creating golangci-lint configuration file (defaults acceptable for now)
- ❌ Modifying existing test suites or Makefile targets
- ❌ Adding status badges to README.md (follow-up task)

## Implementation Approach

**High-level Strategy:**
The implementation follows a single-phase approach because:
1. The Makefile already provides a complete, tested CI pipeline
2. The workflow simply needs to orchestrate environment setup and execute `make ci`
3. No existing infrastructure needs migration (no CI to replace)
4. The change is additive and low-risk (adding a YAML file)

**Design Principles:**
1. **Leverage existing automation**: Use `make ci` rather than duplicating commands
2. **Match local development**: CI should run same commands as developers run locally
3. **Minimal complexity**: Single job, sequential execution, no matrix builds
4. **Fail fast**: Any check failure should fail the workflow immediately
5. **Future-proof**: Structure supports easy enhancement (caching, separate jobs, etc.)

---

## Phase 1: Create GitHub Actions CI Workflow

### Overview
Create `.github/workflows/ci.yml` that installs Go 1.23, Python 3.11, and all required tools, then runs the complete CI pipeline via `make ci`.

### Changes Required:

#### 1. GitHub Actions Workflow File
**File**: `.github/workflows/ci.yml`
**Changes**: Create new workflow file with complete CI pipeline

```yaml
name: CI

on:
  push:
    branches: [ master ]
  pull_request:
    branches: [ master ]

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

**Justification:**
- **Triggers**: `push` and `pull_request` on `master` ensures all changes are validated (matches task requirement)
- **Go version**: `'1.23'` uses latest 1.23.x patch version, matching `go.mod:3` requirement (matches task constraint)
- **Python version**: `'3.11'` is stable and satisfies `>=3.10` requirement from `pyproject.toml:6`
- **Tool installation**:
  - golangci-lint and goimports installed via `go install` (standard practice)
  - uv installed via pip, then `uv sync` creates environment and installs dependencies from `tools/pyproject.toml`
- **Single command**: `make ci` runs all checks in correct order (lint → test → race detection → typecheck)

### Success Criteria:

#### Automated Verification:
- [ ] Workflow file syntax is valid (no YAML errors)
- [ ] Workflow triggers on push to master branch
- [ ] Workflow triggers on pull request to master branch
- [ ] Go 1.23 is installed and available
- [ ] Python 3.11 is installed and available
- [ ] golangci-lint is installed and in PATH
- [ ] goimports is installed and in PATH
- [ ] uv is installed and Python dependencies are synced
- [ ] `make ci` executes and all sub-targets complete:
  - [ ] `make lint-go` (golangci-lint run ./...)
  - [ ] `make lint-py` (ruff check auto_prd/)
  - [ ] `make test-go` (go test ./...)
  - [ ] `make test-go-race` (go test ./... -race)
  - [ ] `make typecheck-lenient` (mypy auto_prd/)

#### Manual Verification:
- [ ] Push a commit to `wreckit/007-create-github-cicd-workflow` branch and observe workflow run in GitHub Actions tab
- [ ] Verify all workflow steps show green checkmarks
- [ ] Create a pull request to master and verify CI checks appear in PR checks list
- [ ] Confirm workflow completes in reasonable time (<5 minutes ideally)
- [ ] Review workflow logs to ensure all Makefile targets executed with expected output

**Rollback Strategy:**
If workflow fails repeatedly:
1. Delete `.github/workflows/ci.yml` to disable CI
2. Investigate failure by running `make ci` locally
3. Fix issues and push updated workflow file
4. The workflow is additive and doesn't affect existing development workflow

---

## Testing Strategy

### Unit Tests:
**Not applicable** - This task adds infrastructure, not application code. The "unit test" is the workflow itself executing the existing unit test suite.

### Integration Tests:
**Workflow execution validation:**
1. Push commit → Workflow triggers automatically
2. All dependencies install successfully
3. `make ci` runs all Makefile targets
4. All Go tests pass (33 test files)
5. All Python tests pass (21 test files)
6. golangci-lint completes without errors
7. ruff completes without errors
8. Race detector tests complete
9. Type checking completes (non-blocking)

### Manual Testing Steps:

#### Step 1: Local Validation
Before pushing to GitHub, verify the Makefile works:
```bash
cd /Users/simo/Projects/autodev
make ci
```
**Expected output**: All checks pass with ✅ emojis

#### Step 2: Workflow Creation
Create the workflow file:
```bash
mkdir -p .github/workflows
# Create .github/workflows/ci.yml with the YAML content above
```

#### Step 3: Push and Observe
```bash
git add .github/workflows/ci.yml
git commit -m "Add CI workflow"
git push origin wreckit/007-create-github-cicd-workflow
```

#### Step 4: Verify in GitHub
1. Navigate to: https://github.com/SimoKiihamaki/autodev/actions
2. Click on the latest workflow run
3. Verify each step:
   - ✓ Checkout code
   - ✓ Set up Go
   - ✓ Set up Python
   - ✓ Install Go tools
   - ✓ Install Python tools
   - ✓ Run CI (expanded to show all Makefile output)

#### Step 5: Pull Request Testing
1. Create a PR from `wreckit/007-create-github-cicd-workflow` to `master`
2. Verify CI checks appear in the PR checks section
3. Confirm all checks pass

### Edge Cases to Validate:

| Scenario | Expected Behavior |
|----------|-------------------|
| **Race test timeout** | CI fails with clear error message; may need to increase timeout in future |
| **golangci-lint not in PATH** | Installation step fails; workflow doesn't proceed to tests |
| **uv sync failure** | Python environment setup fails; workflow stops before running Python tests |
| **Git submodules (if any)** | checkout@v4 handles submodules automatically; not currently applicable |
| **Large repository** | Initial run may be slow; subsequent runs could be optimized with caching |
| **Flaky tests** | CI will fail intermittently; indicates test reliability issue to fix in codebase |

## Migration Notes

**No migration required** - This is new infrastructure with no existing CI to migrate from.

**Post-implementation considerations** (not part of this task):
1. **Caching**: If CI is slow, add caching for Go modules and Python packages
2. **Parallel jobs**: If CI takes >10 minutes, split Go and Python into separate jobs
3. **Branch protection**: Once CI is proven stable, configure branch protection rules
4. **Status badges**: Add CI badge to README.md
5. **Nightly builds**: Consider adding scheduled runs for master branch
6. **Release workflow**: Future workflow could build and release binaries

## References

- **Research**: `/Users/simo/Projects/autodev/.wreckit/items/007-create-github-cicd-workflow/research.md`
- **Makefile**: `/Users/simo/Projects/autodev/Makefile:1-88` (CI automation)
- **Go module**: `/Users/simo/Projects/autodev/go.mod:3` (version requirement)
- **Python config**: `/Users/simo/Projects/autodev/tools/auto_prd/pyproject.toml:6` (version requirement)
- **GitHub Actions docs**: https://docs.github.com/en/actions
- **setup-go action**: https://github.com/actions/setup-go
- **setup-python action**: https://github.com/actions/setup-python
- **uv docs**: https://github.com/astral-sh/uv
