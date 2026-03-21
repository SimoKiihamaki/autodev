# AD004: PRD Path Validation Gaps

## Severity
Low-Medium

## Location
- `internal/tui/run.go` lines 95-99, 173-212
- `internal/tui/prd.go` lines 81-131

## Current Validation

### What's Working
1. **Preflight checks** (run.go:173-212):
   - Selected PRD must exist (`os.Stat` check)
   - Selected PRD cannot be a directory
   - Warning logged if not `.md` extension

2. **Empty selection check** (run.go:95-99):
   - Returns error if `selectedPRD == ""`

### What's Missing

#### 1. Symlink Handling
```go
// Current code uses os.Stat which follows symlinks
info, err := os.Stat(m.selectedPRD)
// Should use os.Lstat to detect symlinks and handle explicitly
```

#### 2. Absolute Path Validation
```go
// No validation that PRD is within repo root
// Could allow reading files outside the repo
```

#### 3. Path Traversal Protection
```go
// No protection against path traversal like:
// ../../../etc/passwd
// ..\\..\\..\\windows\\system32
```

#### 4. Unicode/Encoding Issues
```go
// No validation for unusual characters in paths
// Could cause issues with Python subprocess
```

#### 5. File Size Validation
```go
// No check for extremely large PRD files
// Could cause memory issues in glamour rendering
```

### Current PRD Scanning (prd.go)
```go
func (m model) scanPRDsCmd() tea.Cmd {
    return func() tea.Msg {
        // Walks up to 4 directory levels deep
        if strings.Count(rel, string(os.PathSeparator)) > 4 {
            return filepath.SkipDir
        }
        // Only finds .md files
        if strings.HasSuffix(strings.ToLower(d.Name()), ".md") {
            // No size limit check
            // no symlink check
        }
    }
}
```

### PRD Preview Loading (prd.go:159-187)
```go
const maxPreviewSize = 10000
if len(text) > maxPreviewSize {
    text = text[:maxPreviewSize] + "\n\n... (truncated)"
}
// Good: Has size limit for preview
// Missing: Size limit for actual run usage
```

## Proposed Improvements

### 1. Add PRD Path Validator Function
```go
func validatePRDPath(path, repoRoot string) error {
    // Check path is within repo root
    absPath, err := filepath.Abs(path)
    if err != nil {
        return err
    }
    absRoot, err := filepath.Abs(repoRoot)
    if err != nil {
        return err
    }
    if !strings.HasPrefix(absPath, absRoot) {
        return errors.New("PRD must be within repository root")
    }
    
    // Check for symlinks
    info, err := os.Lstat(path)
    if err != nil {
        return err
    }
    if info.Mode()&os.ModeSymlink != 0 {
        // Resolve and re-validate
        resolved, err := filepath.EvalSymlinks(path)
        if err != nil {
            return fmt.Errorf("cannot resolve symlink: %w", err)
        }
        return validatePRDPath(resolved, repoRoot)
    }
    
    // Check file size (e.g., max 1MB)
    if info.Size() > 1<<20 {
        return errors.New("PRD file too large (max 1MB)")
    }
    
    return nil
}
```

### 2. Add to Preflight Checks
```go
func (m *model) preflightChecks() error {
    // ... existing checks ...
    
    if err := validatePRDPath(m.selectedPRD, m.cfg.RepoPath); err != nil {
        return fmt.Errorf("invalid PRD path: %w", err)
    }
    
    // ... rest of checks ...
}
```

## Test Cases Needed
```go
func TestValidatePRDPathTraversal(t *testing.T)
func TestValidatePRDPathOutsideRepo(t *testing.T)
func TestValidatePRDPathSymlink(t *testing.T)
func TestValidatePRDPathTooLarge(t *testing.T)
func TestValidatePRDPathUnicode(t *testing.T)
```

## Priority
Low-Medium - Current checks are functional for normal use cases
