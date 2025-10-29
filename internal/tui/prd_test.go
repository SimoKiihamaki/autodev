package tui

import (
	"testing"
)

func TestNormalizeTags(t *testing.T) {
	tests := []struct {
		name     string
		input    []string
		expected []string
	}{
		{
			name:     "empty slice",
			input:    []string{},
			expected: []string{},
		},
		{
			name:     "single tag",
			input:    []string{"tag"},
			expected: []string{"tag"},
		},
		{
			name:     "whitespace trimming",
			input:    []string{"  tag  ", " tag ", "\ttag\t"},
			expected: []string{"tag"},
		},
		{
			name:     "case insensitive deduplication preserves first casing",
			input:    []string{"Tag", "tag", "TAG"},
			expected: []string{"Tag"},
		},
		{
			name:     "case insensitive deduplication preserves first occurrence",
			input:    []string{"tag", "Tag", "TAG"},
			expected: []string{"tag"},
		},
		{
			name:     "empty strings filtered out",
			input:    []string{"tag", "", "  ", "\t", "another"},
			expected: []string{"tag", "another"},
		},
		{
			name:     "mixed whitespace and duplicates",
			input:    []string{"  Tag  ", "tag", " Another ", "another", "  TAG  ", ""},
			expected: []string{"Tag", "Another"},
		},
		{
			name:     "different tags preserved",
			input:    []string{"frontend", "backend", "frontend", "  backend  ", "database"},
			expected: []string{"frontend", "backend", "database"},
		},
		{
			name:     "order preserved for unique tags",
			input:    []string{"zebra", "alpha", "beta", "alpha", "zebra"},
			expected: []string{"zebra", "alpha", "beta"},
		},
		{
			name:     "complex real world example",
			input:    []string{"  UI  ", "ui", "Backend", " backend ", "Database", "database", "  API  ", "api"},
			expected: []string{"UI", "Backend", "Database", "API"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := normalizeTags(tt.input)
			if len(result) != len(tt.expected) {
				t.Errorf("normalizeTags(%q) length mismatch: got %d, want %d", tt.input, len(result), len(tt.expected))
				return
			}
			for i, got := range result {
				if got != tt.expected[i] {
					t.Errorf("normalizeTags(%q) at index %d: got %q, want %q", tt.input, i, got, tt.expected[i])
				}
			}
		})
	}
}
