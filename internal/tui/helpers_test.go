package tui

import (
	"math"
	"testing"

	"github.com/SimoKiihamaki/autodev/internal/utils"
)

func TestWrapIndex(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name    string
		current int
		delta   int
		n       int
		expect  int
		valid   bool
	}{
		// Basic functionality
		{
			name:    "forward navigation",
			current: 0,
			delta:   1,
			n:       3,
			expect:  1,
			valid:   true,
		},
		{
			name:    "backward navigation",
			current: 1,
			delta:   -1,
			n:       3,
			expect:  0,
			valid:   true,
		},
		{
			name:    "wrap around negative",
			current: 0,
			delta:   -1,
			n:       3,
			expect:  2,
			valid:   true,
		},
		{
			name:    "wrap around positive",
			current: 2,
			delta:   1,
			n:       3,
			expect:  0,
			valid:   true,
		},
		{
			name:    "no change",
			current: 1,
			delta:   0,
			n:       3,
			expect:  1,
			valid:   true,
		},

		// Edge cases
		{
			name:    "invalid n (zero)",
			current: 0,
			delta:   1,
			n:       0,
			expect:  0,
			valid:   false,
		},
		{
			name:    "invalid n (negative)",
			current: 0,
			delta:   1,
			n:       -1,
			expect:  0,
			valid:   false,
		},
		{
			name:    "current out of bounds (negative)",
			current: -1,
			delta:   1,
			n:       3,
			expect:  0,
			valid:   false,
		},
		{
			name:    "current out of bounds (too large)",
			current: 3,
			delta:   1,
			n:       3,
			expect:  0,
			valid:   false,
		},

		// Large delta values
		{
			name:    "large positive delta",
			current: 1,
			delta:   100,
			n:       3,
			expect:  2, // (1 + 100) % 3 = 101 % 3 = 2
			valid:   true,
		},
		{
			name:    "large negative delta",
			current: 1,
			delta:   -100,
			n:       3,
			expect:  0, // (1 - 100) % 3 = -99 % 3 = 0
			valid:   true,
		},

		// Overflow protection
		{
			name:    "overflow protection triggers",
			current: 1,
			delta:   math.MaxInt,
			n:       3,
			expect:  0,
			valid:   false,
		},
		{
			name:    "overflow protection with zero current",
			current: 0,
			delta:   math.MaxInt,
			n:       3,
			expect:  1, // (0 + math.MaxInt) % 3 = 1
			valid:   true,
		},
	}

	for _, tc := range testCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			result, valid := wrapIndex(tc.current, tc.delta, tc.n)

			if result != tc.expect {
				t.Errorf("expected result %d, got %d", tc.expect, result)
			}
			if valid != tc.valid {
				t.Errorf("expected valid %t, got %t", tc.valid, valid)
			}
		})
	}
}

func TestBoolPtr(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name  string
		input bool
		want  bool
	}{
		{
			name:  "true value",
			input: true,
			want:  true,
		},
		{
			name:  "false value",
			input: false,
			want:  false,
		},
	}

	for _, tc := range testCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			result := utils.BoolPtr(tc.input)

			if result == nil {
				t.Fatal("expected non-nil result")
			}
			if *result != tc.want {
				t.Errorf("expected %t, got %t", tc.want, *result)
			}
		})
	}
}
