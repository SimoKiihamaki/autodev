package utils

import "testing"

// TestBoolPtr verifies BoolPtr returns correct pointer.
func TestBoolPtr(t *testing.T) {
	tests := []struct {
		name  string
		input bool
	}{
		{"true value", true},
		{"false value", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := BoolPtr(tt.input)

			if result == nil {
				t.Fatal("BoolPtr returned nil")
			}

			if *result != tt.input {
				t.Errorf("BoolPtr(%v) = %v, want %v", tt.input, *result, tt.input)
			}
		})
	}
}

// TestIntPtr verifies IntPtr returns correct pointer.
func TestIntPtr(t *testing.T) {
	tests := []struct {
		name  string
		input int
	}{
		{"zero", 0},
		{"positive", 42},
		{"negative", -1},
		{"large", 2147483647},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			result := IntPtr(tt.input)

			if result == nil {
				t.Fatal("IntPtr returned nil")
			}

			if *result != tt.input {
				t.Errorf("IntPtr(%v) = %v, want %v", tt.input, *result, tt.input)
			}
		})
	}
}

// TestBoolPtr_PointerIndependence verifies that returned pointers
// are independent values (modifying one doesn't affect others).
func TestBoolPtr_PointerIndependence(t *testing.T) {
	// Start both pointers with the same value
	ptr1 := BoolPtr(false)
	ptr2 := BoolPtr(false)

	// Modify first pointer to opposite value
	*ptr1 = true

	// Second pointer should be unaffected (still false)
	if *ptr2 != false {
		t.Errorf("BoolPtr pointers are not independent: *ptr2=%v, want false", *ptr2)
	}
}

// TestIntPtr_PointerIndependence verifies that returned pointers
// are independent values (modifying one doesn't affect others).
func TestIntPtr_PointerIndependence(t *testing.T) {
	ptr1 := IntPtr(100)
	ptr2 := IntPtr(200)

	// Modify first pointer
	*ptr1 = 50

	// Second pointer should be unaffected
	if *ptr2 != 200 {
		t.Error("pointer values are not independent")
	}
}
