package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"
)

// setupTestRepo creates a test repository with proper configuration
func setupTestRepo(users []User) *InMemoryUserRepository {
	os.Setenv("JWT_SECRET", "test-jwt-secret-for-testing-only")
	config, _ := NewUserConfig()
	return NewInMemoryUserRepository(users, config)
}

func TestInMemoryUserRepository_ListUsers(t *testing.T) {
	repo := setupTestRepo(sampleUsers())

	result, err := repo.ListUsers(context.Background(), ListUsersParams{
		Page:     2,
		PageSize: 2,
	})
	if err != nil {
		t.Fatalf("ListUsers returned error: %v", err)
	}

	if len(result.Users) != 1 {
		t.Fatalf("expected 1 user on page 2, got %d", len(result.Users))
	}

	if result.Users[0].ID != "user-3" {
		t.Fatalf("expected user-3 on second page, got %s", result.Users[0].ID)
	}

	if result.Pagination.TotalItems != 3 {
		t.Fatalf("expected TotalItems=3 got %d", result.Pagination.TotalItems)
	}

	if result.Pagination.TotalPages != 2 {
		t.Fatalf("expected TotalPages=2 got %d", result.Pagination.TotalPages)
	}
}

func TestListUsersHandler_Pagination(t *testing.T) {
	repo := setupTestRepo(sampleUsers())
	router := newRouter(Dependencies{UserRepo: repo})

	req := httptest.NewRequest(http.MethodGet, "/api/users?page=1&page_size=2", nil)
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rr.Code)
	}

	var body struct {
		Data       []User     `json:"data"`
		Pagination Pagination `json:"pagination"`
	}
	if err := json.NewDecoder(rr.Body).Decode(&body); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if len(body.Data) != 2 {
		t.Fatalf("expected 2 users on page 1, got %d", len(body.Data))
	}

	if body.Data[0].ID != "user-1" {
		t.Fatalf("expected user-1 as first result, got %s", body.Data[0].ID)
	}

	if body.Pagination.TotalItems != 3 {
		t.Fatalf("expected TotalItems=3 got %d", body.Pagination.TotalItems)
	}

	if body.Pagination.Page != 1 || body.Pagination.PageSize != 2 {
		t.Fatalf("expected Page=1 PageSize=2, got Page=%d PageSize=%d", body.Pagination.Page, body.Pagination.PageSize)
	}
}

func TestListUsersHandler_InvalidQuery(t *testing.T) {
	repo := setupTestRepo(sampleUsers())
	router := newRouter(Dependencies{UserRepo: repo})

	req := httptest.NewRequest(http.MethodGet, "/api/users?page=abc", nil)
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rr.Code)
	}

	var body map[string]string
	if err := json.NewDecoder(rr.Body).Decode(&body); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if body["error"] == "" {
		t.Fatalf("expected error message in body")
	}
}

func TestInMemoryUserRepository_CreateUser(t *testing.T) {
	repo := setupTestRepo(nil)

	req := CreateUserRequest{
		Email:    "newuser@example.com",
		Username: "newuser",
		Password: "password123",
	}

	user, err := repo.CreateUser(context.Background(), req)
	if err != nil {
		t.Fatalf("CreateUser returned error: %v", err)
	}

	if user.Email != req.Email {
		t.Fatalf("expected email %s, got %s", req.Email, user.Email)
	}

	if user.Username != req.Username {
		t.Fatalf("expected username %s, got %s", req.Username, user.Username)
	}

	if user.ID == "" {
		t.Fatal("expected non-empty user ID")
	}

	if user.CreatedAt.IsZero() || user.UpdatedAt.IsZero() {
		t.Fatal("expected non-zero timestamps")
	}
}

func TestInMemoryUserRepository_CreateUser_DuplicateEmail(t *testing.T) {
	repo := setupTestRepo(sampleUsers())

	req := CreateUserRequest{
		Email:    "user1@example.com", // Duplicate email
		Username: "uniqueuser",
		Password: "password123",
	}

	_, err := repo.CreateUser(context.Background(), req)
	if err == nil {
		t.Fatal("expected error for duplicate email")
	}

	expected := "user with email user1@example.com already exists"
	if err.Error() != expected {
		t.Fatalf("expected error '%s', got '%s'", expected, err.Error())
	}
}

func TestInMemoryUserRepository_CreateUser_DuplicateUsername(t *testing.T) {
	repo := setupTestRepo(sampleUsers())

	req := CreateUserRequest{
		Email:    "unique@example.com",
		Username: "user1", // Duplicate username
		Password: "password123",
	}

	_, err := repo.CreateUser(context.Background(), req)
	if err == nil {
		t.Fatal("expected error for duplicate username")
	}

	expected := "user with username user1 already exists"
	if err.Error() != expected {
		t.Fatalf("expected error '%s', got '%s'", expected, err.Error())
	}
}

func TestInMemoryUserRepository_GetUserByID(t *testing.T) {
	repo := setupTestRepo(sampleUsers())

	user, err := repo.GetUserByID(context.Background(), "user-1")
	if err != nil {
		t.Fatalf("GetUserByID returned error: %v", err)
	}

	if user.ID != "user-1" {
		t.Fatalf("expected ID user-1, got %s", user.ID)
	}

	if user.Email != "user1@example.com" {
		t.Fatalf("expected email user1@example.com, got %s", user.Email)
	}
}

func TestInMemoryUserRepository_GetUserByID_NotFound(t *testing.T) {
	repo := setupTestRepo(sampleUsers())

	_, err := repo.GetUserByID(context.Background(), "nonexistent")
	if err == nil {
		t.Fatal("expected error for nonexistent user")
	}

	expected := "user with ID nonexistent not found"
	if err.Error() != expected {
		t.Fatalf("expected error '%s', got '%s'", expected, err.Error())
	}
}

func TestInMemoryUserRepository_UpdateUser(t *testing.T) {
	repo := setupTestRepo(sampleUsers())

	req := UpdateUserRequest{
		Email:    stringPtr("updated@example.com"),
		Username: stringPtr("updateduser"),
	}

	user, err := repo.UpdateUser(context.Background(), "user-1", req)
	if err != nil {
		t.Fatalf("UpdateUser returned error: %v", err)
	}

	if user.Email != *req.Email {
		t.Fatalf("expected email %s, got %s", *req.Email, user.Email)
	}

	if user.Username != *req.Username {
		t.Fatalf("expected username %s, got %s", *req.Username, user.Username)
	}

	if user.UpdatedAt.Before(user.CreatedAt) {
		t.Fatal("expected UpdatedAt to be after CreatedAt")
	}
}

func TestInMemoryUserRepository_UpdateUser_NotFound(t *testing.T) {
	repo := setupTestRepo(sampleUsers())

	req := UpdateUserRequest{
		Email: stringPtr("updated@example.com"),
	}

	_, err := repo.UpdateUser(context.Background(), "nonexistent", req)
	if err == nil {
		t.Fatal("expected error for nonexistent user")
	}

	expected := "user with ID nonexistent not found"
	if err.Error() != expected {
		t.Fatalf("expected error '%s', got '%s'", expected, err.Error())
	}
}

func TestInMemoryUserRepository_DeleteUser(t *testing.T) {
	repo := setupTestRepo(sampleUsers())

	err := repo.DeleteUser(context.Background(), "user-1")
	if err != nil {
		t.Fatalf("DeleteUser returned error: %v", err)
	}

	// Verify user is deleted
	_, err = repo.GetUserByID(context.Background(), "user-1")
	if err == nil {
		t.Fatal("expected user to be deleted")
	}

	// Verify other users still exist
	_, err = repo.GetUserByID(context.Background(), "user-2")
	if err != nil {
		t.Fatalf("expected user-2 to still exist: %v", err)
	}
}

func TestInMemoryUserRepository_DeleteUser_NotFound(t *testing.T) {
	repo := setupTestRepo(sampleUsers())

	// Idempotent behavior - should not return error
	err := repo.DeleteUser(context.Background(), "nonexistent")
	if err != nil {
		t.Fatalf("DeleteUser returned error for nonexistent user: %v", err)
	}
}

func TestValidateCreateUserRequest_Valid(t *testing.T) {
	req := CreateUserRequest{
		Email:    "test@example.com",
		Username: "testuser",
		Password: "password123",
	}

	errors := validateCreateUserRequest(req)
	if len(errors) != 0 {
		t.Fatalf("expected no validation errors, got %d", len(errors))
	}
}

func TestValidateCreateUserRequest_Invalid(t *testing.T) {
	tests := []struct {
		name     string
		req      CreateUserRequest
		expected int
	}{
		{
			name: "empty email",
			req: CreateUserRequest{
				Email:    "",
				Username: "testuser",
				Password: "password123",
			},
			expected: 1,
		},
		{
			name: "invalid email format",
			req: CreateUserRequest{
				Email:    "invalid-email",
				Username: "testuser",
				Password: "password123",
			},
			expected: 1,
		},
		{
			name: "short username",
			req: CreateUserRequest{
				Email:    "test@example.com",
				Username: "ab",
				Password: "password123",
			},
			expected: 1,
		},
		{
			name: "invalid username characters",
			req: CreateUserRequest{
				Email:    "test@example.com",
				Username: "test@user",
				Password: "password123",
			},
			expected: 1,
		},
		{
			name: "empty password",
			req: CreateUserRequest{
				Email:    "test@example.com",
				Username: "testuser",
				Password: "",
			},
			expected: 1,
		},
		{
			name: "short password",
			req: CreateUserRequest{
				Email:    "test@example.com",
				Username: "testuser",
				Password: "123",
			},
			expected: 1,
		},
		{
			name: "multiple errors",
			req: CreateUserRequest{
				Email:    "",
				Username: "ab",
				Password: "",
			},
			expected: 3,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			errors := validateCreateUserRequest(tt.req)
			if len(errors) != tt.expected {
				t.Fatalf("expected %d validation errors, got %d: %+v", tt.expected, len(errors), errors)
			}
		})
	}
}

func TestValidateUpdateUserRequest_Valid(t *testing.T) {
	req := UpdateUserRequest{
		Email:    stringPtr("test@example.com"),
		Username: stringPtr("testuser"),
	}

	errors := validateUpdateUserRequest(req)
	if len(errors) != 0 {
		t.Fatalf("expected no validation errors, got %d", len(errors))
	}
}

func TestValidateUpdateUserRequest_EmptyFields(t *testing.T) {
	req := UpdateUserRequest{
		Email:    nil,
		Username: nil,
	}

	errors := validateUpdateUserRequest(req)
	if len(errors) != 0 {
		t.Fatalf("expected no validation errors for nil fields, got %d", len(errors))
	}
}

func sampleUsers() []User {
	return []User{
		{
			ID:        "user-1",
			Email:     "user1@example.com",
			Username:  "user1",
			CreatedAt: time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC),
			UpdatedAt: time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC),
		},
		{
			ID:        "user-2",
			Email:     "user2@example.com",
			Username:  "user2",
			CreatedAt: time.Date(2024, 1, 2, 12, 0, 0, 0, time.UTC),
			UpdatedAt: time.Date(2024, 1, 2, 12, 0, 0, 0, time.UTC),
		},
		{
			ID:        "user-3",
			Email:     "user3@example.com",
			Username:  "user3",
			CreatedAt: time.Date(2024, 1, 3, 12, 0, 0, 0, time.UTC),
			UpdatedAt: time.Date(2024, 1, 3, 12, 0, 0, 0, time.UTC),
		},
	}
}

// Helper function to create string pointers
func stringPtr(s string) *string {
	return &s
}
