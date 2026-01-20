# Research: Expose AllowedPythonDirs config in TUI Settings

**Date**: 2025-01-19
**Item**: 011-expose-allowedpythondirs-config-in-tui-settings

## Research Question

Users can only configure allowed Python directories by manually editing `~/.config/aprd/config.yaml`.

**Motivation:** Provides consistent configuration experience through TUI instead of requiring manual config file editing.

**Technical constraints:**
- Add TUI input field in Settings tab for managing allowed Python directories

**Signals:** priority: high

## Summary

The `allowed_python_dirs` configuration field is already present in the config system but not exposed in the TUI Settings interface. The field is used by the Python runner to validate and allowlist Python interpreter directories for security reasons. Currently, there's a similar field `safe_script_dirs` that IS exposed in the TUI, which we can use as a template. The implementation requires adding a new text input field, wiring it through the input accessors, handling it in config population/saving, and displaying it in the Security settings group. The change is straightforward but touches multiple files in a well-established pattern.

## Current State Analysis

### Existing Implementation

**Config Structure** (`internal/config/config.go`):
- Line 126: `AllowedPythonDirs []string` field exists in Config struct
- Line 178: Default value is empty slice `[]string{}`
- Lines 420-422: Field is initialized from config or defaults during load
- Lines 499-501: Field is properly cloned in `Clone()` method
- Lines 644-646: Field is compared in `Equal()` method for dirty state detection
- Lines 706-714: `GetAllowedPythonDirs()` getter method exists
- Line 127: There's ALSO a `SafeScriptDirs []string` field which IS already exposed in TUI

**TUI Model** (`internal/tui/model.go`):
- Line 162: `inSafeScriptDirs textinput.Model` field exists (as the template to follow)
- Line 441: `inSafeScriptDirs` is initialized with `joinPaths(cfg.SafeScriptDirs)`
- Lines 238-263: `settingsInputNames` array includes "safescriptdirs"

**TUI Settings View** (`internal/tui/view_settings.go`):
- Lines 112-120: `renderSecurityGroup()` renders a "Security" box with `inSafeScriptDirs`
- This is WHERE we need to add the AllowedPythonDirs field

**Input Handling** (`internal/tui/keys_settings.go`):
- Lines 115-118: `inputFieldAccessors` map includes "safescriptdirs" getter/setter
- Lines 27-119: This is WHERE we need to add "allowedpythondirs" accessors

**Config Population** (`internal/tui/run.go`):
- Line 356: `dst.SafeScriptDirs = parsePathList(m.inSafeScriptDirs.Value())`
- This is WHERE we need to add AllowedPythonDirs parsing

**Security Validation** (`internal/runner/runner.go`):
- Lines 796-873: Python runner uses `cfg.GetAllowedPythonDirs()` to validate Python interpreters
- Lines 821: User-configured dirs are fetched: `userAllowedDirs := cfg.GetAllowedPythonDirs()`
- Lines 854, 872-873: Error messages reference `allowed_python_dirs` config field
- The field IS actively used for security validation

**Path Utilities** (`internal/tui/helpers.go`):
- Lines 78-85: `joinPaths()` converts string slice to path-separated string
- Lines 87-103: `parsePathList()` splits path-separated string into slice
- Both are OS-aware (use `os.PathListSeparator`)

### Key Files

- `internal/config/config.go:126` - Config struct with AllowedPythonDirs field
- `internal/config/config.go:706-714` - GetAllowedPythonDirs() getter method
- `internal/runner/runner.go:821` - Usage in Python validation
- `internal/tui/model.go:162` - Template: inSafeScriptDirs field
- `internal/tui/model.go:441` - Template: SafeScriptDirs initialization
- `internal/tui/view_settings.go:112-120` - Template: Security settings group rendering
- `internal/tui/keys_settings.go:115-118` - Template: SafeScriptDirs input accessors
- `internal/tui/run.go:356` - Template: SafeScriptDirs config population
- `internal/tui/inputs.go:37` - Template: safescriptdirs in settings grid
- `internal/tui/inputs.go:123-124` - Template: safescriptdirs focus handling
- `internal/tui/helpers.go:78-103` - Path utility functions (joinPaths, parsePathList)

## Technical Considerations

### Dependencies
- **Internal**: `internal/config` package (Config struct), `internal/tui` (model, views, input handling)
- **External**: `github.com/charmbracelet/bubbles/textinput` for text input component
- **Standard Library**: `os` for path separator, `strings` for path manipulation

### Patterns to Follow

**1. Field Naming Convention:**
- Config YAML: `allowed_python_dirs` (snake_case, already defined)
- Go struct: `AllowedPythonDirs` (PascalCase, already defined)
- TUI input: `inAllowedPythonDirs` (camelCase with "in" prefix)
- Settings key: `"allowedpythondirs"` (lowercase, single word)

**2. Input Initialization Pattern** (from `inSafeScriptDirs`):
```go
m.inSafeScriptDirs = mkInput("Allowed script dirs (path-separated)", joinPaths(cfg.SafeScriptDirs), 80)
```

**3. Settings Grid Pattern:**
```go
"safescriptdirs": {13, 0},  // Row 13, column 0
```
Should add allowedpythondirs at row 13, column 1 (or create new row)

**4. Input Accessor Pattern:**
```go
"safescriptdirs": {
    get: func(m *model) *textinput.Model { return &m.inSafeScriptDirs },
    set: func(m *model, v string) { m.inSafeScriptDirs.SetValue(v) },
},
```

**5. Focus Handling Pattern:**
```go
case "safescriptdirs":
    m.inSafeScriptDirs.Focus()
```

**6. Config Population Pattern:**
```go
dst.SafeScriptDirs = parsePathList(m.inSafeScriptDirs.Value())
```

**7. View Rendering Pattern:**
```go
securityContent := lipgloss.JoinVertical(lipgloss.Left,
    m.inSafeScriptDirs.View(),
)
```

**8. Settings Group Pattern:**
Currently Security group has only 1 field. Should add second field either:
- On same line (horizontal layout)
- On new line (vertical layout)

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Breaking existing user configs** | High | AllowedPythonDirs field already exists in config; adding TUI exposure won't break anything as field already persists |
| **Path parsing issues on different OS** | Medium | Use existing `parsePathList()` and `joinPaths()` which handle `os.PathListSeparator` correctly (colon on Unix, semicolon on Windows) |
| **Input validation missing** | Low | No validation currently on SafeScriptDirs either; paths are validated at runtime by Python script. Keep consistent behavior. |
| **Layout issues in Settings view** | Low | Security box currently has 1 field; adding a second field may require layout adjustment. Test with various terminal widths. |
| **Settings grid navigation issues** | Low | Need to add entry to `settingsGrid` map at correct position. Follow existing pattern. |

## Recommended Approach

### High-Level Strategy

1. **Add model field** (`internal/tui/model.go`):
   - Add `inAllowedPythonDirs textinput.Model` field (after line 162)
   - Initialize in `initSettingsInputs()` (after line 441)
   - Add to `settingsInputs` map (after line 476)

2. **Add to settings navigation** (`internal/tui/inputs.go`):
   - Add entry to `settingsGrid` map (row 13 or new row 14)
   - Add focus case in `focusInput()` (after line 124)

3. **Add input accessors** (`internal/tui/keys_settings.go`):
   - Add getter/setter to `inputFieldAccessors` map (after line 118)

4. **Wire to config** (`internal/tui/run.go`):
   - Add parsing in `populateConfigFromInputs()` (after line 356)

5. **Update view** (`internal/tui/view_settings.go`):
   - Modify `renderSecurityGroup()` to include new field (after line 115)

6. **Update settings input names list** (`internal/tui/model.go`):
   - Add "allowedpythondirs" to `settingsInputNames` array (line 238-263)

### Detailed Changes

**File: internal/tui/model.go**
- Add field: `inAllowedPythonDirs textinput.Model` (line ~163)
- Add to `settingsInputNames`: `"allowedpythondirs"` (line ~263)
- Initialize: `m.inAllowedPythonDirs = mkInput("Allowed Python dirs (path-separated)", joinPaths(cfg.AllowedPythonDirs), 80)` (line ~442)
- Add to map: `"allowedpythondirs": &m.inAllowedPythonDirs` (line ~477)

**File: internal/tui/inputs.go**
- Add grid position: `"allowedpythondirs": {13, 1}` (or `{14, 0}` for new row)
- Add focus case:
  ```go
  case "allowedpythondirs":
      m.inAllowedPythonDirs.Focus()
  ```

**File: internal/tui/keys_settings.go**
- Add accessor:
  ```go
  "allowedpythondirs": {
      get: func(m *model) *textinput.Model { return &m.inAllowedPythonDirs },
      set: func(m *model, v string) { m.inAllowedPythonDirs.SetValue(v) },
  },
  ```

**File: internal/tui/run.go**
- Add parsing:
  ```go
  dst.AllowedPythonDirs = parsePathList(m.inAllowedPythonDirs.Value())
  ```

**File: internal/tui/view_settings.go**
- Modify `renderSecurityGroup()`:
  ```go
  securityContent := lipgloss.JoinVertical(lipgloss.Left,
      m.inSafeScriptDirs.View(),
      m.inAllowedPythonDirs.View(),
  )
  ```
- Update focused input list to include "allowedpythondirs"

### Testing Strategy

1. **Unit Tests**: No new unit tests needed (follows existing pattern)
2. **Integration Tests**:
   - Start TUI, navigate to Settings tab
   - Navigate to Security section
   - Verify both SafeScriptDirs and AllowedPythonDirs fields are visible
   - Test field focusing and editing
   - Test save/load cycle
   - Verify config.yaml is updated correctly
3. **Cross-Platform Tests**: Verify path separator works on:
   - Linux/macOS (colon `:` separator)
   - Windows (semicolon `;` separator)

## Open Questions

**Q1: Should the two fields be on the same row or different rows?**
- **Answer**: Recommend same row (columns 0 and 1) since both are path lists and Security section is at the bottom. Can always adjust if layout looks cramped.

**Q2: What placeholder text should be used?**
- **Answer**: Follow pattern: "Allowed Python dirs (path-separated)" matches "Allowed script dirs (path-separated)"

**Q3: Should we add validation for directory existence?**
- **Answer**: No. SafeScriptDirs doesn't validate, and Python script validates at runtime. Keep consistent behavior.

**Q4: What's the max width for the input field?**
- **Answer**: Use 80 (same as SafeScriptDirs)

**Q5: Should we migrate existing allowed_python_dirs from config to TUI?**
- **Answer**: Yes, automatically. Since field already exists in config, initialization via `joinPaths(cfg.AllowedPythonDirs)` will load existing values on TUI start.
