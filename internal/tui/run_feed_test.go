package tui

import "testing"

func TestHandleIterationHeader(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name             string
		line             string
		expectCurrent    int
		expectTotal      int
		expectLabel      string
		expectPhase      string
		expectRunCurrent string
	}{
		{
			name:             "with total and label",
			line:             "===== Iteration 3/10: Build =====",
			expectCurrent:    3,
			expectTotal:      10,
			expectLabel:      "Build",
			expectPhase:      "Iteration 3/10",
			expectRunCurrent: "Build",
		},
		{
			name:             "unknown total",
			line:             "===== Iteration 2/999999999999999999999 =====",
			expectCurrent:    2,
			expectTotal:      iterTotalUnknown,
			expectLabel:      "",
			expectPhase:      "Iteration 2/?",
			expectRunCurrent: "Iteration 2/?",
		},
		{
			name:             "unspecified total",
			line:             "===== Iteration 5 =====",
			expectCurrent:    5,
			expectTotal:      iterTotalUnspecified,
			expectLabel:      "",
			expectPhase:      "Iteration 5",
			expectRunCurrent: "Iteration 5",
		},
		{
			name:             "index overflow",
			line:             "===== Iteration 999999999999999999999 =====",
			expectCurrent:    iterIndexUnknown,
			expectTotal:      iterTotalUnspecified,
			expectLabel:      "",
			expectPhase:      "Iteration",
			expectRunCurrent: "Iteration",
		},
	}

	for _, tc := range tests {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			m := model{}
			matched := m.handleIterationHeader(tc.line)
			if !matched {
				t.Fatalf("expected header to match for line %q", tc.line)
			}
			if m.runIterCurrent != tc.expectCurrent {
				t.Fatalf("runIterCurrent=%d, want %d", m.runIterCurrent, tc.expectCurrent)
			}
			if m.runIterTotal != tc.expectTotal {
				t.Fatalf("runIterTotal=%d, want %d", m.runIterTotal, tc.expectTotal)
			}
			if m.runIterLabel != tc.expectLabel {
				t.Fatalf("runIterLabel=%q, want %q", m.runIterLabel, tc.expectLabel)
			}
			if m.runPhase != tc.expectPhase {
				t.Fatalf("runPhase=%q, want %q", m.runPhase, tc.expectPhase)
			}
			if m.runCurrent != tc.expectRunCurrent {
				t.Fatalf("runCurrent=%q, want %q", m.runCurrent, tc.expectRunCurrent)
			}
		})
	}
}

func TestConsumeRunSummaryStripsLogPrefix(t *testing.T) {
	t.Parallel()

	m := model{}
	line := "2025-10-27 13:14:40,704 INFO auto_prd.print: === Iteration 2/5: Build ==="
	m.consumeRunSummary(line)

	if m.runIterCurrent != 2 {
		t.Fatalf("runIterCurrent=%d, want 2", m.runIterCurrent)
	}
	if m.runIterTotal != 5 {
		t.Fatalf("runIterTotal=%d, want 5", m.runIterTotal)
	}
	if m.runIterLabel != "Build" {
		t.Fatalf("runIterLabel=%q, want Build", m.runIterLabel)
	}
	if m.runPhase != "Iteration 2/5" {
		t.Fatalf("runPhase=%q, want Iteration 2/5", m.runPhase)
	}
	if m.runCurrent != "Build" {
		t.Fatalf("runCurrent=%q, want Build", m.runCurrent)
	}

	m2 := model{}
	arrow := "2025-10-27 13:14:47,615 INFO auto_prd.print: → Launching implementation pass"
	m2.consumeRunSummary(arrow)
	if m2.runCurrent != "Launching implementation pass" {
		t.Fatalf("runCurrent=%q, want Launching implementation pass", m2.runCurrent)
	}
	if m2.runPhase != "Running" {
		t.Fatalf("runPhase=%q, want Running", m2.runPhase)
	}
}
