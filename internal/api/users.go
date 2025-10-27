package api

import (
	"context"
	"errors"
	"sort"
	"sync"
	"time"
)

// Default pagination values for user listing.
const (
	defaultUsersPage     = 1
	defaultUsersPageSize = 20
	maxUsersPageSize     = 100
)

// User represents the public API view of a user.
type User struct {
	ID        string    `json:"id"`
	Email     string    `json:"email"`
	Username  string    `json:"username"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// ListUsersParams defines filters accepted by ListUsers.
type ListUsersParams struct {
	Page     int
	PageSize int
}

// Pagination describes the pagination metadata returned by list endpoints.
type Pagination struct {
	Page       int `json:"page"`
	PageSize   int `json:"page_size"`
	TotalItems int `json:"total_items"`
	TotalPages int `json:"total_pages"`
}

// ListUsersResult wraps the users returned by the repository together with pagination information.
type ListUsersResult struct {
	Users      []User
	Pagination Pagination
}

// UserRepository describes behaviours required to persist and retrieve users.
type UserRepository interface {
	ListUsers(ctx context.Context, params ListUsersParams) (ListUsersResult, error)
}

// InMemoryUserRepository stores users in memory; intended for early development and testing.
type InMemoryUserRepository struct {
	mu    sync.RWMutex
	users []User
}

// NewInMemoryUserRepository constructs a repository seeded with optional initial users.
func NewInMemoryUserRepository(initial []User) *InMemoryUserRepository {
	repo := &InMemoryUserRepository{}
	if len(initial) > 0 {
		repo.replaceAll(initial)
	}

	return repo
}

// ListUsers returns a paginated slice of users.
func (r *InMemoryUserRepository) ListUsers(_ context.Context, params ListUsersParams) (ListUsersResult, error) {
	if r == nil {
		return ListUsersResult{}, errors.New("repository is nil")
	}

	page := params.Page
	if page < 1 {
		page = defaultUsersPage
	}

	pageSize := params.PageSize
	if pageSize <= 0 {
		pageSize = defaultUsersPageSize
	}
	if pageSize > maxUsersPageSize {
		pageSize = maxUsersPageSize
	}

	r.mu.RLock()
	defer r.mu.RUnlock()

	total := len(r.users)
	start := (page - 1) * pageSize
	if start > total {
		start = total
	}

	end := start + pageSize
	if end > total {
		end = total
	}

	var slice []User
	if start < end {
		slice = make([]User, end-start)
		copy(slice, r.users[start:end])
	} else {
		slice = []User{}
	}

	totalPages := 0
	if total > 0 {
		totalPages = (total + pageSize - 1) / pageSize
	}

	return ListUsersResult{
		Users: slice,
		Pagination: Pagination{
			Page:       page,
			PageSize:   pageSize,
			TotalItems: total,
			TotalPages: totalPages,
		},
	}, nil
}

// replaceAll swaps the internal user list for the provided one in a deterministic order.
func (r *InMemoryUserRepository) replaceAll(users []User) {
	clone := make([]User, len(users))
	copy(clone, users)

	sort.Slice(clone, func(i, j int) bool {
		if clone[i].CreatedAt.Equal(clone[j].CreatedAt) {
			return clone[i].ID < clone[j].ID
		}
		return clone[i].CreatedAt.Before(clone[j].CreatedAt)
	})

	r.users = clone
}
