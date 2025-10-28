# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`aprd-tui` is a terminal user interface (TUI) built with Go and the Bubble Tea framework that drives a Python PRD-to-PR automation pipeline. The application provides an interactive interface for selecting PRD (Product Requirements Document) files, configuring execution parameters, and running automated workflows that implement features and create pull requests.

## Architecture

### Core Components

- **`cmd/aprd/main.go`**: Entry point that initializes the Bubble Tea TUI
- **`internal/tui/`**: Contains the main TUI model (`model.go`), styling (`styles.go`), and UI logic
- **`internal/config/`**: Configuration management with YAML persistence to `~/.config/aprd/config.yaml`
- **`internal/runner/`**: Process execution layer that runs the Python automation script
- **`tools/auto_prd_to_pr_v3.py`**: The Python automation pipeline that does the actual work

### TUI Structure

The application uses a tab-based interface with 7 main tabs:
1. **Run**: Execute the automation pipeline
2. **PRD**: Select and tag markdown PRD files
3. **Settings**: Configure paths, models, and executors
4. **Env**: Toggle phases and flags
5. **Prompt**: Add optional initial instructions
6. **Logs**: View live output from the Python process
7. **Help**: Usage instructions

### Configuration System

The config system uses YAML files stored in `~/.config/aprd/config.yaml` and includes:
- Repository settings (repo path, base branch, feature branch)
- Executor configuration (per-phase executors: codex/claude)
- Timing parameters (wait times, poll intervals, iteration limits)
- Boolean flags (dry run, sync git, unsafe execution)
- Phase selection (local, PR, review_fix)
- PRD metadata (tags, last used timestamps)

## Development Commands

### Build and Run
```bash
# Build the binary
make build

# Run the application (builds and executes)
make run

# Build and install to system PATH
make install

# Clean build artifacts
make clean

# Update Go modules
make tidy
```

The binary will be output to `./bin/aprd` and can be run directly from there.

### Dependencies
- Go 1.22+ (uses Go modules)
- Python 3.9+ (for the automation script)
- External CLIs: `codex`, `claude`, `coderabbit`, `git`, `gh`

## Key Implementation Details

### TUI Model Architecture
The main `model` struct in `internal/tui/model.go` follows Bubble Tea patterns:
- **State management**: All UI state is stored in the model
- **Message passing**: Uses Go channels for async communication with the Python process
- **Tab navigation**: Number keys 1-6 and ? for direct tab switching
- **Input handling**: Different update functions per tab context

### Process Execution
The `runner` package handles subprocess execution:
- Creates temporary PRD files when initial prompts are provided
- Streams stdout/stderr back to the TUI via channels
- Supports context cancellation with Ctrl+C
- Manages environment variables for executor configuration

### Configuration Persistence
- Auto-saves configuration when changed in the UI
- Supports per-PRD metadata (tags, usage history)
- Provides sensible defaults for all settings
- Uses environment variable overrides for executor settings

### Python Integration
The TUI is a frontend for the Python automation script:
- Constructs command-line arguments from UI state
- Handles per-phase executor configuration via environment variables
- Supports starting from any phase (local, PR, review_fix)
- Manages temporary files for initial prompt injection

## Testing the Application

Since this is a TUI application, testing involves:
1. Building and running locally: `make run`
2. Testing with actual PRD files (markdown files in the working directory)
3. Verifying configuration persistence across runs
4. Testing process cancellation and error handling

The application expects to find PRD files by scanning for `*.md` files in the current working directory and subdirectories (up to 4 levels deep).

## Post-Push Requirements

Whenever you push fixes to an open pull request, immediately leave a PR comment that:
- Summarizes what changed in the new commit(s) and why those changes were necessary.
- Calls out any important decisions you made, including references to repository rules or conventions that shaped the approach.
- Tags `@coderabbit`, `@copilot-pull-request-reviewer[bot]`, and `@codex` so the automation tools receive the update. **Do not mention `@copilot` directly**; that handle summons the SWE agent and will open a new PR automatically.
