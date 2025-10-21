package tui

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

const pythonScriptName = "auto_prd_to_pr_v3.py"

type scriptCandidate struct {
	path   string
	reason string
}

func detectPythonScript(configured, repo string) (resolved string, reason string, changed bool, found bool) {
	configuredAbs := canonicalize(configured)
	if configuredAbs != "" {
		if isFile(configuredAbs) {
			return configuredAbs, "", !pathsEqual(configuredAbs, configured), true
		}
	}

	envOverride := os.Getenv("AUTO_PRD_SCRIPT")
	candidates := []scriptCandidate{}
	add := func(path, why string) {
		if path == "" {
			return
		}
		candidates = append(candidates, scriptCandidate{path: path, reason: why})
	}

	if envOverride != "" {
		add(envOverride, "AUTO_PRD_SCRIPT env")
	}

	if repo != "" {
		add(filepath.Join(repo, "tools", pythonScriptName), "repo settings")
	}

	if exe, err := os.Executable(); err == nil {
		exeDir := filepath.Dir(exe)
		add(filepath.Join(exeDir, pythonScriptName), "next to aprd binary")
		add(filepath.Join(exeDir, "tools", pythonScriptName), "tools next to aprd binary")
		add(filepath.Join(exeDir, "..", "tools", pythonScriptName), "tools alongside aprd binary")
		add(filepath.Join(exeDir, "..", "..", "tools", pythonScriptName), "tools two levels up from aprd binary")
	}

	if wd, err := os.Getwd(); err == nil {
		add(filepath.Join(wd, "tools", pythonScriptName), "working directory")
	}

	if configured != "" {
		add(configured, "configured path")
	}

	seen := map[string]struct{}{}
	for _, cand := range candidates {
		abs := canonicalize(cand.path)
		if abs == "" {
			continue
		}
		key := abs
		if runtime.GOOS == "windows" {
			key = strings.ToLower(key)
		}
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		if isFile(abs) {
			changed := !pathsEqual(abs, configuredAbs)
			return abs, cand.reason, changed, true
		}
	}

	return configuredAbs, "", configuredAbs != "" && !pathsEqual(configuredAbs, configured), false
}

func canonicalize(path string) string {
	path = strings.TrimSpace(path)
	if path == "" {
		return ""
	}
	if !filepath.IsAbs(path) {
		abs, err := filepath.Abs(path)
		if err == nil {
			path = abs
		}
	}
	return filepath.Clean(path)
}

func isFile(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return !info.IsDir()
}

func pathsEqual(a, b string) bool {
	if a == "" && b == "" {
		return true
	}
	if a == "" || b == "" {
		return false
	}
	if runtime.GOOS == "windows" {
		return strings.EqualFold(filepath.Clean(a), filepath.Clean(b))
	}
	return filepath.Clean(a) == filepath.Clean(b)
}

func abbreviatePath(path string) string {
	path = canonicalize(path)
	if path == "" {
		return path
	}
	home, err := os.UserHomeDir()
	if err == nil {
		home = canonicalize(home)
		sep := string(filepath.Separator)
		if runtime.GOOS == "windows" {
			pathLower := strings.ToLower(path)
			homeLower := strings.ToLower(home)
			if strings.HasPrefix(pathLower, homeLower+sep) {
				return "~" + path[len(home):]
			}
			if strings.EqualFold(path, home) {
				return "~"
			}
		} else {
			if strings.HasPrefix(path, home+sep) {
				return "~" + strings.TrimPrefix(path, home)
			}
			if path == home {
				return "~"
			}
		}
	}
	return path
}
