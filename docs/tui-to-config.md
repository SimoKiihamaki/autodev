# TUI → Config Mapping Checklist

This checklist enumerates every interactive control in the Bubble Tea interface and the configuration field it drives. Each item notes the handler that copies UI state into `config.Config` before `config.Save` runs. Entries marked `[runtime-only]` are intentionally transient and excluded from persistence.

## PRD Tab
- [x] PRD selection list (`m.prdList`, `handlePRDTabActions`) → `config.Config.PRDs[path].LastUsed` updated when the user saves metadata; used to auto-select the most recent PRD on launch.
- [x] Tag input (`m.tagInput`, `handlePRDTabActions`/`applyPRDMetadata`) → `config.Config.PRDs[path].Tags` via `model.applyPRDMetadata`, persisted on `Ctrl+S` and PRD Save.

## Settings Tab
- [x] Repo path (`m.inRepo`) → `Config.RepoPath` via `populateConfigFromInputs`.
- [x] Base branch (`m.inBase`) → `Config.BaseBranch` via `populateConfigFromInputs`.
- [x] Feature branch (`m.inBranch`) → `Config.Branch` via `populateConfigFromInputs`.
- [x] Codex model (`m.inCodexModel`) → `Config.CodexModel` via `populateConfigFromInputs`.
- [x] Python command (`m.inPyCmd`) → `Config.PythonCommand` via `populateConfigFromInputs`.
- [x] Python script path (`m.inPyScript`) → `Config.PythonScript` via `populateConfigFromInputs`.
- [x] Executor policy (`m.inPolicy`) → `Config.ExecutorPolicy` via `populateConfigFromInputs`.
- [x] Local Loop executor toggle (`m.execLocalChoice`) → `Config.PhaseExecutors.Implement`/`Fix` via `populateConfigFromInputs`.
- [x] PR Push executor toggle (`m.execPRChoice`) → `Config.PhaseExecutors.PR` via `populateConfigFromInputs`.
- [x] Review Fix executor toggle (`m.execReviewChoice`) → `Config.PhaseExecutors.ReviewFix` via `populateConfigFromInputs`.
- [x] Wait minutes (`m.inWaitMin`) → `Config.Timings.WaitMinutes` via `populateConfigFromInputs`.
- [x] Review poll seconds (`m.inPollSec`) → `Config.Timings.ReviewPollSeconds` via `populateConfigFromInputs`.
- [x] Idle grace minutes (`m.inIdleMin`) → `Config.Timings.IdleGraceMinutes` via `populateConfigFromInputs`.
- [x] Max local iters (`m.inMaxIters`) → `Config.Timings.MaxLocalIters` via `populateConfigFromInputs`.

## Env & Flags Tab
- [x] Local phase toggle (`m.runLocal`) → `Config.RunPhases.Local` via `populateConfigFromInputs`.
- [x] PR phase toggle (`m.runPR`) → `Config.RunPhases.PR` via `populateConfigFromInputs`.
- [x] Review Fix phase toggle (`m.runReview`) → `Config.RunPhases.ReviewFix` via `populateConfigFromInputs`.
- [x] Allow unsafe (`m.flagAllowUnsafe`) → `Config.Flags.AllowUnsafe` via `populateConfigFromInputs`.
- [x] Dry run (`m.flagDryRun`) → `Config.Flags.DryRun` via `populateConfigFromInputs`.
- [x] Sync git (`m.flagSyncGit`) → `Config.Flags.SyncGit` via `populateConfigFromInputs`.
- [x] Infinite reviews (`m.flagInfinite`) → `Config.Flags.InfiniteReviews` via `populateConfigFromInputs`.

## Prompt Tab
- [runtime-only] Initial prompt textarea (`m.prompt`) is applied directly to `runner.Options.InitialPrompt` for the next run and intentionally not persisted to config.

## Run Tab
- Follow logs toggle (`m.followLogs`) persists to `config.Config.FollowLogs` (introduced in task D1).

## Logs Tab
- [runtime-only] Scroll actions modify viewport state only; no config fields are expected.
