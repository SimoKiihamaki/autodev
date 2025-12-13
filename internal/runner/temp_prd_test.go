package runner

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/SimoKiihamaki/autodev/internal/config"
)

// TestMakeTempPRDCreatesInConfigDir verifies that temp PRD files are created
// in ~/.config/aprd/tmp/ instead of the system temp directory.
// This is important for passing Python's security validation which requires
// PRD files to be within the repository, working directory, or home directory.
func TestMakeTempPRDCreatesInConfigDir(t *testing.T) {
	// Create a temporary directory for the test PRD
	testDir := t.TempDir()
	prdPath := filepath.Join(testDir, "test.md")
	if err := os.WriteFile(prdPath, []byte("# Test PRD\n\nSome content"), 0o644); err != nil {
		t.Fatalf("Failed to create test PRD: %v", err)
	}

	// Call makeTempPRD with a prompt
	tempPath, cleanup, err := makeTempPRD(prdPath, "Test initial prompt")
	if err != nil {
		t.Fatalf("makeTempPRD failed: %v", err)
	}
	defer cleanup()

	// Verify the temp file is created in the config directory
	configDir, err := config.EnsureDir()
	if err != nil {
		t.Fatalf("Failed to get config directory: %v", err)
	}

	expectedPrefix := filepath.Join(configDir, "tmp")
	if !strings.HasPrefix(tempPath, expectedPrefix) {
		t.Errorf("Temp PRD should be in %s, got %s", expectedPrefix, tempPath)
	}

	// Verify the file exists
	if _, err := os.Stat(tempPath); os.IsNotExist(err) {
		t.Error("Temp PRD file should exist")
	}
}

// TestMakeTempPRDDirectoryPermissions verifies that the tmp directory
// is created with 0o700 permissions (owner rwx only).
func TestMakeTempPRDDirectoryPermissions(t *testing.T) {
	// Create a temporary directory for the test PRD
	testDir := t.TempDir()
	prdPath := filepath.Join(testDir, "test.md")
	if err := os.WriteFile(prdPath, []byte("# Test PRD"), 0o644); err != nil {
		t.Fatalf("Failed to create test PRD: %v", err)
	}

	// Call makeTempPRD to trigger directory creation
	tempPath, cleanup, err := makeTempPRD(prdPath, "Test prompt")
	if err != nil {
		t.Fatalf("makeTempPRD failed: %v", err)
	}
	defer cleanup()

	// Get the tmp directory
	tmpDir := filepath.Dir(tempPath)

	// Check directory permissions
	info, err := os.Stat(tmpDir)
	if err != nil {
		t.Fatalf("Failed to stat tmp directory: %v", err)
	}

	// On Unix systems, check the permission bits
	mode := info.Mode().Perm()
	if mode != 0o700 {
		t.Errorf("Tmp directory should have 0700 permissions, got %o", mode)
	}
}

// TestMakeTempPRDFilePermissions verifies that temp PRD files
// are created with 0o600 permissions (owner read/write only).
func TestMakeTempPRDFilePermissions(t *testing.T) {
	// Create a temporary directory for the test PRD
	testDir := t.TempDir()
	prdPath := filepath.Join(testDir, "test.md")
	if err := os.WriteFile(prdPath, []byte("# Test PRD"), 0o644); err != nil {
		t.Fatalf("Failed to create test PRD: %v", err)
	}

	// Call makeTempPRD
	tempPath, cleanup, err := makeTempPRD(prdPath, "Test prompt")
	if err != nil {
		t.Fatalf("makeTempPRD failed: %v", err)
	}
	defer cleanup()

	// Check file permissions
	info, err := os.Stat(tempPath)
	if err != nil {
		t.Fatalf("Failed to stat temp PRD file: %v", err)
	}

	// On Unix systems, check the permission bits
	mode := info.Mode().Perm()
	if mode != 0o600 {
		t.Errorf("Temp PRD file should have 0600 permissions, got %o", mode)
	}
}

// TestMakeTempPRDCleanupRemovesFile verifies that the cleanup function
// correctly removes the temporary PRD file.
func TestMakeTempPRDCleanupRemovesFile(t *testing.T) {
	// Create a temporary directory for the test PRD
	testDir := t.TempDir()
	prdPath := filepath.Join(testDir, "test.md")
	if err := os.WriteFile(prdPath, []byte("# Test PRD"), 0o644); err != nil {
		t.Fatalf("Failed to create test PRD: %v", err)
	}

	// Call makeTempPRD
	tempPath, cleanup, err := makeTempPRD(prdPath, "Test prompt")
	if err != nil {
		t.Fatalf("makeTempPRD failed: %v", err)
	}

	// Verify file exists before cleanup
	if _, err := os.Stat(tempPath); os.IsNotExist(err) {
		t.Fatal("Temp PRD file should exist before cleanup")
	}

	// Run cleanup
	cleanup()

	// Verify file is removed
	if _, err := os.Stat(tempPath); !os.IsNotExist(err) {
		t.Error("Temp PRD file should be removed after cleanup")
	}
}

// TestMakeTempPRDNoPromptReturnsOriginal verifies that when no prompt
// is provided, the original PRD path is returned without creating a temp file.
func TestMakeTempPRDNoPromptReturnsOriginal(t *testing.T) {
	t.Parallel()

	// Create a temporary directory for the test PRD
	testDir := t.TempDir()
	prdPath := filepath.Join(testDir, "test.md")
	if err := os.WriteFile(prdPath, []byte("# Test PRD"), 0o644); err != nil {
		t.Fatalf("Failed to create test PRD: %v", err)
	}

	// Call makeTempPRD with empty prompt
	returnedPath, cleanup, err := makeTempPRD(prdPath, "")
	if err != nil {
		t.Fatalf("makeTempPRD failed: %v", err)
	}
	defer cleanup()

	// Should return original path
	if returnedPath != prdPath {
		t.Errorf("Expected original path %s, got %s", prdPath, returnedPath)
	}
}

// TestMakeTempPRDWhitespaceOnlyPromptReturnsOriginal verifies that
// whitespace-only prompts are treated as empty.
func TestMakeTempPRDWhitespaceOnlyPromptReturnsOriginal(t *testing.T) {
	t.Parallel()

	// Create a temporary directory for the test PRD
	testDir := t.TempDir()
	prdPath := filepath.Join(testDir, "test.md")
	if err := os.WriteFile(prdPath, []byte("# Test PRD"), 0o644); err != nil {
		t.Fatalf("Failed to create test PRD: %v", err)
	}

	// Call makeTempPRD with whitespace-only prompt
	returnedPath, cleanup, err := makeTempPRD(prdPath, "   \t\n  ")
	if err != nil {
		t.Fatalf("makeTempPRD failed: %v", err)
	}
	defer cleanup()

	// Should return original path
	if returnedPath != prdPath {
		t.Errorf("Expected original path %s, got %s", prdPath, returnedPath)
	}
}

// TestMakeTempPRDContentIncludesPromptHeader verifies that the temp PRD
// includes the OPERATOR_INSTRUCTION header with the prompt.
func TestMakeTempPRDContentIncludesPromptHeader(t *testing.T) {
	// Create a temporary directory for the test PRD
	testDir := t.TempDir()
	prdPath := filepath.Join(testDir, "test.md")
	originalContent := "# Test PRD\n\nOriginal content"
	if err := os.WriteFile(prdPath, []byte(originalContent), 0o644); err != nil {
		t.Fatalf("Failed to create test PRD: %v", err)
	}

	// Call makeTempPRD with a prompt
	prompt := "Do this special thing"
	tempPath, cleanup, err := makeTempPRD(prdPath, prompt)
	if err != nil {
		t.Fatalf("makeTempPRD failed: %v", err)
	}
	defer cleanup()

	// Read the temp file content
	content, err := os.ReadFile(tempPath)
	if err != nil {
		t.Fatalf("Failed to read temp PRD: %v", err)
	}

	contentStr := string(content)

	// Verify OPERATOR_INSTRUCTION header is present
	if !strings.Contains(contentStr, "<!-- OPERATOR_INSTRUCTION") {
		t.Error("Temp PRD should contain OPERATOR_INSTRUCTION header")
	}

	// Verify prompt is included
	if !strings.Contains(contentStr, prompt) {
		t.Error("Temp PRD should contain the prompt text")
	}

	// Verify original content is preserved
	if !strings.Contains(contentStr, originalContent) {
		t.Error("Temp PRD should preserve original PRD content")
	}
}

// TestMakeTempPRDErrorOnMissingFile verifies that makeTempPRD returns
// an error when the source PRD file doesn't exist.
func TestMakeTempPRDErrorOnMissingFile(t *testing.T) {
	t.Parallel()

	nonexistentPath := "/nonexistent/path/to/prd.md"

	_, _, err := makeTempPRD(nonexistentPath, "Some prompt")
	if err == nil {
		t.Error("Expected error for missing PRD file")
	}
}
