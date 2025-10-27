package api

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestInMemoryUserRepository_ListUsers(t *testing.T) {
	repo := NewInMemoryUserRepository(sampleUsers())

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
	repo := NewInMemoryUserRepository(sampleUsers())
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
	repo := NewInMemoryUserRepository(sampleUsers())
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
