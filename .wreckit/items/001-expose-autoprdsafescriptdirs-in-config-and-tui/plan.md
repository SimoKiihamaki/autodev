# Expose AUTO_PRD_SAFE_SCRIPT_DIRS in config and TUI Implementation Plan

## Overview

Users must currently configure allowed script directories by setting the `AUTO_PRD_SAFE_SCRIPT_DIRS` environment variable manually outside the application. This creates a poor user experience and breaks the principle that all configuration should be accessible through the TUI Settings interface.

This implementation adds a new `SafeScriptDirs` field to the Config struct and exposes it in the TUI, allowing users to whitelist directories containing automation Python scripts through the standard Settings interface.

**Security Context:** The `AUTO_PRD_SAFE_SCRIPT_DIRS` mechanism prevents execution of arbitrary Python scripts by only allowing scripts from whitelisted directories. This is a critical security feature.

## Current State Analysis

### What Exists Now

1. **Environment Variable Only** (`internal/runner/runner.go:232`):
   - `safeScriptDirsEnv` constant defines `"AUTO_PRD_SAFE_SCRIPT_DIRS"`
   - Users must set this environment variable manually
   - No config field exists for this setting

2. **Script Validation** (`internal/runner/runner.go:234-293`):
   - `resolvedSafeScriptDirs()` function builds whitelist from:
     - Temporary autodev working directory
     - User-level autodev installation directory
     - Directories relative to the aprd executable
     - **Environment variable** `AUTO_PRD_SAFE_SCRIPT_DIRS` (lines 277-286)
   - `validatePythonScriptPath()` uses this whitelist (line 184)

3. **Environment Propagation** (`internal/runner/runner.go:991-1031`):
   - `ensureScriptDirWhitelisted()` adds script dir to env var for child processes
   - Script dir is merged into environment before execution (line 638)

### What's Missing

1. **Config Field**: No `SafeScriptDirs` field in Config struct
2. **TUI Exposure**: No input field in Settings tab
3. **Config-Env Integration**: Runner doesn't read from config for script dirs
4. **User Experience**: Users must manually edit environment variables

### Key Constraints Discovered

1. **Existing Pattern**: `AllowedPythonDirs` field already exists (line 126 in config.go) but serves a different purpose:
   - `AllowedPythonDirs`: Validates Python **interpreter/binary** paths
   - `SafeScriptDirs` (new): Whitelists directories for **automation scripts**

2. **Platform Differences**: Path separator varies by platform (`:` on Unix, `;` on Windows)
   - Use `os.PathListSeparator` consistently
   - Must handle parsing correctly in TUI

3. **Backward Compatibility**: Must preserve existing environment variable behavior
   - Read from both config and environment
   - Merge sources with appropriate precedence

4. **TUI Patterns**: No existing pattern for string slice inputs
   - Current fields: strings, integers, booleans, enums
   - Need to add path list parsing (single-line with separators)

## Desired End State

Users can configure allowed script directories through the TUI Settings interface. The configuration is saved to `config.yaml` and merged with the environment variable at runtime. Users no longer need to manually edit environment variables outside the application.

**Verification:**
- TUI Settings has "Allowed script dirs" input field
- Config file contains `safe_script_dirs` field
- Runner reads from both config and environment variable
- Error messages mention TUI Settings instead of config file editing
- Existing environment variable workflows continue to work

## What We're NOT Doing

1. **Exposing AllowedPythonDirs in TUI**: This field already exists in config for Python interpreter validation but is not part of this task. It could be a separate follow-up task.

2. **Removing Environment Variable Support**: The `AUTO_PRD_SAFE_SCRIPT_DIRS` environment variable will continue to work as a fallback/override mechanism.

3. **Path Validation UI**: We won't add interactive path validation buttons or existence checks in the TUI (too complex for this iteration).

4. **Multi-line Input**: Using single-line text input with path separators (e.g., "/path1:/path2") rather than multi-line textarea or dynamic list UI.

5. **Regex Pattern Support for Script Dirs**: Unlike AllowedPythonDirs which supports regex, SafeScriptDirs will only support literal directory paths (simpler and more appropriate for this use case).

## Implementation Approach

**High-level Strategy:**
1. Add `SafeScriptDirs` field to Config struct following existing patterns
2. Update runner to read from config and merge with environment variable
3. Add TUI input field with path list parsing helpers
4. Update error messages to reference TUI Settings
5. Test backward compatibility with environment variable

**Design Rationale:**
- **Single-line input**: Matches existing TUI patterns, simplest to implement
- **Config takes precedence**: Config is more discoverable than env vars
- **Merge behavior**: Config + env var, with config overriding duplicates
- **Helper functions**: Reusable for future string slice fields (e.g., AllowedPythonDirs exposure)

---

## Phase 1: Add SafeScriptDirs Config Field

### Overview
Add the `SafeScriptDirs` field to the Config struct and implement all necessary config infrastructure (defaults, loading, cloning, equality checks, getter method).

### Changes Required:

#### 1. Config Struct Field
**File**: `internal/config/config.go`
**Line**: 127 (after `AllowedPythonDirs`)

```go
type Config struct {
    // ... existing fields ...
    AllowedPythonDirs []string           `yaml:"allowed_python_dirs"`
    SafeScriptDirs    []string           `yaml:"safe_script_dirs"` // NEW: Whitelisted directories for automation scripts
    PRDs              map[string]PRDMeta `yaml:"prds"`
}
```

#### 2. Default Value
**File**: `internal/config/config.go`
**Line**: 178 (in `Defaults()` function)

```go
func Defaults() Config {
    return Config{
        // ... existing fields ...
        AllowedPythonDirs: []string{},
        SafeScriptDirs:    []string{}, // NEW: Default to empty slice
        PRDs:              make(map[string]PRDMeta),
    }
}
```

#### 3. Initialize on Load
**File**: `internal/config/config.go`
**Line**: 420-423 (in `LoadWithWarnings()` after AllowedPythonDirs initialization)

```go
func LoadWithWarnings(path string) (*Config, []string, error) {
    // ... existing code ...
    if cfg.AllowedPythonDirs == nil {
        cfg.AllowedPythonDirs = []string{}
    }
    if cfg.SafeScriptDirs == nil { // NEW: Initialize if nil
        cfg.SafeScriptDirs = []string{}
    }
    // ... rest of function ...
}
```

#### 4. Clone Method
**File**: `internal/config/config.go`
**Line**: 496 (in `Clone()` method after AllowedPythonDirs)

```go
func (c Config) Clone() Config {
    return Config{
        // ... existing fields ...
        AllowedPythonDirs: cloneStringSlice(c.AllowedPythonDirs),
        SafeScriptDirs:    cloneStringSlice(c.SafeScriptDirs), // NEW: Clone safe script dirs
        PRDs:              c.clonePRDs(),
    }
}
```

#### 5. Equal Method
**File**: `internal/config/config.go`
**Line**: 639 (in `Equal()` method after AllowedPythonDirs comparison)

```go
func (c Config) Equal(other Config) bool {
    // ... existing comparisons ...
    if !equalStringSlices(c.AllowedPythonDirs, other.AllowedPythonDirs) {
        return false
    }
    if !equalStringSlices(c.SafeScriptDirs, other.SafeScriptDirs) { // NEW: Compare safe script dirs
        return false
    }
    // ... rest of comparisons ...
}
```

#### 6. Getter Method
**File**: `internal/config/config.go`
**Line**: 704 (after `GetAllowedPythonDirs()`)

```go
// GetAllowedPythonDirs returns the list of allowed Python directories from the config.
func (c Config) GetAllowedPythonDirs() []string {
    if c.AllowedPythonDirs == nil {
        return []string{}
    }
    return append([]string(nil), c.AllowedPythonDirs...)
}

// GetSafeScriptDirs returns the list of safe script directories from the config.
// These directories are whitelisted for automation script execution.
func (c Config) GetSafeScriptDirs() []string {
    if c.SafeScriptDirs == nil {
        return []string{}
    }
    return append([]string(nil), c.SafeScriptDirs...)
}
```

### Success Criteria:

#### Automated Verification:
- [ ] Config compiles without errors: `go build ./internal/config`
- [ ] Unit tests pass: `go test ./internal/config`
- [ ] Default config has empty `safe_script_dirs` field when saved to YAML
- [ ] Config load initializes nil slices to empty slices
- [ ] Clone creates independent copy of SafeScriptDirs
- [ ] Equal returns false when SafeScriptDirs differs

#### Manual Verification:
- [ ] Create config with `safe_script_dirs: ["/tmp/scripts", "~/scripts"]`
- [ ] Load config and verify `GetSafeScriptDirs()` returns both paths
- [ ] Verify YAML serialization matches expected format
- [ ] Test that modifying returned slice doesn't affect config (defensive copy)

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 2.

---

## Phase 2: Update Runner to Use Config

### Overview
Modify `resolvedSafeScriptDirs()` to accept a config parameter and merge `SafeScriptDirs` with the environment variable. Update callers to pass the config.

### Changes Required:

#### 1. Update resolvedSafeScriptDirs Signature
**File**: `internal/runner/runner.go`
**Line**: 234

**Before:**
```go
func resolvedSafeScriptDirs() []string {
```

**After:**
```go
func resolvedSafeScriptDirs(cfg *config.Config) []string {
```

#### 2. Add Config Merging Logic
**File**: `internal/runner/runner.go`
**Line**: 277-286 (after environment variable parsing, before return)

**Add after line 286:**
```go
// Additional safe directories provided via environment variable (path list)
if extra := os.Getenv(safeScriptDirsEnv); extra != "" {
    sep := string(os.PathListSeparator)
    for _, part := range strings.Split(extra, sep) {
        part = strings.TrimSpace(part)
        if part == "" {
            continue
        }
        addIfDir(part, dirs)
    }
}

// NEW: Merge with config SafeScriptDirs (config takes precedence over env var)
if cfg != nil {
    for _, dir := range cfg.GetSafeScriptDirs() {
        addIfDir(dir, dirs)
    }
}
```

**Alternative approach (config overrides env var duplicates):**
```go
// Build map from env var first
envDirs := make(map[string]struct{})
if extra := os.Getenv(safeScriptDirsEnv); extra != "" {
    sep := string(os.PathListSeparator)
    for _, part := range strings.Split(extra, sep) {
        part = strings.TrimSpace(part)
        if part == "" {
            continue
        }
        addIfDir(part, envDirs)
    }
}

// Merge env dirs into main set
for dir := range envDirs {
    dirs[dir] = struct{}{}
}

// Add config dirs (config takes precedence, will deduplicate via addIfDir)
if cfg != nil {
    for _, dir := range cfg.GetSafeScriptDirs() {
        addIfDir(dir, dirs)
    }
}
```

#### 3. Update Caller
**File**: `internal/runner/runner.go`
**Line**: 184 (in `validatePythonScriptPath()`)

**Before:**
```go
safeDirs := resolvedSafeScriptDirs()
```

**After:**
```go
safeDirs := resolvedSafeScriptDirs(cfg)
```

**Note**: Verify that `cfg` is available in this scope. If not, pass it as a parameter to `validatePythonScriptPath()`.

### Success Criteria:

#### Automated Verification:
- [ ] Runner compiles without errors: `go build ./internal/runner`
- [ ] Unit tests pass: `go test ./internal/runner`
- [ ] Environment variable only: `resolvedSafeScriptDirs(nil)` returns env var paths
- [ ] Config only: `resolvedSafeScriptDirs(cfg)` returns config paths
- [ ] Both env and config: Paths are merged, no duplicates
- [ ] Config takes precedence: Config paths override env var paths if duplicates
- [ ] Nil config handled: `resolvedSafeScriptDirs(nil)` doesn't crash

#### Manual Verification:
- [ ] Set `AUTO_PRD_SAFE_SCRIPT_DIRS=/tmp/scripts` env var
- [ ] Set config `safe_script_dirs: [~/scripts]`
- [ ] Verify both directories appear in resolved list
- [ ] Remove env var, verify config paths still work
- [ ] Remove config paths, verify env var still works
- [ ] Test with script in whitelisted directory (validation passes)
- [ ] Test with script in non-whitelisted directory (validation fails)

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 3.

---

## Phase 3: Add TUI Helpers for Path Lists

### Overview
Add helper functions to parse and format path lists for TUI input. These functions convert between string slices (config) and path-separated strings (TUI input).

### Changes Required:

#### 1. Add Helper Functions
**File**: `internal/tui/helpers.go`
**Line**: 76 (after `wrapIndex()`)

```go
// joinPaths converts a string slice to a path-separated string using OS-specific separator.
// Empty or nil slices return empty string.
func joinPaths(paths []string) string {
    if len(paths) == 0 {
        return ""
    }
    return strings.Join(paths, string(os.PathListSeparator))
}

// parsePathList splits a path-separated string into a string slice using OS-specific separator.
// Empty strings and extra whitespace are trimmed. Returns empty slice for empty input.
func parsePathList(raw string) []string {
    raw = strings.TrimSpace(raw)
    if raw == "" {
        return []string{}
    }
    sep := string(os.PathListSeparator)
    parts := strings.Split(raw, sep)
    result := make([]string, 0, len(parts))
    for _, part := range parts {
        if trimmed := strings.TrimSpace(part); trimmed != "" {
            result = append(result, trimmed)
        }
    }
    return result
}
```

**Note**: Add `import "os"` to helpers.go if not already present.

#### 2. Add Unit Tests
**File**: `internal/tui/helpers_test.go` (create if doesn't exist)

```go
package tui

import (
    "os"
    "testing"
)

func TestJoinPaths(t *testing.T) {
    tests := []struct {
        name     string
        paths    []string
        expected string
    }{
        {"empty slice", []string{}, ""},
        {"nil slice", nil, ""},
        {"single path", []string{"/tmp/scripts"}, "/tmp/scripts"},
        {"multiple paths", []string{"/tmp/scripts", "~/scripts", "/opt/automation"},
            "/tmp/scripts:" + "~/scripts:" + "/opt/automation"}, // Unix
        {"paths with spaces", []string{"/tmp/my scripts", "~/scripts"},
            "/tmp/my scripts:" + "~/scripts"},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            result := joinPaths(tt.paths)
            // Adjust expected based on OS
            expected := tt.expected
            if os.PathListSeparator == ';' {
                expected = strings.ReplaceAll(expected, ":", ";")
            }
            if result != expected {
                t.Errorf("joinPaths(%v) = %q, want %q", tt.paths, result, expected)
            }
        })
    }
}

func TestParsePathList(t *testing.T) {
    tests := []struct {
        name     string
        raw      string
        expected []string
    }{
        {"empty string", "", []string{}},
        {"whitespace only", "   ", []string{}},
        {"single path", "/tmp/scripts", []string{"/tmp/scripts"}},
        {"multiple paths", "/tmp/scripts:~/scripts:/opt/automation",
            []string{"/tmp/scripts", "~/scripts", "/opt/automation"}},
        {"extra separators", "/tmp/scripts::~/scripts:",
            []string{"/tmp/scripts", "~/scripts"}},
        {"spaces around paths", " /tmp/scripts : ~/scripts ",
            []string{"/tmp/scripts", "~/scripts"}},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            result := parsePathList(tt.raw)
            // Adjust input based on OS
            raw := tt.raw
            if os.PathListSeparator == ';' && strings.Contains(raw, ":") {
                raw = strings.ReplaceAll(raw, ":", ";")
            }
            result = parsePathList(raw)
            if !equalStringSlices(result, tt.expected) {
                t.Errorf("parsePathList(%q) = %v, want %v", tt.raw, result, tt.expected)
            }
        })
    }
}

// Helper for comparing string slices in tests
func equalStringSlices(a, b []string) bool {
    if len(a) != len(b) {
        return false
    }
    for i := range a {
        if a[i] != b[i] {
            return false
        }
    }
    return true
}
```

### Success Criteria:

#### Automated Verification:
- [ ] TUI compiles without errors: `go build ./internal/tui`
- [ ] Unit tests pass: `go test ./internal/tui`
- [ ] `joinPaths([]string{})` returns `""`
- [ ] `joinPaths([]string{"/tmp", "~/scripts"})` returns `"/tmp:~/scripts"` (Unix) or `"/tmp;~/scripts"` (Windows)
- [ ] `parsePathList("")` returns `[]string{}`
- [ ] `parsePathList("/tmp:~/scripts")` returns `[]string{"/tmp", "~/scripts"}` (Unix)
- [ ] `parsePathList("/tmp::~/scripts:")` trims empty parts and returns `[]string{"/tmp", "~/scripts"}`
- [ ] Round-trip: `parsePathList(joinPaths(paths)) == paths` for various inputs

#### Manual Verification:
- [ ] Test on Unix system with `:` separator
- [ ] Test on Windows system with `;` separator (if available)
- [ ] Verify paths with spaces are handled correctly
- [ ] Verify extra whitespace is trimmed

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 4.

---

## Phase 4: Add TUI Model Input

### Overview
Add the `inSafeScriptDirs` field to the TUI model struct and initialize it in `initSettingsInputs()`. Register it in the settings inputs map and input field accessors.

### Changes Required:

#### 1. Add Model Field
**File**: `internal/tui/model.go`
**Line**: 160 (after Ralph settings inputs, before `settingsInputs`)

```go
type model struct {
    // ... existing fields ...
    inRalphGutterTimeout    textinput.Model
    inRalphGutterNoProgress textinput.Model
    inSafeScriptDirs        textinput.Model // NEW: Safe script directories input

    settingsInputs map[string]*textinput.Model
    // ... rest of fields ...
}
```

#### 2. Initialize Input
**File**: `internal/tui/model.go`
**Line**: 434 (in `initSettingsInputs()`, after Ralph inputs initialization)

```go
func (m *model) initSettingsInputs() {
    cfg := m.cfg

    // ... existing input initializations ...

    // Ralph settings inputs
    m.inRalphEnabled = mkInput("Ralph enabled (true/false)", formatBool(cfg.Ralph.Enabled), 6)
    // ... other Ralph inputs ...
    m.inRalphGutterNoProgress = mkInput("Gutter no progress iters", formatIntPtr(cfg.Ralph.GutterNoProgressIters), 6)

    // NEW: Safe script directories input
    m.inSafeScriptDirs = mkInput("Allowed script dirs (path-separated)", joinPaths(cfg.SafeScriptDirs), 80)

    m.settingsInputs = map[string]*textinput.Model{
        // ... existing mappings ...
        "ralphguttertimeout":    &m.inRalphGutterTimeout,
        "ralphgutternoprogress": &m.inRalphGutterNoProgress,
        "safescriptdirs":        &m.inSafeScriptDirs, // NEW: Add to map
    }
```

#### 3. Add to Blur Function
**File**: `internal/tui/inputs.go`
**Line**: 60 (in `blurAllInputs()`, after Ralph blur calls)

```go
func (m *model) blurAllInputs() {
    // ... existing blur calls ...
    m.inRalphGutterTimeout.Blur()
    m.inRalphGutterNoProgress.Blur()
    m.inSafeScriptDirs.Blur() // NEW: Blur on initialization
}
```

#### 4. Add Input Field Accessor
**File**: `internal/tui/keys_settings.go`
**Line**: 115 (in `inputFieldAccessors` map, after Ralph accessors)

```go
var inputFieldAccessors = map[string]struct {
    get inputFieldGetter
    set inputFieldSetter
}{
    // ... existing accessors ...
    "ralphgutternoprogress": {
        get: func(m *model) *textinput.Model { return &m.inRalphGutterNoProgress },
        set: func(m *model, v string) { m.inRalphGutterNoProgress.SetValue(v) },
    },
    "safescriptdirs": { // NEW: Add accessor
        get: func(m *model) *textinput.Model { return &m.inSafeScriptDirs },
        set: func(m *model, v string) { m.inSafeScriptDirs.SetValue(v) },
    },
}
```

#### 5. Add Grid Position
**File**: `internal/tui/inputs.go`
**Line**: 36 (in `settingsGrid` map)

```go
var settingsGrid = map[string][2]int{
    // ... existing positions ...
    // Ralph settings (rows 10-12)
    "ralphenabled":          {10, 0},
    "ralphcontextrotate":    {10, 1},
    "ralphmaxconsecutive":   {10, 2},
    "ralphautoaddsigns":     {11, 0},
    "ralphshowprogresslog":  {11, 1},
    "ralphshowguardrails":   {11, 2},
    "ralphguttertimeout":    {12, 0},
    "ralphgutternoprogress": {12, 1},
    // NEW: Safe script dirs (row 13, full width)
    "safescriptdirs":        {13, 0},
}
```

#### 6. Add to Focus Navigation
**File**: `internal/tui/inputs.go`
**Line**: 80 (in `focusInput()` switch, add case for "safescriptdirs")

```go
func (m *model) focusInput(key string) {
    // ... existing cases ...
    case "ralphgutternoprogress":
        m.inRalphGutterNoProgress.Focus()
    case "safescriptdirs": // NEW: Handle focus
        m.inSafeScriptDirs.Focus()
    default:
        return
    }
    // ... rest of function ...
}
```

### Success Criteria:

#### Automated Verification:
- [ ] TUI compiles without errors: `go build ./internal/tui`
- [ ] Unit tests pass: `go test ./internal/tui`
- [ ] Model field is properly initialized
- [ ] Input is registered in `settingsInputs` map
- [ ] Input is registered in `inputFieldAccessors` map
- [ ] Grid position is defined
- [ ] Focus handler includes case for "safescriptdirs"
- [ ] Blur is called on initialization

#### Manual Verification:
- [ ] Launch TUI and navigate to Settings tab
- [ ] Verify input field is visible in UI
- [ ] Tab through inputs and verify focus reaches the new field
- [ ] Verify placeholder text shows current config value
- [ ] Verify field width is appropriate (80 chars)

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 5.

---

## Phase 5: Add TUI View Rendering

### Overview
Add the input field to the Settings view by creating a new "Security" group or adding to an existing group. Update focus detection for the group.

### Changes Required:

#### 1. Render Input in View (Create Security Group)
**File**: `internal/tui/view_settings.go`
**Line**: 83 (after `renderRalphGroup()`)

```go
// renderRalphGroup renders the Ralph autonomous iteration settings group.
func renderRalphGroup(b *strings.Builder, m model) {
    // ... existing code ...
}

// renderSecurityGroup renders the security settings group.
func renderSecurityGroup(b *strings.Builder, m model) {
    securityContent := lipgloss.JoinVertical(lipgloss.Left,
        m.inSafeScriptDirs.View(),
    )
    securityBox := NewBorderedBox("Security", securityContent)
    securityBox.Focused = isInSettingsGroup(m.focusedInput, []string{"safescriptdirs"})
    b.WriteString(securityBox.Render() + "\n\n")
}
```

#### 2. Call from Main View Function
**File**: `internal/tui/view_settings.go`
**Line**: 30 (in `renderSettingsView()`)

**Before:**
```go
func renderSettingsView(b *strings.Builder, m model) {
    b.WriteString(sectionTitle.Render("Settings") + "\n\n")

    renderRepositoryGroup(b, m)
    renderExecutorsGroup(b, m)
    renderTimingsGroup(b, m)
    renderRalphGroup(b, m)
    renderSettingsHelp(b, m)
}
```

**After:**
```go
func renderSettingsView(b *strings.Builder, m model) {
    b.WriteString(sectionTitle.Render("Settings") + "\n\n")

    renderRepositoryGroup(b, m)
    renderExecutorsGroup(b, m)
    renderTimingsGroup(b, m)
    renderRalphGroup(b, m)
    renderSecurityGroup(b, m) // NEW: Add security group
    renderSettingsHelp(b, m)
}
```

**Alternative: Add to Ralph Group** (if new group is undesirable):

```go
func renderRalphGroup(b *strings.Builder, m model) {
    // ... existing Ralph inputs ...

    // Add security input
    ralphContent := lipgloss.JoinVertical(lipgloss.Left,
        // ... existing Ralph content ...
        m.inSafeScriptDirs.View(), // NEW: Add security field here
    )
    // Update focus detection
    ralphBox.Focused = isInSettingsGroup(m.focusedInput, []string{
        // ... existing Ralph inputs ...
        "safescriptdirs", // NEW: Include in focus detection
    })
    // ... rest of function ...
}
```

**Recommendation**: Create separate "Security" group for clarity and future extensibility.

### Success Criteria:

#### Automated Verification:
- [ ] TUI compiles without errors: `go build ./internal/tui`
- [ ] View rendering doesn't panic
- [ ] Focus detection works for the security group

#### Manual Verification:
- [ ] Launch TUI and navigate to Settings tab
- [ ] Verify "Security" group appears (or input appears in Ralph group)
- [ ] Verify input is properly styled and aligned
- [ ] Tab into the field and verify group border shows focus state
- [ ] Verify visual consistency with other groups

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 6.

---

## Phase 6: Parse Input in TUI Run Handler

### Overview
Add parsing logic in `populateConfigFromInputs()` to convert the path-separated string back to a string slice and populate the config.

### Changes Required:

#### 1. Parse and Populate Config
**File**: `internal/tui/run.go`
**Line**: 330 (in `populateConfigFromInputs()`, after Ralph field parsing)

```go
func (m *model) populateConfigFromInputs(dst *config.Config) ([]string, []numericParseError) {
    // ... existing field assignments ...

    // Ralph settings
    dst.Ralph.Enabled, _ = parseBoolSafe(m.inRalphEnabled.Value())
    // ... other Ralph field parsing ...

    // NEW: Safe script directories
    dst.SafeScriptDirs = parsePathList(m.inSafeScriptDirs.Value())

    return invalid, parseErrs
}
```

**Note**: No error collection needed for path list parsing (empty list is valid).

### Success Criteria:

#### Automated Verification:
- [ ] TUI compiles without errors: `go build ./internal/tui`
- [ ] Unit tests pass: `go test ./internal/tui`
- [ ] Empty input results in empty slice
- [ ] Single path is parsed correctly
- [ ] Multiple paths are parsed correctly
- [ ] Extra separators and whitespace are handled
- [ ] Config is properly populated when saving

#### Manual Verification:
- [ ] Launch TUI and navigate to Settings
- [ ] Enter single path: `/tmp/scripts`
- [ ] Save and verify config file has `safe_script_dirs: ["/tmp/scripts"]`
- [ ] Enter multiple paths: `/tmp/scripts:~/automation:/opt/tools`
- [ ] Save and verify config file has all three paths
- [ ] Enter empty value and verify config has empty list
- [ ] Enter paths with spaces: `/tmp/my scripts:~/automation tools`
- [ ] Verify spaces are preserved in config

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to Phase 7.

---

## Phase 7: Update Error Messages

### Overview
Update error messages that mention editing config file to reference the TUI Settings interface instead. This improves discoverability.

### Changes Required:

#### 1. Update Script Validation Error (if exists)
**File**: `internal/runner/runner.go`
**Line**: 184-230 (in `validatePythonScriptPath()`)

Search for error messages that mention:
- "config file"
- "config.yaml"
- "environment variable"
- "manually edit"

Replace with references to TUI Settings.

**Example (if such message exists):**
```go
// Before:
return fmt.Errorf("script path %q is not in allowed directories; add to %s environment variable", scriptPath, safeScriptDirsEnv)

// After:
return fmt.Errorf("script path %q is not in allowed directories; configure allowed directories in TUI Settings → Security", scriptPath)
```

**Note**: Check if this error message exists. The current implementation may not have a user-facing error for script validation failures.

#### 2. Update Interpreter Validation Error (For Reference)
**File**: `internal/runner/runner.go`
**Line**: 862-866 (in `validatePythonCommandWithConfig()`)

**Before:**
```go
if !allowed {
    return fmt.Errorf("interpreter path %q is not in allowed directories; "+
        "to permit this interpreter, add its directory as a prefix or a regex pattern "+
        "to allowed_python_dirs in your config file (e.g., ~/.config/aprd/config.yaml): "+
        "allowed_python_dirs: [%s] or as regex: ['^%s([/\\\\]|$)']",
        absPath, filepath.Dir(absPath), regexp.QuoteMeta(filepath.Dir(absPath)))
}
```

**After:**
```go
if !allowed {
    return fmt.Errorf("interpreter path %q is not in allowed directories; "+
        "to permit this interpreter, add its directory as a prefix or a regex pattern "+
        "via TUI Settings → Executors, or edit allowed_python_dirs in your config file: "+
        "allowed_python_dirs: [%s] or as regex: ['^%s([/\\\\]|$)']",
        absPath, filepath.Dir(absPath), regexp.QuoteMeta(filepath.Dir(absPath)))
}
```

**Note**: This is for AllowedPythonDirs (different field), but included for completeness. Consider updating if exposing that field in the future.

### Success Criteria:

#### Automated Verification:
- [ ] Runner compiles without errors: `go build ./internal/runner`
- [ ] Unit tests pass: `go test ./internal/runner`
- [ ] Error messages don't reference raw config file paths as primary option
- [ ] TUI Settings is mentioned as the configuration method

#### Manual Verification:
- [ ] Trigger validation error (if applicable) and verify message
- [ ] Verify message mentions TUI Settings
- [ ] Verify message is clear and actionable

**Note**: Complete all automated verification, then pause for manual confirmation before proceeding to final testing.

---

## Testing Strategy

### Integration Test: Full Workflow

**File**: `internal/tui/run_integration_test.go` or create new `internal/tui/settings_integration_test.go`

```go
package tui

import (
    "os"
    "path/filepath"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
)

func TestSafeScriptDirsIntegration(t *testing.T) {
    // Create temp config
    tmpDir := t.TempDir()
    cfgPath := filepath.Join(tmpDir, "config.yaml")

    // Test 1: Save and load config with safe_script_dirs
    t.Run("save and load config", func(t *testing.T) {
        cfg := config.Defaults()
        cfg.SafeScriptDirs = []string{"/tmp/scripts", "~/automation", "/opt/tools"}

        err := config.Save(cfgPath, cfg)
        require.NoError(t, err)

        loaded, warnings, err := config.LoadWithWarnings(cfgPath)
        require.NoError(t, err)
        assert.Empty(t, warnings)
        assert.Equal(t, []string{"/tmp/scripts", "~/automation", "/opt/tools"}, loaded.SafeScriptDirs)
    })

    // Test 2: Parse from TUI input
    t.Run("parse from TUI input", func(t *testing.T) {
        sep := string(os.PathListSeparator)
        input := "/tmp/scripts" + sep + "~/automation" + sep + "/opt/tools"
        parsed := parsePathList(input)
        assert.Equal(t, []string{"/tmp/scripts", "~/automation", "/opt/tools"}, parsed)
    })

    // Test 3: Format for TUI input
    t.Run("format for TUI input", func(t *testing.T) {
        paths := []string{"/tmp/scripts", "~/automation", "/opt/tools"}
        formatted := joinPaths(paths)
        sep := string(os.PathListSeparator)
        expected := "/tmp/scripts" + sep + "~/automation" + sep + "/opt/tools"
        assert.Equal(t, expected, formatted)
    })

    // Test 4: Round-trip through TUI
    t.Run("round-trip through TUI", func(t *testing.T) {
        original := []string{"/tmp/scripts", "~/automation", "/opt/tools"}
        formatted := joinPaths(original)
        parsed := parsePathList(formatted)
        assert.Equal(t, original, parsed)
    })

    // Test 5: Empty input handling
    t.Run("empty input handling", func(t *testing.T) {
        parsed := parsePathList("")
        assert.Equal(t, []string{}, parsed)

        formatted := joinPaths([]string{})
        assert.Equal(t, "", formatted)

        formatted = joinPaths(nil)
        assert.Equal(t, "", formatted)
    })

    // Test 6: Whitespace and separator handling
    t.Run("whitespace and separator handling", func(t *testing.T) {
        sep := string(os.PathListSeparator)
        input := " /tmp/scripts " + sep + sep + " ~/automation " + sep + sep
        parsed := parsePathList(input)
        assert.Equal(t, []string{"/tmp/scripts", "~/automation"}, parsed)
    })
}
```

### Integration Test: Runner Config Merge

**File**: `internal/runner/runner_integration_test.go` or create new test file

```go
package runner

import (
    "os"
    "testing"

    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"

    "github.com/user/autodev/internal/config"
)

func TestResolvedSafeScriptDirs(t *testing.T) {
    // Test 1: Environment variable only
    t.Run("environment variable only", func(t *testing.T) {
        sep := string(os.PathListSeparator)
        envValue := "/tmp/env/scripts" + sep + "~/env/automation"
        t.Setenv(safeScriptDirsEnv, envValue)
        defer os.Unsetenv(safeScriptDirsEnv)

        dirs := resolvedSafeScriptDirs(nil)
        assert.Contains(t, dirs, "/tmp/env/scripts")
        assert.Contains(t, dirs, "~/env/automation")
    })

    // Test 2: Config only
    t.Run("config only", func(t *testing.T) {
        os.Unsetenv(safeScriptDirsEnv)

        cfg := &config.Config{
            SafeScriptDirs: []string{"/tmp/cfg/scripts", "~/cfg/automation"},
        }

        dirs := resolvedSafeScriptDirs(cfg)
        assert.Contains(t, dirs, "/tmp/cfg/scripts")
        assert.Contains(t, dirs, "~/cfg/automation")
    })

    // Test 3: Both env and config (merge)
    t.Run("both env and config", func(t *testing.T) {
        sep := string(os.PathListSeparator)
        envValue := "/tmp/env/scripts"
        t.Setenv(safeScriptDirsEnv, envValue)
        defer os.Unsetenv(safeScriptDirsEnv)

        cfg := &config.Config{
            SafeScriptDirs: []string{"/tmp/cfg/scripts"},
        }

        dirs := resolvedSafeScriptDirs(cfg)
        assert.Contains(t, dirs, "/tmp/env/scripts", "env var paths should be included")
        assert.Contains(t, dirs, "/tmp/cfg/scripts", "config paths should be included")
    })

    // Test 4: Config takes precedence (no duplicates)
    t.Run("no duplicates in merge", func(t *testing.T) {
        sep := string(os.PathListSeparator)
        envValue := "/tmp/scripts"
        t.Setenv(safeScriptDirsEnv, envValue)
        defer os.Unsetenv(safeScriptDirsEnv)

        cfg := &config.Config{
            SafeScriptDirs: []string{"/tmp/scripts"}, // Same path as env
        }

        dirs := resolvedSafeScriptDirs(cfg)
        count := 0
        for _, dir := range dirs {
            if dir == "/tmp/scripts" {
                count++
            }
        }
        assert.Equal(t, 1, count, "should not have duplicates")
    })

    // Test 5: Nil config
    t.Run("nil config", func(t *testing.T) {
        sep := string(os.PathListSeparator)
        envValue := "/tmp/scripts"
        t.Setenv(safeScriptDirsEnv, envValue)
        defer os.Unsetenv(safeScriptDirsEnv)

        dirs := resolvedSafeScriptDirs(nil) // Should not panic
        assert.Contains(t, dirs, "/tmp/scripts")
    })
}
```

### Manual Testing Steps

1. **Fresh Install Test**:
   ```bash
   # Remove existing config
   rm ~/.config/aprd/config.yaml

   # Launch TUI
   aprd

   # Navigate to Settings → Security
   # Verify "Allowed script dirs" field shows empty
   # Enter paths: /tmp/scripts:~/automation
   # Save and exit

   # Verify config file contains:
   # safe_script_dirs:
   #   - /tmp/scripts
   #   - ~/automation
   ```

2. **Existing Config Migration Test**:
   ```bash
   # Set environment variable
   export AUTO_PRD_SAFE_SCRIPT_DIRS=/tmp/env/scripts

   # Launch TUI with existing config
   aprd

   # Navigate to Settings → Security
   # Verify field shows existing config value
   # Add new path via TUI: /opt/tools
   # Save and exit

   # Run automation script from /tmp/env/scripts (env var path)
   # Verify it works

   # Run automation script from /opt/tools (config path)
   # Verify it works
   ```

3. **Cross-Platform Test** (if possible):
   - Test on Unix with `:` separator
   - Test on Windows with `;` separator
   - Verify paths with spaces work on both platforms

4. **Error Handling Test**:
   - Try to run script from non-whitelisted directory
   - Verify error message mentions TUI Settings
   - Add directory to whitelist via TUI
   - Verify script now runs

5. **Backward Compatibility Test**:
   - Set `AUTO_PRD_SAFE_SCRIPT_DIRS` without any config
   - Verify scripts in env var paths still work
   - Verify no regression in existing functionality

## Migration Notes

### No Schema Migration Required

The `SafeScriptDirs` field is a new addition to the config schema. Existing configs without this field will default to an empty slice (`[]string{}`), which is safe and correct behavior.

**User Impact:**
- **Existing users**: No impact. Environment variable continues to work. Config field defaults to empty.
- **New users**: Can use TUI Settings immediately. No manual config editing needed.

**Environment Variable Behavior:**
- **Preserved**: `AUTO_PRD_SAFE_SCRIPT_DIRS` continues to work
- **Merged**: Config and env var paths are combined
- **Precedence**: Config takes priority over env var for duplicates
- **Fallback**: Env var works if config field is empty

**Upgrade Path:**
1. User updates to new version
2. Launches TUI
3. Navigates to Settings → Security
4. Enters script directories
5. Saves config
6. (Optional) Removes `AUTO_PRD_SAFE_SCRIPT_DIRS` from shell profile

**Rollback:**
- If user downgrades to previous version:
  - Config field is ignored (not read by old version)
  - Environment variable continues to work
  - No data loss or corruption

## References

### Research Summary
- Research findings: `/Users/simo/Projects/autodev/.wreckit/items/001-expose-autoprdsafescriptdirs-in-config-and-tui/research.md`

### Key Files
- `internal/config/config.go:108-128` - Config struct definition (add SafeScriptDirs at line 127)
- `internal/config/config.go:130-178` - Defaults() function (add SafeScriptDirs default)
- `internal/config/config.go:350-423` - LoadWithWarnings() function (initialize if nil)
- `internal/config/config.go:467-515` - Clone() method (clone SafeScriptDirs)
- `internal/config/config.go:600-650` - Equal() method (compare SafeScriptDirs)
- `internal/config/config.go:695-703` - GetAllowedPythonDirs() method (add GetSafeScriptDirs after)

- `internal/runner/runner.go:232` - safeScriptDirsEnv constant
- `internal/runner/runner.go:234-293` - resolvedSafeScriptDirs() function (modify to accept cfg)
- `internal/runner/runner.go:184` - validatePythonScriptPath() caller (update call)

- `internal/tui/helpers.go:76` - Add joinPaths() and parsePathList() helpers
- `internal/tui/helpers_test.go` - Add unit tests for helpers

- `internal/tui/model.go:160` - Add inSafeScriptDirs field
- `internal/tui/model.go:408-467` - initSettingsInputs() function
- `internal/tui/inputs.go:10-36` - settingsGrid layout
- `internal/tui/inputs.go:38-76` - blurAllInputs() and focusInput()
- `internal/tui/keys_settings.go:24-115` - inputFieldAccessors map
- `internal/tui/view_settings.go:24-122` - Settings tab rendering
- `internal/tui/run.go:249-373` - populateConfigFromInputs() function

### Existing Patterns to Follow
- String slice field: `AllowedPythonDirs []string` at config.go:126
- Getter method: `GetAllowedPythonDirs()` at config.go:698
- Input initialization: `mkInput()` pattern in model.go:408-433
- Grid position: 2D array `[row, column]` in inputs.go:10-36
- Field accessor: Getter/setter functions in keys_settings.go:27-115
- View rendering: Group-based rendering in view_settings.go:24-122
- Config parsing: Direct assignment in run.go:249-373

### Constants
- `os.PathListSeparator` - Platform-appropriate path separator (`:` or `;`)
- `safeScriptDirsEnv` = `"AUTO_PRD_SAFE_SCRIPT_DIRS"` at runner.go:232
