package main

import (
	"fmt"
)

func main() {
	// Test basic functionality
	testCases := []struct {
		current int
		delta   int
		n       int
		expect  int
		valid   bool
	}{
		{0, 1, 3, 1, true},  // forward
		{1, -1, 3, 0, true}, // backward
		{0, -1, 3, 2, true}, // wrap around negative
		{2, 1, 3, 0, true},  // wrap around positive
		{1, 0, 3, 1, true},  // no change
	}

	fmt.Println("Testing wrapIndex function:")
	for _, tc := range testCases {
		result, valid := wrapIndex(tc.current, tc.delta, tc.n)
		status := "PASS"
		if result != tc.expect || valid != tc.valid {
			status = "FAIL"
		}
		fmt.Printf("%s: wrapIndex(%d, %d, %d) = (%d, %t), expect (%d, %t)\n",
			status, tc.current, tc.delta, tc.n, result, valid, tc.expect, tc.valid)
	}
}

// Copy of the function for testing
func wrapIndex(current, delta, n int) (int, bool) {
	// n must be > 0 for modulo operation to be safe
	if n <= 0 {
		return 0, false
	}
	// Validate that current is within bounds [0, n)
	if current < 0 || current >= n {
		return 0, false
	}
	// Check for potential overflow - only for extreme delta values
	// This handles the case where delta is extremely large (positive or negative)
	// For typical UI navigation (delta = -1, 1, etc.), this won't trigger
	if delta > 0 && current > 0 && delta >= int(^uint(0)>>1)-current {
		return 0, false // Would overflow on addition
	}
	// Note: Overflow check for negative delta removed since modulo operation handles negative results correctly
	// and UI navigation deltas are typically small values that won't cause overflow

	idx := (current + delta) % n
	if idx < 0 {
		idx += n
	}
	return idx, true
}
