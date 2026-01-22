# Support Mode

Framework-agnostic continuous monitoring and review tool for AI-assisted development.

## Features

- Repository state monitoring (branch, commit SHA, working tree)
- Tracker validation (structure, features, tasks, dependencies)
- PRD synchronization (checkbox extraction, comparison)
- Git quality checks (`git diff --check`)
- Verification run status checking
- Guardrails display
- Configurable polling interval with graceful shutdown

## Installation

```bash
pip install support-mode
```

For development:

```bash
pip install -e .
```

## Usage

Basic usage:

```bash
support-mode --prd path/to/prd.md
```

With custom polling interval:

```bash
support-mode --prd path/to/prd.md --poll-seconds 60
```

Specify repository path:

```bash
support-mode --prd path/to/prd.md --repo /path/to/repo
```

## Compatibility

Support mode reads and writes the same `.aprd` directory structure as auto_prd:

- `.aprd/tracker.json` - Implementation tracker
- `.aprd/support_state.json` - Review state persistence
- `.aprd/verification/runs.jsonl` - Verification run history

This means you can use support-mode alongside auto_prd, or as a replacement
for the monitoring functionality.

## Requirements

- Python 3.10 or higher
- Git repository
- Existing `.aprd/tracker.json` file

## Exit Codes

- 0: Clean exit (Ctrl+C or completion)
- 1: Error (missing PRD, invalid arguments, etc.)

## License

MIT

## Contributing

Contributions welcome! Please open an issue or PR.
