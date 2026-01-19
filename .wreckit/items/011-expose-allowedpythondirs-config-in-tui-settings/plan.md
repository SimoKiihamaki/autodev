# Expose AllowedPythonDirs config in TUI Settings Implementation Plan

## Overview

Add a new text input field in the TUI Settings tab to expose the `allowed_python_dirs` configuration field, which currently can only be configured by manually editing `~/.config/aprd/config.yaml`. This provides a consistent configuration experience through the TUI interface for managing allowed Python interpreter directories.

## Current State Analysis

### What Exists Now

1. **Config Field Already Defined**: `AllowedPythonDirs` is a fully-functional config field (`internal/config/config.go:126`)
   - Default: empty slice `[]string{}`
   - Used by Python runner for security validation (`internal/runner/runner.go:821`)
   - Has getter method: `GetAllowedPythonDirs()` (`internal/config/config.go:706-714`)

2. **TUI Pattern Already Established**: `SafeScriptDirs` is exposed in TUI and serves as a perfect template
   - Model field: `inSafeScriptDirs` (`internal/tui/model.go:162`)
   - Input initialization with path joining (`internal/tui/model.go:441`)
   - Grid positioning (`internal/tui/inputs.go:37`)
   - Input accessor mapping (`internal/tui/keys_settings.go:115-118`)
   - Config population with path parsing (`internal/tui/run.go:356`)
   - View rendering in Security group (`internal/tui/view_settings.go:112-120`)

3. **Helper Functions Available**: OS-aware path utilities already exist
   - `joinPaths()` - converts slice to path-separated string (`internal/tui/helpers.go:78-85`)
   - `parsePathList()` - splits path-separated string into slice (`internal/tui/helpers.go:87-103`)
   - Both use `os.PathListSeparator` (colon on Unix, semicolon on Windows)

### What's Missing

The TUI interface does not expose `AllowedPythonDirs` despite:
- The field being fully functional in the config system
- An identical pattern already existing for `SafeScriptDirs`
- User need to configure this without manual YAML editing
- No breaking changes required (field already persists)

## Desired End State

### Functional Requirements

1. Users can view and edit `allowed_python_dirs` in the TUI Settings tab
2. The field is located in the Security settings group alongside `safescriptdirs`
3. Changes are persisted to `~/.config/aprd/config.yaml` on save
4. Existing `allowed_python_dirs` values are automatically loaded on TUI startup
5. Path separator works correctly on all platforms (Unix: `:`, Windows: `;`)

### Non-Functional Requirements

1. No breaking changes to existing configs or functionality
2. Consistent UX with existing `SafeScriptDirs` field
3. Code follows established patterns (minimal deviation from template)
4. Navigation works with arrow keys and tab

### Verification

**Manual Testing Checklist:**
- [ ] Field appears in Security group in Settings tab
- [ ] Field can be focused with arrow keys/navigation
- [ ] Field accepts path-separated input (e.g., `/usr/bin:/usr/local/bin` on Unix)
- [ ] Changes trigger "dirty" state indicator
- [ ] Save persists changes to `config.yaml`
- [ ] Reload shows saved values correctly
- [ ] Empty field is handled gracefully
- [ ] Existing values from config are loaded on startup

**Cross-Platform Testing:**
- [ ] Path separator works on macOS/Linux (colon `:`)
- [ ] Path separator works on Windows (semicolon `;`)

## Key Discoveries

### Critical File Locations

- **Config Definition**: `internal/config/config.go:126` - `AllowedPythonDirs` field
- **Config Getter**: `internal/config/config.go:706-714` - `GetAllowedPythonDirs()` method
- **Usage in Runner**: `internal/runner/runner.go:821` - Python validation uses this field
- **Template Field**: `internal/tui/model.go:162` - `inSafeScriptDirs` (exact pattern to follow)
- **Template Init**: `internal/tui/model.go:441` - Initialization with `joinPaths()`
- **Template Grid**: `internal/tui/inputs.go:37` - Grid positioning
- **Template Accessors**: `internal/tui/keys_settings.go:115-118` - Getter/setter mapping
- **Template Parsing**: `internal/tui/run.go:356` - Config population with `parsePathList()`
- **Template View**: `internal/tui/view_settings.go:112-120` - Security group rendering

### Pattern to Follow

The implementation should mirror `SafeScriptDirs` exactly:

1. **Field naming**: `inAllowedPythonDirs` (model) → `"allowedpythondirs"` (settings key)
2. **Placeholder**: "Allowed Python dirs (path-separated)" (matches pattern)
3. **Width**: 80 (same as `SafeScriptDirs`)
4. **Layout**: Vertical in Security box (below `SafeScriptDirs`)
5. **Grid position**: Row 13, column 0 (or share row 13: column 0 and 1)

### Constraints

1. **No config migration needed**: Field already exists in config
2. **No validation**: Same as `SafeScriptDirs` (no directory existence checks)
3. **No breaking changes**: Addition only, no modifications to existing fields
4. **Minimal testing**: Follows established pattern, no new edge cases

## What We're NOT Doing

- **NOT** adding directory existence validation (out of scope, inconsistent with `SafeScriptDirs`)
- **NOT** adding auto-discovery of Python directories (feature creep)
- **NOT** changing the config field structure or semantics
- **NOT** adding user prompts or help text beyond placeholder
- **NOT** modifying the Python runner validation logic
- **NOT** creating migration scripts for existing configs (field already exists)
- **NOT** adding unit tests (follows existing pattern, no new logic)
- **NOT** changing the Security group layout beyond adding the field

## Implementation Approach

### High-Level Strategy

Add `AllowedPythonDirs` to TUI by following the exact pattern established by `SafeScriptDirs`. This is a straightforward addition that touches 5 files in well-defined locations. The changes are additive only with no modifications to existing code paths.

### Why This Approach

1. **Zero Risk**: Follows battle-tested pattern with identical semantics
2. **Maintainable**: Future developers see consistent code structure
3. **No Surprises**: Users already familiar with `SafeScriptDirs` UI
4. **Testable**: Can verify independently without affecting other features
5. **Reversible**: Purely additive changes are easy to roll back if needed

---

## Phase 1: Add Model Field and Initialization

### Overview

Add the `inAllowedPythonDirs` text input field to the TUI model and initialize it with values from the config.

### Changes Required

#### 1. Model Field Declaration

**File**: `internal/tui/model.go`

**Location**: After line 162 (after `inSafeScriptDirs` field)

**Change**: Add new field declaration

```go
// Security settings inputs
inSafeScriptDirs    textinput.Model
inAllowedPythonDirs textinput.Model
```

#### 2. Settings Input Names List

**File**: `internal/tui/model.go`

**Location**: After line 262 (after `"safescriptdirs"` in `settingsInputNames` array)

**Change**: Add to the list

```go
var settingsInputNames = []string{
    // ... existing entries ...
    // Security settings
    "safescriptdirs",
    "allowedpythondirs",
}
```

#### 3. Input Initialization

**File**: `internal/tui/model.go`

**Location**: After line 441 (after `inSafeScriptDirs` initialization in `initSettingsInputs()`)

**Change**: Initialize the field

```go
// Security settings inputs
m.inSafeScriptDirs = mkInput("Allowed script dirs (path-separated)", joinPaths(cfg.SafeScriptDirs), 80)
m.inAllowedPythonDirs = mkInput("Allowed Python dirs (path-separated)", joinPaths(cfg.AllowedPythonDirs), 80)
```

#### 4. Settings Inputs Map

**File**: `internal/tui/model.go`

**Location**: After line 476 (after `"safescriptdirs"` entry in `settingsInputs` map)

**Change**: Add to map

```go
m.settingsInputs = map[string]*textinput.Model{
    // ... existing entries ...
    // Security settings
    "safescriptdirs":    &m.inSafeScriptDirs,
    "allowedpythondirs": &m.inAllowedPythonDirs,
}
```

#### 5. Blur All Inputs

**File**: `internal/tui/inputs.go`

**Location**: After line 64 (after `m.inSafeScriptDirs.Blur()` in `blurAllInputs()`)

**Change**: Add blur call

```go
// Security inputs
m.inSafeScriptDirs.Blur()
m.inAllowedPythonDirs.Blur()
```

### Success Criteria

#### Automated Verification:
- [ ] Code compiles: `go build ./internal/tui/...`
- [ ] No type errors

#### Manual Verification:
- [ ] TUI starts without errors
- [ ] Settings tab displays without crashes
- [ ] Field appears in Security group (if rendering also complete)

**Note**: Complete this phase before proceeding to Phase 2. The field should be initialized but not yet visible in the UI or wired to config.

---

## Phase 2: Add to Settings Navigation

### Overview

Wire up the new field to the TUI navigation system (grid positioning and focus handling).

### Changes Required

#### 1. Settings Grid Position

**File**: `internal/tui/inputs.go`

**Location**: After line 37 (after `"safescriptdirs"` entry in `settingsGrid` map)

**Change**: Add grid position

**Option A (same row, adjacent column)**:
```go
// Security settings (row 13)
"safescriptdirs":    {13, 0},
"allowedpythondirs": {13, 1},
```

**Option B (new row)**:
```go
// Security settings (rows 13-14)
"safescriptdirs":    {13, 0},
"allowedpythondirs": {14, 0},
```

**Recommendation**: Use Option B (new row) for better layout in narrow terminals.

#### 2. Focus Handler

**File**: `internal/tui/inputs.go`

**Location**: After line 124 (after `safescriptdirs` case in `focusInput()`)

**Change**: Add focus case

```go
// Security settings
case "safescriptdirs":
    m.inSafeScriptDirs.Focus()
case "allowedpythondirs":
    m.inAllowedPythonDirs.Focus()
```

### Success Criteria

#### Automated Verification:
- [ ] Code compiles: `go build ./internal/tui/...`

#### Manual Verification:
- [ ] Arrow key navigation reaches the field
- [ ] Field can be focused
- [ ] Tab navigation cycles through the field
- [ ] Visual indicator shows when field is focused

**Note**: Complete this phase before proceeding to Phase 3. The field should be navigable but not yet wired to config save/load.

---

## Phase 3: Wire to Config System

### Overview

Connect the TUI input field to the config system for loading and saving values.

### Changes Required

#### 1. Input Accessors Map

**File**: `internal/tui/keys_settings.go`

**Location**: After line 118 (after `"safescriptdirs"` entry in `inputFieldAccessors` map)

**Change**: Add getter/setter

```go
"safescriptdirs": {
    get: func(m *model) *textinput.Model { return &m.inSafeScriptDirs },
    set: func(m *model, v string) { m.inSafeScriptDirs.SetValue(v) },
},
"allowedpythondirs": {
    get: func(m *model) *textinput.Model { return &m.inAllowedPythonDirs },
    set: func(m *model, v string) { m.inAllowedPythonDirs.SetValue(v) },
},
```

#### 2. Config Population

**File**: `internal/tui/run.go`

**Location**: After line 356 (after `dst.SafeScriptDirs` parsing in `populateConfigFromInputs()`)

**Change**: Add parsing

```go
// Security settings parsing
dst.SafeScriptDirs = parsePathList(m.inSafeScriptDirs.Value())
dst.AllowedPythonDirs = parsePathList(m.inAllowedPythonDirs.Value())
```

### Success Criteria

#### Automated Verification:
- [ ] Code compiles: `go build ./internal/tui/...`

#### Manual Verification:
- [ ] Existing `allowed_python_dirs` from config load on startup
- [ ] Changes to field are saved to `config.yaml`
- [ ] Reloading TUI shows saved values
- [ ] Empty field saves as empty array
- [ ] Path-separated values parse correctly

**Note**: Complete this phase before proceeding to Phase 4. The field should be fully functional for save/load.

---

## Phase 4: Update View Rendering

### Overview

Render the new field in the Security settings group of the Settings tab.

### Changes Required

#### 1. Security Group Rendering

**File**: `internal/tui/view_settings.go`

**Location**: Modify `renderSecurityGroup()` function (lines 112-120)

**Change**: Add field to layout

```go
// renderSecurityGroup renders the security settings group.
func renderSecurityGroup(b *strings.Builder, m model) {
    securityContent := lipgloss.JoinVertical(lipgloss.Left,
        m.inSafeScriptDirs.View(),
        m.inAllowedPythonDirs.View(),
    )
    securityBox := NewBorderedBox("Security", securityContent)
    securityBox.Focused = isInSettingsGroup(m.focusedInput, []string{"safescriptdirs", "allowedpythondirs"})
    b.WriteString(securityBox.Render() + "\n")
}
```

### Success Criteria

#### Automated Verification:
- [ ] Code compiles: `go build ./internal/tui/...`

#### Manual Verification:
- [ ] Both fields visible in Security group
- [ ] Layout looks correct (vertical stacking)
- [ ] Focus indicator works for both fields
- [ ] Box highlights when either field is focused

**Note**: This is the final phase. After completion, the feature should be fully functional.

---

## Testing Strategy

### Unit Tests

**No new unit tests required.** This change follows existing patterns with no new logic:
- Path utilities (`joinPaths`, `parsePathList`) already exist
- Config field already has getter method
- Input field logic is standard textinput.Model behavior

### Integration Tests

**Manual testing checklist:**

1. **Startup Load**:
   - [ ] Set `allowed_python_dirs` in `config.yaml`
   - [ ] Start TUI
   - [ ] Navigate to Settings tab
   - [ ] Verify values appear in field

2. **Edit and Save**:
   - [ ] Focus field
   - [ ] Enter paths (e.g., `/usr/bin:/usr/local/bin` on Unix)
   - [ ] Press Ctrl+S to save
   - [ ] Verify "dirty" indicator clears
   - [ ] Exit TUI
   - [ ] Check `config.yaml` contains saved values

3. **Empty Handling**:
   - [ ] Clear field completely
   - [ ] Save
   - [ ] Verify `config.yaml` shows `allowed_python_dirs: []`

4. **Navigation**:
   - [ ] Use arrow keys to navigate to field
   - [ ] Use Tab to cycle through
   - [ ] Verify focus indicator appears
   - [ ] Verify typing works

5. **Cross-Platform** (if applicable):
   - [ ] Test on macOS/Linux with colon `:` separator
   - [ ] Test on Windows with semicolon `;` separator

### Edge Cases

- [ ] Empty field (should save as empty array)
- [ ] Whitespace-only field (should trim and save as empty array)
- [ ] Paths with spaces (should preserve correctly)
- [ ] Very long path strings (should handle gracefully)
- [ ] Special characters in paths (should preserve correctly)

## Migration Notes

**No migration required.** The `AllowedPythonDirs` field:
- Already exists in config schema
- Already has default value (`[]`)
- Already persists correctly
- Already loads correctly

Users who have manually set `allowed_python_dirs` in their config will see those values automatically appear in the TUI field on first load after this change.

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Breaking existing configs | Low | High | **Mitigated**: Field already exists; no schema changes |
| Path parsing bugs | Low | Medium | **Mitigated**: Uses existing `parsePathList()` function |
| Navigation issues | Low | Low | **Mitigated**: Follows established grid pattern |
| Layout problems | Low | Low | **Mitigated**: Vertical layout same as other multi-field groups |
| Typos in field names | Medium | Medium | **Mitigated**: Compile-time checks on struct fields |

## Rollback Plan

If issues arise, rollback is straightforward:
1. Revert changes to 5 files (model.go, inputs.go, keys_settings.go, run.go, view_settings.go)
2. Config field remains functional (just not exposed in TUI)
3. Users can still edit config manually
4. No data loss (field persists correctly)

## References

- **Research**: `/Users/simo/Projects/autodev/.wreckit/items/011-expose-allowedpythondirs-config-in-tui-settings/research.md`
- **Config Definition**: `internal/config/config.go:126` - `AllowedPythonDirs` field
- **Config Getter**: `internal/config/config.go:706-714` - `GetAllowedPythonDirs()` method
- **Template Field**: `internal/tui/model.go:162` - `inSafeScriptDirs` (exact pattern to follow)
- **Template Init**: `internal/tui/model.go:441` - Initialization with `joinPaths()`
- **Template Grid**: `internal/tui/inputs.go:37` - Grid positioning
- **Template Accessors**: `internal/tui/keys_settings.go:115-118` - Getter/setter mapping
- **Template Parsing**: `internal/tui/run.go:356` - Config population with `parsePathList()`
- **Template View**: `internal/tui/view_settings.go:112-120` - Security group rendering
- **Path Utilities**: `internal/tui/helpers.go:78-103` - `joinPaths()` and `parsePathList()`
- **Runner Usage**: `internal/runner/runner.go:821` - Python validation using this field
