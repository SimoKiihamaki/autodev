# Repository Guidelines

## Project Structure & Module Organization
- `cmd/aprd`: CLI entrypoint for Bubble Tea TUI; keep this minimal, delegate to `internal`.
- `internal/tui`: models, view, style; focus on state updates and key handling.
- `internal/runner`: orchestrates Python automation and process control.
- `internal/config`: loads/saves settings and CLI flag wiring.
- `tools/auto_prd_to_pr_v3.py`: Python pipeline invoked by TUI.
- `bin/`: build artifacts produced by `make build`; keep out of version control.

## Build, Test, and Development Commands
- `make build`: tidies modules and emits `bin/aprd`.
- `make run`: rebuilds then launches the TUI for manual testing.
- `make tidy`: keep `go.mod` / `go.sum` tidy; run before commits that touch deps.
- `go run ./cmd/aprd`: quick iteration without generating binaries.
- `go test ./...`: execute all Go unit tests once they exist.

## Coding Style & Naming Conventions
- Go code must pass `go fmt ./...`; prefer explicit imports and short receiver names (`func (m *Model)`).
- Use `goimports` to maintain import ordering.
- Package names should be lowercase (no underscores) to align with Go idioms; examples: runner, config; exported types use PascalCase (`AppState`), internal helpers use camelCase.
- Constants follow `const FooBar = ...`; avoid all-caps except for env keys (`AUTO_PRD_EXECUTOR_*`).

## Testing Guidelines
- Add `_test.go` files alongside implementation packages; model updates benefit from table-driven tests.
- Mock external commands via interfaces in `internal/runner`; avoid invoking the Python script in unit tests.
- Target: keep coverage high on state transitions and config serialization; document gaps in PR if coverage dips.
- Run `go test ./...` before pushing; include sample command output in PR when introducing integration paths.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`feat:`, `fix:`, `refactor:`, etc.) as seen in `git log`.
- Commits should be scoped per feature or bugfix; avoid mixing lint and feature changes.
- PRs include summary, testing evidence (`go test ./...`, `make run` manual validation), and linked issue/PRD.
- Provide screenshots or terminal captures when UI/UX behavior changes; flag any required env vars or secrets.

## Agent-Specific Tips
- Configure the embedded Python script path via Settings tab; default `tools/auto_prd_to_pr_v3.py` should remain valid.
- When auto-running phases, document new flags within `internal/config` and surface them through the Env tab.
