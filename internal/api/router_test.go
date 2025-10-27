package api

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
)

// setupTestRepo creates a test repository with proper configuration
func setupTestRepoRouter(users []User) *InMemoryUserRepository {
	os.Setenv("JWT_SECRET", "test-jwt-secret-for-testing-only")
	config, _ := NewUserConfig()
	return NewInMemoryUserRepository(users, config)
}

// getTestJWTToken creates a test user and returns a JWT token
func getTestJWTToken(router http.Handler) string {
	// Create test user first
	createReq := CreateUserRequest{
		Email:    "test@example.com",
		Username: "testuser",
		Password: "password123",
	}

	bodyBytes, _ := json.Marshal(createReq)
	req := httptest.NewRequest(http.MethodPost, "/api/users", bytes.NewReader(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()
	router.ServeHTTP(rr, req)

	// Now login to get token
	loginReq := LoginRequest{
		Email:    "test@example.com",
		Password: "password123",
	}

	loginBodyBytes, _ := json.Marshal(loginReq)
	loginReqHTTP := httptest.NewRequest(http.MethodPost, "/api/auth/login", bytes.NewReader(loginBodyBytes))
	loginReqHTTP.Header.Set("Content-Type", "application/json")
	loginRR := httptest.NewRecorder()
	router.ServeHTTP(loginRR, loginReqHTTP)

	var response LoginResponse
	_ = json.NewDecoder(loginRR.Body).Decode(&response)
	return response.Token
}

func TestHealthEndpoint(t *testing.T) {
	router := newRouter(Dependencies{
		UserRepo: setupTestRepoRouter(nil),
	})

	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rr.Code)
	}
}

func TestCreateUserHandler_Valid(t *testing.T) {
	repo := setupTestRepoRouter(nil)
	router := newRouter(Dependencies{UserRepo: repo})

	body := CreateUserRequest{
		Email:    "test@example.com",
		Username: "testuser",
		Password: "password123",
	}

	bodyBytes, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/users", bytes.NewReader(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusCreated {
		t.Fatalf("expected status 201, got %d", rr.Code)
	}

	var user User
	if err := json.NewDecoder(rr.Body).Decode(&user); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if user.Email != body.Email {
		t.Fatalf("expected email %s, got %s", body.Email, user.Email)
	}

	if user.Username != body.Username {
		t.Fatalf("expected username %s, got %s", body.Username, user.Username)
	}
}

func TestCreateUserHandler_ValidationError(t *testing.T) {
	repo := setupTestRepoRouter(nil)
	router := newRouter(Dependencies{UserRepo: repo})

	body := CreateUserRequest{
		Email:    "invalid-email",
		Username: "ab",  // Too short
		Password: "123", // Too short
	}

	bodyBytes, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/users", bytes.NewReader(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rr.Code)
	}

	var response struct {
		Error  string            `json:"error"`
		Fields []ValidationError `json:"fields"`
	}
	if err := json.NewDecoder(rr.Body).Decode(&response); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if response.Error != "validation failed" {
		t.Fatalf("expected error message 'validation failed', got '%s'", response.Error)
	}

	if len(response.Fields) != 3 {
		t.Fatalf("expected 3 validation errors, got %d", len(response.Fields))
	}
}

func TestCreateUserHandler_DuplicateEmail(t *testing.T) {
	repo := setupTestRepoRouter(sampleUsers())
	router := newRouter(Dependencies{UserRepo: repo})

	body := CreateUserRequest{
		Email:    "user1@example.com", // Duplicate
		Username: "uniqueuser",
		Password: "password123",
	}

	bodyBytes, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPost, "/api/users", bytes.NewReader(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusConflict {
		t.Fatalf("expected status 409, got %d", rr.Code)
	}
}

func TestGetUserHandler_Found(t *testing.T) {
	repo := setupTestRepoRouter(sampleUsers())
	router := newRouter(Dependencies{UserRepo: repo})

	req := httptest.NewRequest(http.MethodGet, "/api/users/user-1", nil)
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rr.Code)
	}

	var user User
	if err := json.NewDecoder(rr.Body).Decode(&user); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if user.ID != "user-1" {
		t.Fatalf("expected ID user-1, got %s", user.ID)
	}
}

func TestGetUserHandler_NotFound(t *testing.T) {
	repo := setupTestRepoRouter(sampleUsers())
	router := newRouter(Dependencies{UserRepo: repo})

	req := httptest.NewRequest(http.MethodGet, "/api/users/nonexistent", nil)
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", rr.Code)
	}
}

func TestUpdateUserHandler_Valid(t *testing.T) {
	repo := setupTestRepoRouter(sampleUsers())
	router := newRouter(Dependencies{UserRepo: repo})

	// Get JWT token for authentication
	token := getTestJWTToken(router)

	body := UpdateUserRequest{
		Email: stringPtr("updated@example.com"),
	}

	bodyBytes, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPut, "/api/users/user-1", bytes.NewReader(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rr.Code)
	}

	var user User
	if err := json.NewDecoder(rr.Body).Decode(&user); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if user.Email != *body.Email {
		t.Fatalf("expected email %s, got %s", *body.Email, user.Email)
	}
}

func TestUpdateUserHandler_NotFound(t *testing.T) {
	repo := setupTestRepoRouter(sampleUsers())
	router := newRouter(Dependencies{UserRepo: repo})

	// Get JWT token for authentication
	token := getTestJWTToken(router)

	body := UpdateUserRequest{
		Email: stringPtr("updated@example.com"),
	}

	bodyBytes, _ := json.Marshal(body)
	req := httptest.NewRequest(http.MethodPut, "/api/users/nonexistent", bytes.NewReader(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+token)
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusNotFound {
		t.Fatalf("expected status 404, got %d", rr.Code)
	}
}

func TestDeleteUserHandler_Success(t *testing.T) {
	repo := setupTestRepoRouter(sampleUsers())
	router := newRouter(Dependencies{UserRepo: repo})

	// Get JWT token for authentication
	token := getTestJWTToken(router)

	req := httptest.NewRequest(http.MethodDelete, "/api/users/user-1", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusNoContent {
		t.Fatalf("expected status 204, got %d", rr.Code)
	}

	if rr.Body.Len() != 0 {
		t.Fatalf("expected empty body, got %d bytes", rr.Body.Len())
	}
}

func TestDeleteUserHandler_NotFound(t *testing.T) {
	repo := setupTestRepoRouter(sampleUsers())
	router := newRouter(Dependencies{UserRepo: repo})

	// Get JWT token for authentication
	token := getTestJWTToken(router)

	req := httptest.NewRequest(http.MethodDelete, "/api/users/nonexistent", nil)
	req.Header.Set("Authorization", "Bearer "+token)
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusNoContent {
		t.Fatalf("expected status 204 for idempotent delete, got %d", rr.Code)
	}
}

func TestLoginHandler_Success(t *testing.T) {
	// Create a user first
	repo := setupTestRepoRouter(nil)
	createReq := CreateUserRequest{
		Email:    "test@example.com",
		Username: "testuser",
		Password: "password123",
	}
	user, _ := repo.CreateUser(context.Background(), createReq)

	router := newRouter(Dependencies{UserRepo: repo})

	loginReq := LoginRequest{
		Email:    "test@example.com",
		Password: "password123",
	}

	bodyBytes, _ := json.Marshal(loginReq)
	req := httptest.NewRequest(http.MethodPost, "/api/auth/login", bytes.NewReader(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rr.Code)
	}

	var response LoginResponse
	if err := json.NewDecoder(rr.Body).Decode(&response); err != nil {
		t.Fatalf("failed to decode response: %v", err)
	}

	if response.Token == "" {
		t.Fatal("expected non-empty token")
	}

	if response.User.ID != user.ID {
		t.Fatalf("expected user ID %s, got %s", user.ID, response.User.ID)
	}
}

func TestLoginHandler_InvalidCredentials(t *testing.T) {
	repo := setupTestRepoRouter(nil)
	router := newRouter(Dependencies{UserRepo: repo})

	loginReq := LoginRequest{
		Email:    "nonexistent@example.com",
		Password: "wrongpassword",
	}

	bodyBytes, _ := json.Marshal(loginReq)
	req := httptest.NewRequest(http.MethodPost, "/api/auth/login", bytes.NewReader(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("expected status 401, got %d", rr.Code)
	}
}

func TestLoginHandler_MissingFields(t *testing.T) {
	repo := setupTestRepoRouter(nil)
	router := newRouter(Dependencies{UserRepo: repo})

	loginReq := LoginRequest{
		Email: "test@example.com",
		// Missing password
	}

	bodyBytes, _ := json.Marshal(loginReq)
	req := httptest.NewRequest(http.MethodPost, "/api/auth/login", bytes.NewReader(bodyBytes))
	req.Header.Set("Content-Type", "application/json")
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d", rr.Code)
	}
}

func TestLogoutHandler(t *testing.T) {
	router := newRouter(Dependencies{
		UserRepo: setupTestRepoRouter(nil),
	})

	req := httptest.NewRequest(http.MethodPost, "/api/auth/logout", nil)
	rr := httptest.NewRecorder()

	router.ServeHTTP(rr, req)

	if rr.Code != http.StatusNoContent {
		t.Fatalf("expected status 204, got %d", rr.Code)
	}

	if rr.Body.Len() != 0 {
		t.Fatalf("expected empty body, got %d bytes", rr.Body.Len())
	}
}
