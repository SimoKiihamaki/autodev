package api

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"
	"unicode/utf8"
)

// Resource constants
const (
	maxResourceNameLength    = 100
	maxResourceDescLength    = 1000
	minResourceNameLength    = 1
	defaultResourcesPage     = 1
	defaultResourcesPageSize = 20
	maxResourcesPageSize     = 100
)

// Resource represents a resource in the system
type Resource struct {
	ID          string    `json:"id"`
	Name        string    `json:"name"`
	Description string    `json:"description"`
	OwnerID     string    `json:"owner_id"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// CreateResourceRequest defines the payload for creating a new resource
type CreateResourceRequest struct {
	Name        string `json:"name"`
	Description string `json:"description"`
}

// UpdateResourceRequest defines the payload for updating an existing resource
type UpdateResourceRequest struct {
	Name        *string `json:"name"`
	Description *string `json:"description"`
}

// ListResourcesParams defines filters accepted by ListResources
type ListResourcesParams struct {
	Page     int
	PageSize int
}

// ResourceRepository describes behaviours required to persist and retrieve resources
type ResourceRepository interface {
	ListResources(ctx context.Context, params ListResourcesParams) (ListResourcesResult, error)
	CreateResource(ctx context.Context, req CreateResourceRequest, ownerID string) (Resource, error)
	GetResourceByID(ctx context.Context, id string) (Resource, error)
	UpdateResource(ctx context.Context, id string, req UpdateResourceRequest, ownerID string) (Resource, error)
	DeleteResource(ctx context.Context, id string, ownerID string) error
}

// ListResourcesResult wraps the resources returned by the repository together with pagination information
type ListResourcesResult struct {
	Resources  []Resource
	Pagination Pagination
}

// InMemoryResourceRepository stores resources in memory; intended for early development and testing
type InMemoryResourceRepository struct {
	mu        sync.RWMutex
	resources []Resource
	nextID    int
}

// NewInMemoryResourceRepository constructs a resource repository
func NewInMemoryResourceRepository() *InMemoryResourceRepository {
	return &InMemoryResourceRepository{nextID: 1}
}

// validateResourceName performs resource name validation
func validateResourceName(name string) error {
	if name == "" {
		return errors.New("resource name is required")
	}
	if utf8.RuneCountInString(name) < minResourceNameLength {
		return fmt.Errorf("resource name must be at least %d characters", minResourceNameLength)
	}
	if utf8.RuneCountInString(name) > maxResourceNameLength {
		return fmt.Errorf("resource name cannot exceed %d characters", maxResourceNameLength)
	}
	return nil
}

// validateResourceDescription performs resource description validation
func validateResourceDescription(description string) error {
	if utf8.RuneCountInString(description) > maxResourceDescLength {
		return fmt.Errorf("resource description cannot exceed %d characters", maxResourceDescLength)
	}
	return nil
}

// validateCreateResourceRequest validates a CreateResourceRequest
func validateCreateResourceRequest(req CreateResourceRequest) ValidationErrors {
	var errors ValidationErrors

	if err := validateResourceName(req.Name); err != nil {
		errors = append(errors, ValidationError{Field: "name", Message: err.Error()})
	}

	if err := validateResourceDescription(req.Description); err != nil {
		errors = append(errors, ValidationError{Field: "description", Message: err.Error()})
	}

	return errors
}

// validateUpdateResourceRequest validates an UpdateResourceRequest
func validateUpdateResourceRequest(req UpdateResourceRequest) ValidationErrors {
	var errors ValidationErrors

	if req.Name != nil {
		if err := validateResourceName(*req.Name); err != nil {
			errors = append(errors, ValidationError{Field: "name", Message: err.Error()})
		}
	}

	if req.Description != nil {
		if err := validateResourceDescription(*req.Description); err != nil {
			errors = append(errors, ValidationError{Field: "description", Message: err.Error()})
		}
	}

	return errors
}

// ListResources returns a paginated slice of resources
func (r *InMemoryResourceRepository) ListResources(_ context.Context, params ListResourcesParams) (ListResourcesResult, error) {
	if r == nil {
		return ListResourcesResult{}, errors.New("resource repository is nil")
	}

	page := params.Page
	if page < 1 {
		page = defaultResourcesPage
	}

	pageSize := params.PageSize
	if pageSize <= 0 {
		pageSize = defaultResourcesPageSize
	}
	if pageSize > maxResourcesPageSize {
		pageSize = maxResourcesPageSize
	}

	r.mu.RLock()
	defer r.mu.RUnlock()

	total := len(r.resources)
	start := (page - 1) * pageSize
	if start > total {
		start = total
	}

	end := start + pageSize
	if end > total {
		end = total
	}

	var slice []Resource
	if start < end {
		slice = make([]Resource, end-start)
		for i := start; i < end; i++ {
			slice[i-start] = r.resources[i]
		}
	} else {
		slice = []Resource{}
	}

	totalPages := 0
	if total > 0 {
		totalPages = (total + pageSize - 1) / pageSize
	}

	return ListResourcesResult{
		Resources: slice,
		Pagination: Pagination{
			Page:       page,
			PageSize:   pageSize,
			TotalItems: total,
			TotalPages: totalPages,
		},
	}, nil
}

// CreateResource adds a new resource to the repository
func (r *InMemoryResourceRepository) CreateResource(_ context.Context, req CreateResourceRequest, ownerID string) (Resource, error) {
	if r == nil {
		return Resource{}, errors.New("resource repository is nil")
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	// Normalize and validate
	req.Name = strings.TrimSpace(req.Name)
	req.Description = strings.TrimSpace(req.Description)
	if ve := validateCreateResourceRequest(req); len(ve) > 0 {
		return Resource{}, ve
	}
	now := time.Now().UTC()

	resource := Resource{
		ID:          fmt.Sprintf("resource-%d", r.nextID),
		Name:        req.Name,
		Description: req.Description,
		OwnerID:     ownerID,
		CreatedAt:   now,
		UpdatedAt:   now,
	}

	r.nextID++
	r.resources = append(r.resources, resource)

	return resource, nil
}

// GetResourceByID retrieves a resource by their ID
func (r *InMemoryResourceRepository) GetResourceByID(_ context.Context, id string) (Resource, error) {
	if r == nil {
		return Resource{}, errors.New("resource repository is nil")
	}

	r.mu.RLock()
	defer r.mu.RUnlock()

	for _, resource := range r.resources {
		if resource.ID == id {
			return resource, nil
		}
	}

	return Resource{}, fmt.Errorf("resource with ID %s not found", id)
}

// UpdateResource updates an existing resource
func (r *InMemoryResourceRepository) UpdateResource(_ context.Context, id string, req UpdateResourceRequest, ownerID string) (Resource, error) {
	if r == nil {
		return Resource{}, errors.New("resource repository is nil")
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	for i, resource := range r.resources {
		if resource.ID == id {
			// Enforce ownership without leaking existence
			if resource.OwnerID != ownerID {
				return Resource{}, fmt.Errorf("access denied to resource with ID %s", id)
			}

			updated := resource
			updated.UpdatedAt = time.Now().UTC()

			// Normalize and validate
			norm := UpdateResourceRequest{}
			if req.Name != nil {
				n := strings.TrimSpace(*req.Name)
				norm.Name = &n
			}
			if req.Description != nil {
				d := strings.TrimSpace(*req.Description)
				norm.Description = &d
			}
			if ve := validateUpdateResourceRequest(norm); len(ve) > 0 {
				return Resource{}, ve
			}
			if norm.Name != nil {
				updated.Name = *norm.Name
			}
			if norm.Description != nil {
				updated.Description = *norm.Description
			}

			r.resources[i] = updated
			return updated, nil
		}
	}

	return Resource{}, fmt.Errorf("resource with ID %s not found", id)
}

// DeleteResource removes a resource by their ID
func (r *InMemoryResourceRepository) DeleteResource(_ context.Context, id string, ownerID string) error {
	if r == nil {
		return errors.New("resource repository is nil")
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	for i, resource := range r.resources {
		if resource.ID == id {
			// Enforce ownership without leaking existence
			if resource.OwnerID != ownerID {
				return fmt.Errorf("access denied to resource with ID %s", id)
			}

			// Remove resource from slice
			r.resources = append(r.resources[:i], r.resources[i+1:]...)
			return nil
		}
	}

	// Return error if resource doesn't exist (not idempotent for resources for security reasons)
	return fmt.Errorf("resource with ID %s not found", id)
}

// replaceAll swaps the internal resource list for the provided one in a deterministic order
func (r *InMemoryResourceRepository) replaceAll(resources []Resource) {
	clone := make([]Resource, len(resources))
	copy(clone, resources)

	sort.Slice(clone, func(i, j int) bool {
		if clone[i].CreatedAt.Equal(clone[j].CreatedAt) {
			return clone[i].ID < clone[j].ID
		}
		return clone[i].CreatedAt.Before(clone[j].CreatedAt)
	})

	r.resources = clone
}
