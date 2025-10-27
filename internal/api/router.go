package api

import (
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
		deps.UserRepo = NewInMemoryUserRepository(nil)
	}

	r := chi.NewRouter()
	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	r.Get("/healthz", healthHandler)
	r.Get("/api/users", listUsersHandler(deps.UserRepo))

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
