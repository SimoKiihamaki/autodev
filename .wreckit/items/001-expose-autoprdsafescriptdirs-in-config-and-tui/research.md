# Research: Expose AUTO_PRD_SAFE_SCRIPT_DIRS in config and TUI

**Date**: 2026-01-19
**Item**: 001-expose-autoprdsafescriptdirs-in-config-and-tui

## Research Question
Users cannot configure allowed Python directories through the UI; they must manually edit environment variables.

**Motivation:** Improves user experience by allowing configuration through the standard TUI Settings interface instead of requiring manual environment variable editing.

**Technical constraints:**
- Add SafeScriptDirs field to Config struct in config.go
- Update runner.go to read from config instead of just environment
- Add TUI input field in Settings tab

**Signals:** priority: critical

## Summary

The current implementation uses the environment variable `AUTO_PRD_SAFE_SCRIPT_DIRS` to whitelist directories containing Python scripts. This is a security feature that prevents execution of scripts from arbitrary locations. However, users must currently edit this environment variable manually outside the application, which creates a poor user experience.

The research reveals that:
1. The `AllowedPythonDirs` field **already exists** in the Config struct (line 126 in config.go) but is not exposed in the TUI
2. The runner already reads from `cfg.GetAllowedPythonDirs()` for Python interpreter validation (lines 813-860 in runner.go)
3. The `AUTO_PRD_SAFE_SCRIPT_DIRS` environment variable is used for a different purpose: whitelisting directories that contain the **automation Python script itself** (not the Python interpreter)
4. There is confusion between two different concepts:
   - `AllowedPythonDirs`: Validates Python **interpreter** paths (already implemented, needs TUI exposure)
   - `AUTO_PRD_SAFE_SCRIPT_DIRS`: Whitelists directories for the **automation script** (currently only via env var)

**Key Finding:** The task description is slightly misleading. The `AUTO_PRD_SAFE_SCRIPT_DIRS` environment variable and the `AllowedPythonDirs` config field serve **different purposes**:
- `AllowedPythonDirs` validates Python **binary/interpreter** locations
- `AUTO_PRD_SAFE_SCRIPT_DIRS` validates the **automation script** location (e.g., `tools/auto_prd_to_pr_v3.py`)

However, both need TUI exposure for complete user control. Based on the technical constraints and user needs, this implementation should:

1. Expose the existing `AllowedPythonDirs` field in the TUI (for Python interpreter validation)
2. Add a new config field for script directory whitelisting (to replace `AUTO_PRD_SAFE_SCRIPT_DIRS` env var usage)
3. Update runner.go to merge both sources for script validation

## Current State Analysis

### Existing Implementation

**Config Structure** (`internal/config/config.go`):
- Line 126: `AllowedPythonDirs []string` field already exists in Config struct
- Line 177: Default value is empty slice `[]string{}`
- Line 418-419: Initialized to defaults if nil during config load
- Line 494-495: Cloned properly in `Clone()` method
- Line 636-638: Compared in `Equal()` method using `equalStringSlices()`
- Lines 698-703: `GetAllowedPythonDirs()` getter method returns a defensive copy

**Runner Usage** (`internal/runner/runner.go`):
- Lines 232, 277: `safeScriptDirsEnv` constant defines `"AUTO_PRD_SAFE_SCRIPT_DIRS"`
- Lines 234-293: `resolvedSafeScriptDirs()` function builds whitelist from:
  - Temporary autodev working directory
  - User-level autodev installation directory
  - Directories relative to the aprd executable
  - **Environment variable** `AUTO_PRD_SAFE_SCRIPT_DIRS` (lines 277-286)
- Lines 178-230: `validatePythonScriptPath()` uses `resolvedSafeScriptDirs()` for script validation
- Lines 757-877: `validatePythonCommandWithConfig()` uses `cfg.GetAllowedPythonDirs()` for **interpreter** validation

**Environment Variable Handling** (`internal/runner/runner.go`):
- Lines 277-286: Reads `AUTO_PRD_SAFE_SCRIPT_DIRS` and parses as path list
- Lines 991-1031: `ensureScriptDirWhitelisted()` adds script dir to env var for child processes
- Line 638: Script dir is merged into environment before execution

### Key Files

- `internal/config/config.go:108-128` - Config struct definition with AllowedPythonDirs field
- `internal/config/config.go:695-703` - GetAllowedPythonDirs() getter method
- `internal/runner/runner.go:232` - safeScriptDirsEnv constant definition
- `internal/runner/runner.go:234-293` - resolvedSafeScriptDirs() function (currently env-only)
- `internal/runner/runner.go:757-877` - validatePythonCommandWithConfig() (uses AllowedPythonDirs for interpreter)
- `internal/tui/model.go:408-467` - initSettingsInputs() function (where new input must be added)
- `internal/tui/run.go:249-373` - populateConfigFromInputs() function (where parsing must be added)
- `internal/tui/view_settings.go:24-122` - Settings tab rendering (where UI must be added)
- `internal/tui/inputs.go:10-36` - settingsGrid layout (where input position must be defined)
- `internal/tui/keys_settings.go:24-115` - inputFieldAccessors map (where input must be registered)

### Current Patterns and Conventions

**TUI Input Pattern:**
1. Add field to `model` struct (e.g., `inAllowedPythonDirs textinput.Model`)
2. Add input name to `settingsInputNames` slice (line 235 in model.go)
3. Create input in `initSettingsInputs()` with `mkInput()`
4. Add to `settingsInputs` map with key and pointer
5. Add grid position to `settingsGrid` in inputs.go
6. Add getter/setter to `inputFieldAccessors` in keys_settings.go
7. Render in appropriate group in `view_settings.go`
8. Add to `booleanInputs` map if it's a toggle (not applicable here)
9. Parse value in `populateConfigFromInputs()` in run.go

**String Slice Pattern:**
The TUI doesn't currently have a pattern for editing string slices (arrays). All existing fields are:
- Single strings (repo, base, branch, etc.)
- Numeric integers (waitmin, pollsec, etc.)
- Booleans (ralph enabled, auto add signs, etc.)
- Enums (executor choices via toggles)

For `AllowedPythonDirs`, we need to either:
- Option A: Single-line text input with path-separated values (e.g., "/path1:/path2:/path3")
- Option B: Multi-line textarea for one path per line
- Option C: Dynamic list with add/remove functionality (most complex)

**Recommended:** Option A (single-line with path separators) matches existing patterns and is simplest to implement. The path separator can be OS-specific (`os.PathListSeparator`).

**Navigation Pattern:**
- Settings are organized in groups: Repository, Executors, Timings, Ralph
- Each group is rendered by a separate `render*Group()` function
- Grid positions are 2D arrays: `[row, column]`
- Current rows: 0-12 (row 12 has 2 columns)

## Technical Considerations

### Dependencies
- No external dependencies required
- Uses existing `github.com/charmbracelet/bubbles/textinput` for input
- Uses standard `os.PathListSeparator` for platform-appropriate separator (`:` on Unix, `;` on Windows)

### Integration Points

**Config Load/Save:**
- Already handled by existing `config.Load()` and `config.Save()` functions
- `AllowedPythonDirs` field is already serialized as `allowed_python_dirs` in YAML
- No migration needed (field already exists in current schema)

**Runner Integration:**
- For **Python interpreter validation**: Already uses `cfg.GetAllowedPythonDirs()` (lines 813-860 in runner.go)
  - Supports both prefix matching and regex patterns
  - Error message already instructs users to edit config (line 864-865)
- For **script directory validation**: Currently only uses environment variable
  - Need to merge config values into `resolvedSafeScriptDirs()`
  - Proposed: Add `SafeScriptDirs` field to Config struct
  - Update `resolvedSafeScriptDirs()` to read from both config and environment

**TUI Rendering:**
- Add to "Executors" group (most logical placement since it's about Python paths)
- Or create new "Security" group (may be overkill for single field)
- Place after `inPolicy` or in new row within Executors group

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **User confusion between AllowedPythonDirs and AUTO_PRD_SAFE_SCRIPT_DIRS** | High | Clear labeling and help text. AllowedPythonDirs = Python interpreter locations; SafeScriptDirs = automation script directory. |
| **Breaking existing environment variable workflows** | Medium | Keep env var as fallback/read-only. Merge config + env var, with config taking precedence. |
| **Path separator differences across platforms** | Low | Use `os.PathListSeparator` consistently. Show separator hint in placeholder. |
| **Invalid path syntax causing runtime errors** | Medium | Validate paths in `populateConfigFromInputs()`. Show warnings for invalid entries. |
| **Performance impact of path validation** | Low | Only validate on save, not on every keystroke. Same pattern as existing numeric fields. |
| **Backward compatibility with existing configs** | Medium | Field already exists in config schema. Default empty slice is safe. No migration needed. |

### Clarification on Two Separate Concepts

After thorough research, I've identified that the task description conflates two different security mechanisms:

1. **AllowedPythonDirs** (already in config):
   - Purpose: Validate Python **interpreter/binary** paths
   - Used by: `validatePythonCommandWithConfig()` in runner.go
   - Config field: Already exists at `config.go:126`
   - Missing: TUI exposure

2. **AUTO_PRD_SAFE_SCRIPT_DIRS** (env var only):
   - Purpose: Whitelist directories containing **automation scripts**
   - Used by: `resolvedSafeScriptDirs()` in runner.go
   - Config field: Does NOT exist
   - Missing: Config field + TUI exposure

**Recommendation:** Implement both for complete security control:
- Expose existing `AllowedPythonDirs` in TUI (simpler, field already exists)
- Add new `SafeScriptDirs` config field to replace env var dependency (requires new field)

## Recommended Approach

### Phase 1: Expose Existing AllowedPythonDirs (Lower Risk)

1. **Config Changes** (`internal/config/config.go`):
   - No changes needed (field already exists)
   - Already has: `AllowedPythonDirs []string` at line 126
   - Already has: `GetAllowedPythonDirs()` method at line 698
   - Already has: Default empty slice, cloning, equality checks

2. **TUI Model Changes** (`internal/tui/model.go`):
   - Add `inAllowedPythonDirs textinput.Model` field to struct (after line 159)
   - Add "allowedpythondirs" to `settingsInputNames` slice (after line 257)
   - Create input in `initSettingsInputs()`: `m.inAllowedPythonDirs = mkInput("Allowed Python dirs (path-separated)", joinPaths(cfg.AllowedPythonDirs), 60)`
   - Add to `settingsInputs` map: `"allowedpythondirs": &m.inAllowedPythonDirs`
   - Add to `blurAllInputs()`: `m.inAllowedPythonDirs.Blur()`

3. **TUI Keys Changes** (`internal/tui/keys_settings.go`):
   - Add accessor to `inputFieldAccessors` map:
   ```go
   "allowedpythondirs": {
       get: func(m *model) *textinput.Model { return &m.inAllowedPythonDirs },
       set: func(m *model, v string) { m.inAllowedPythonDirs.SetValue(v) },
   },
   ```

4. **TUI Inputs Changes** (`internal/tui/inputs.go`):
   - Add grid position: `"allowedpythondirs": {13, 0}` (new row after Ralph settings)
   - Add to `focusInput()` switch case

5. **TUI View Changes** (`internal/tui/view_settings.go`):
   - Add input to appropriate group (probably create new "Security" group or add to Executors)
   - Update group focus detection

6. **TUI Run Changes** (`internal/tui/run.go`):
   - Parse in `populateConfigFromInputs()`:
   ```go
   raw := m.inAllowedPythonDirs.Value()
   paths := parsePathList(raw) // Split by os.PathListSeparator
   dst.AllowedPythonDirs = paths
   ```

7. **Helper Function** (new in `internal/tui/helpers.go` or similar):
   ```go
   func joinPaths(paths []string) string {
       return strings.Join(paths, string(os.PathListSeparator))
   }

   func parsePathList(raw string) []string {
       if strings.TrimSpace(raw) == "" {
           return []string{}
       }
       parts := strings.Split(raw, string(os.PathListSeparator))
       result := make([]string, 0, len(parts))
       for _, part := range parts {
           if trimmed := strings.TrimSpace(part); trimmed != "" {
               result = append(result, trimmed)
           }
       }
       return result
   }
   ```

### Phase 2: Add SafeScriptDirs Config Field (Higher Impact)

This phase adds a config field to replace the `AUTO_PRD_SAFE_SCRIPT_DIRS` environment variable dependency.

1. **Config Changes** (`internal/config/config.go`):
   - Add `SafeScriptDirs []string` field to Config struct (line 127)
   - Add default empty slice in `Defaults()` (line 178)
   - Initialize in `LoadWithWarnings()` if nil (line 420-423)
   - Clone in `Clone()` method (line 496)
   - Compare in `Equal()` method (line 639)
   - Add `GetSafeScriptDirs()` getter method (line 704)

2. **Runner Changes** (`internal/runner/runner.go`):
   - Modify `resolvedSafeScriptDirs()` (line 234) to accept config parameter
   - Merge `cfg.GetSafeScriptDirs()` with environment variable
   - Config values should take precedence over env var
   - Update caller in `validatePythonScriptPath()` (line 184)

3. **TUI Changes** (same pattern as Phase 1):
   - Add `inSafeScriptDirs textinput.Model`
   - Follow same 7-step pattern as AllowedPythonDirs
   - Can use same helper functions for parsing

### Phase 3: Documentation and Testing

1. **Update Error Messages**:
   - Update runner.go line 864-865 to mention TUI Settings
   - Remove instruction to manually edit config.yaml
   - Add: "Configure via TUI Settings → Security"

2. **Add Tests**:
   - Unit test for `parsePathList()` helper
   - Unit test for `joinPaths()` helper
   - Integration test for config load/save with new field
   - TUI test for input field registration
   - Runner test for config + env var merge logic

3. **Update Documentation**:
   - Add help text in TUI: "Allowed Python directories (path-separated with : or ;)"
   - Document in user guide
   - Update README if it mentions the env var

## Open Questions

1. **Scope Decision:** Should we implement only Phase 1 (AllowedPythonDirs TUI exposure) or both phases?
   - Rationale: Phase 1 is safer and the field already exists
   - Phase 2 is more complex but provides complete control

2. **Input Format:** For path list input, which approach is best?
   - Single-line with separator (simplest, matches existing patterns)
   - Multi-line textarea (better UX for many paths)
   - Dynamic list (most complex but most intuitive)

3. **Group Placement:** Where should the new input go in the Settings UI?
   - Add to "Executors" group (related to Python paths)
   - Create new "Security" group (may be clearer separation)
   - Add to "Repository" group (if it's about repo security)

4. **Validation:** Should we validate that paths exist?
   - Current implementation doesn't validate path existence
   - May want to warn but not block (paths may be on different machines)
   - Could add "Validate Paths" button (complexity vs benefit tradeoff)

5. **Backward Compatibility:** How should we handle existing environment variable usage?
   - Recommended: Read from both config and env, merge with config taking precedence
   - Alternative: Config only, deprecate env var (breaking change)
   - Document the merge order clearly

6. **Regex Support:** AllowedPythonDirs supports regex patterns (line 842-850 in runner.go). Should the TUI:
   - Allow raw input and document regex syntax
   - Provide regex toggle/helper
   - Keep it simple and let advanced users edit config.yaml directly
