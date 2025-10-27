package api

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

func newRouter(deps Dependencies) http.Handler {
	if deps.UserRepo == nil {
		config, err := NewUserConfig()
		if err != nil {
			panic(fmt.Sprintf("Failed to initialize user repository config: %v", err))
		}
		deps.UserRepo = NewInMemoryUserRepository(nil, config)
	}

	if deps.ResourceRepo == nil {
		deps.ResourceRepo = NewInMemoryResourceRepository()
	}

	if deps.RateLimiter == nil {
		// Default rate limit: 60 requests per minute with burst of 10
		deps.RateLimiter = NewRateLimiter(60, 10)
		// Start cleanup routine
		deps.RateLimiter.CleanupRoutine(context.Background(), DefaultCleanupInterval)
	}

	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	// Security middleware
	r.Use(SecurityMiddleware)
	r.Use(InputSanitizationMiddleware)

	// Apply rate limiting to all endpoints
	r.Use(deps.RateLimiter.RateLimit)

	// Public endpoints
	r.Get("/healthz", healthHandler)
	r.Post("/api/auth/login", loginHandler(deps.UserRepo))
	r.Post("/api/auth/logout", logoutHandler())

	// User endpoints (public for now, but could be protected with auth)
	r.Get("/api/users", listUsersHandler(deps.UserRepo))
	r.Post("/api/users", createUserHandler(deps.UserRepo))
	r.Get("/api/users/{id}", getUserHandler(deps.UserRepo))

	// Protected endpoints (require authentication)
	r.Group(func(r chi.Router) {
		// Apply authentication middleware to this group
		r.Use(AuthMiddleware(deps.UserRepo))

		// Protected user operations
		r.Put("/api/users/{id}", updateUserHandler(deps.UserRepo))
		r.Delete("/api/users/{id}", deleteUserHandler(deps.UserRepo))

		// Resource management endpoints
		r.Get("/api/resources", listResourcesHandler(deps.ResourceRepo))
		r.Post("/api/resources", createResourceHandler(deps.ResourceRepo))
		r.Get("/api/resources/{id}", getResourceHandler(deps.ResourceRepo))
		r.Put("/api/resources/{id}", updateResourceHandler(deps.ResourceRepo))
		r.Delete("/api/resources/{id}", deleteResourceHandler(deps.ResourceRepo))
	})

	return r
}

func healthHandler(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)

	_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
}

func listUsersHandler(repo UserRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "user repository unavailable")
			return
		}

		page, err := parsePositiveInt(r, "page", defaultUsersPage)
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		pageSize, err := parsePositiveInt(r, "page_size", defaultUsersPageSize)
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		result, err := repo.ListUsers(r.Context(), ListUsersParams{
			Page:     page,
			PageSize: pageSize,
		})
		if err != nil {
			writeError(w, http.StatusInternalServerError, "failed to list users")
			return
		}

		response := struct {
			Data       []User     `json:"data"`
			Pagination Pagination `json:"pagination"`
		}{
			Data:       result.Users,
			Pagination: result.Pagination,
		}

		writeJSON(w, http.StatusOK, response)
	}
}

func parsePositiveInt(r *http.Request, key string, fallback int) (int, error) {
	raw := strings.TrimSpace(r.URL.Query().Get(key))
	if raw == "" {
		return fallback, nil
	}

	value, err := strconv.Atoi(raw)
	if err != nil || value < 1 {
		return 0, fmt.Errorf("invalid value for %s", key)
	}

	return value, nil
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func writeValidationErrors(w http.ResponseWriter, errors ValidationErrors) {
	type validationErrorResponse struct {
		Error  string            `json:"error"`
		Fields []ValidationError `json:"fields"`
	}

	response := validationErrorResponse{
		Error:  "validation failed",
		Fields: errors,
	}

	writeJSON(w, http.StatusBadRequest, response)
}

func createUserHandler(repo UserRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "user repository unavailable")
			return
		}

		var req CreateUserRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON payload")
			return
		}

		// Sanitize input (but not password - passwords should be validated, not modified)
		req.Email = sanitizeInput(req.Email)
		req.Username = sanitizeInput(req.Username)

		if validationErrors := validateCreateUserRequest(req); len(validationErrors) > 0 {
			writeValidationErrors(w, validationErrors)
			return
		}

		user, err := repo.CreateUser(r.Context(), req)
		if err != nil {
			if strings.Contains(err.Error(), "already exists") {
				writeError(w, http.StatusConflict, err.Error())
				return
			}
			writeError(w, http.StatusInternalServerError, "failed to create user")
			return
		}

		writeJSON(w, http.StatusCreated, user)
	}
}

func getUserHandler(repo UserRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "user repository unavailable")
			return
		}

		userID := chi.URLParam(r, "id")
		if userID == "" {
			writeError(w, http.StatusBadRequest, "user ID is required")
			return
		}

		user, err := repo.GetUserByID(r.Context(), userID)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				writeError(w, http.StatusNotFound, err.Error())
				return
			}
			writeError(w, http.StatusInternalServerError, "failed to retrieve user")
			return
		}

		writeJSON(w, http.StatusOK, user)
	}
}

func updateUserHandler(repo UserRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "user repository unavailable")
			return
		}

		userID := chi.URLParam(r, "id")
		if userID == "" {
			writeError(w, http.StatusBadRequest, "user ID is required")
			return
		}

		var req UpdateUserRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON payload")
			return
		}

		if validationErrors := validateUpdateUserRequest(req); len(validationErrors) > 0 {
			writeValidationErrors(w, validationErrors)
			return
		}

		user, err := repo.UpdateUser(r.Context(), userID, req)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				writeError(w, http.StatusNotFound, err.Error())
				return
			}
			if strings.Contains(err.Error(), "already exists") {
				writeError(w, http.StatusConflict, err.Error())
				return
			}
			writeError(w, http.StatusInternalServerError, "failed to update user")
			return
		}

		writeJSON(w, http.StatusOK, user)
	}
}

func deleteUserHandler(repo UserRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "user repository unavailable")
			return
		}

		userID := chi.URLParam(r, "id")
		if userID == "" {
			writeError(w, http.StatusBadRequest, "user ID is required")
			return
		}

		err := repo.DeleteUser(r.Context(), userID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "failed to delete user")
			return
		}

		w.WriteHeader(http.StatusNoContent)
	}
}

func loginHandler(repo UserRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "user repository unavailable")
			return
		}

		var req LoginRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON payload")
			return
		}

		// Sanitize input (but not password - passwords should be validated, not modified)
		req.Email = sanitizeInput(req.Email)

		// Basic validation
		if req.Email == "" || req.Password == "" {
			writeError(w, http.StatusBadRequest, "email and password are required")
			return
		}

		user, err := repo.AuthenticateUser(r.Context(), req.Email, req.Password)
		if err != nil {
			writeError(w, http.StatusUnauthorized, "invalid credentials")
			return
		}

		token, err := repo.GenerateJWTToken(user)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "failed to generate token")
			return
		}

		response := LoginResponse{
			Token: token,
			User:  user,
		}

		writeJSON(w, http.StatusOK, response)
	}
}

func logoutHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// In a stateless JWT implementation, logout is typically handled on the client side
		// by simply discarding the token. For a more robust implementation, we might
		// maintain a blacklist of tokens or use refresh tokens.

		w.WriteHeader(http.StatusNoContent)
	}
}

func listResourcesHandler(repo ResourceRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "resource repository unavailable")
			return
		}

		page, err := parsePositiveInt(r, "page", defaultResourcesPage)
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		pageSize, err := parsePositiveInt(r, "page_size", defaultResourcesPageSize)
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		result, err := repo.ListResources(r.Context(), ListResourcesParams{
			Page:     page,
			PageSize: pageSize,
		})
		if err != nil {
			writeError(w, http.StatusInternalServerError, "failed to list resources")
			return
		}

		response := struct {
			Data       []Resource `json:"data"`
			Pagination Pagination `json:"pagination"`
		}{
			Data:       result.Resources,
			Pagination: result.Pagination,
		}

		writeJSON(w, http.StatusOK, response)
	}
}

func createResourceHandler(repo ResourceRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "resource repository unavailable")
			return
		}

		ownerID, ok := GetUserIDFromContext(r.Context())
		if !ok {
			writeError(w, http.StatusUnauthorized, "user authentication required")
			return
		}

		var req CreateResourceRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON payload")
			return
		}

		if validationErrors := validateCreateResourceRequest(req); len(validationErrors) > 0 {
			writeValidationErrors(w, validationErrors)
			return
		}

		resource, err := repo.CreateResource(r.Context(), req, ownerID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "failed to create resource")
			return
		}

		writeJSON(w, http.StatusCreated, resource)
	}
}

func getResourceHandler(repo ResourceRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "resource repository unavailable")
			return
		}

		resourceID := chi.URLParam(r, "id")
		if resourceID == "" {
			writeError(w, http.StatusBadRequest, "resource ID is required")
			return
		}

		resource, err := repo.GetResourceByID(r.Context(), resourceID)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				writeError(w, http.StatusNotFound, err.Error())
				return
			}
			writeError(w, http.StatusInternalServerError, "failed to retrieve resource")
			return
		}

		writeJSON(w, http.StatusOK, resource)
	}
}

func updateResourceHandler(repo ResourceRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "resource repository unavailable")
			return
		}

		resourceID := chi.URLParam(r, "id")
		if resourceID == "" {
			writeError(w, http.StatusBadRequest, "resource ID is required")
			return
		}

		ownerID, ok := GetUserIDFromContext(r.Context())
		if !ok {
			writeError(w, http.StatusUnauthorized, "user authentication required")
			return
		}

		var req UpdateResourceRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON payload")
			return
		}

		if validationErrors := validateUpdateResourceRequest(req); len(validationErrors) > 0 {
			writeValidationErrors(w, validationErrors)
			return
		}

		resource, err := repo.UpdateResource(r.Context(), resourceID, req, ownerID)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				writeError(w, http.StatusNotFound, err.Error())
				return
			}
			if strings.Contains(err.Error(), "access denied") {
				writeError(w, http.StatusForbidden, err.Error())
				return
			}
			writeError(w, http.StatusInternalServerError, "failed to update resource")
			return
		}

		writeJSON(w, http.StatusOK, resource)
	}
}

func deleteResourceHandler(repo ResourceRepository) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if repo == nil {
			writeError(w, http.StatusInternalServerError, "resource repository unavailable")
			return
		}

		resourceID := chi.URLParam(r, "id")
		if resourceID == "" {
			writeError(w, http.StatusBadRequest, "resource ID is required")
			return
		}

		ownerID, ok := GetUserIDFromContext(r.Context())
		if !ok {
			writeError(w, http.StatusUnauthorized, "user authentication required")
			return
		}

		err := repo.DeleteResource(r.Context(), resourceID, ownerID)
		if err != nil {
			if strings.Contains(err.Error(), "not found") {
				writeError(w, http.StatusNotFound, err.Error())
				return
			}
			if strings.Contains(err.Error(), "access denied") {
				writeError(w, http.StatusForbidden, err.Error())
				return
			}
			writeError(w, http.StatusInternalServerError, "failed to delete resource")
			return
		}

		w.WriteHeader(http.StatusNoContent)
	}
}
