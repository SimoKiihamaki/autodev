package api

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/bcrypt"
)

// Default pagination values for user listing.
const (
	defaultUsersPage     = 1
	defaultUsersPageSize = 20
	maxUsersPageSize     = 100
	maxEmailLength       = 254
	maxUsernameLength    = 50
	minUsernameLength    = 3
	minPasswordLength    = 6
	// JWT settings
	jwtExpirationHours = 24
	jwtIssuer          = "autodev-api"
	jwtSecretEnvKey    = "JWT_SECRET"
)

// UserConfig holds configuration for the user management system.
type UserConfig struct {
	JWTSecret string
}

// NewUserConfig creates a new configuration by loading environment variables.
func NewUserConfig() (*UserConfig, error) {
	secret := os.Getenv(jwtSecretEnvKey)
	if secret == "" {
		return nil, fmt.Errorf("JWT_SECRET environment variable is required")
	}
	return &UserConfig{JWTSecret: secret}, nil
}

// User represents the public API view of a user.
type User struct {
	ID        string    `json:"id"`
	Email     string    `json:"email"`
	Username  string    `json:"username"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

// UserWithPassword represents a user with their password (for internal use).
type UserWithPassword struct {
	User
	Password string `json:"-"`
}

// CreateUserRequest defines the payload for creating a new user.
type CreateUserRequest struct {
	Email    string `json:"email"`
	Username string `json:"username"`
	Password string `json:"password"`
}

// UpdateUserRequest defines the payload for updating an existing user.
type UpdateUserRequest struct {
	Email    *string `json:"email"`
	Username *string `json:"username"`
}

// LoginRequest defines the payload for user authentication.
type LoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

// LoginResponse defines the response for successful authentication.
type LoginResponse struct {
	Token string `json:"token"`
	User  User   `json:"user"`
}

// JWTClaims represents the claims stored in the JWT token.
type JWTClaims struct {
	UserID   string `json:"user_id"`
	Email    string `json:"email"`
	Username string `json:"username"`
	jwt.RegisteredClaims
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

// ValidationError represents a single field validation error.
type ValidationError struct {
	Field   string `json:"field"`
	Message string `json:"message"`
}

// ValidationErrors represents multiple validation errors.
type ValidationErrors []ValidationError

func (ve ValidationErrors) Error() string {
	if len(ve) == 0 {
		return "validation failed"
	}
	return fmt.Sprintf("validation failed on %d field(s)", len(ve))
}

// validateEmail performs basic email validation.
func validateEmail(email string) error {
	if email == "" {
		return errors.New("email is required")
	}
	if utf8.RuneCountInString(email) > maxEmailLength {
		return fmt.Errorf("email exceeds maximum length of %d characters", maxEmailLength)
	}
	// Basic email validation - check for @ and at least one dot after @
	at := strings.LastIndex(email, "@")
	if at <= 0 || at == len(email)-1 {
		return errors.New("invalid email format")
	}
	dot := strings.LastIndex(email[at:], ".")
	if dot == -1 || dot == len(email[at:])-1 {
		return errors.New("invalid email format")
	}
	return nil
}

// validateUsername performs username validation.
func validateUsername(username string) error {
	if username == "" {
		return errors.New("username is required")
	}
	if utf8.RuneCountInString(username) < minUsernameLength {
		return fmt.Errorf("username must be at least %d characters", minUsernameLength)
	}
	if utf8.RuneCountInString(username) > maxUsernameLength {
		return fmt.Errorf("username cannot exceed %d characters", maxUsernameLength)
	}
	// Allow only alphanumeric characters, underscores, and hyphens
	for _, r := range username {
		if !((r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '_' || r == '-') {
			return errors.New("username can only contain letters, numbers, underscores, and hyphens")
		}
	}
	return nil
}

// validatePassword performs password validation.
func validatePassword(password string) error {
	if password == "" {
		return errors.New("password is required")
	}
	if utf8.RuneCountInString(password) < minPasswordLength {
		return fmt.Errorf("password must be at least %d characters", minPasswordLength)
	}
	return nil
}

// validateCreateUserRequest validates a CreateUserRequest.
func validateCreateUserRequest(req CreateUserRequest) ValidationErrors {
	var errors ValidationErrors

	if err := validateEmail(req.Email); err != nil {
		errors = append(errors, ValidationError{Field: "email", Message: err.Error()})
	}

	if err := validateUsername(req.Username); err != nil {
		errors = append(errors, ValidationError{Field: "username", Message: err.Error()})
	}

	if err := validatePassword(req.Password); err != nil {
		errors = append(errors, ValidationError{Field: "password", Message: err.Error()})
	}

	return errors
}

// validateUpdateUserRequest validates an UpdateUserRequest.
func validateUpdateUserRequest(req UpdateUserRequest) ValidationErrors {
	var errors ValidationErrors

	if req.Email != nil {
		if err := validateEmail(*req.Email); err != nil {
			errors = append(errors, ValidationError{Field: "email", Message: err.Error()})
		}
	}

	if req.Username != nil {
		if err := validateUsername(*req.Username); err != nil {
			errors = append(errors, ValidationError{Field: "username", Message: err.Error()})
		}
	}

	return errors
}

// UserRepository describes behaviours required to persist and retrieve users.
type UserRepository interface {
	ListUsers(ctx context.Context, params ListUsersParams) (ListUsersResult, error)
	CreateUser(ctx context.Context, req CreateUserRequest) (User, error)
	GetUserByID(ctx context.Context, id string) (User, error)
	UpdateUser(ctx context.Context, id string, req UpdateUserRequest) (User, error)
	DeleteUser(ctx context.Context, id string) error
	AuthenticateUser(ctx context.Context, email, password string) (User, error)
	GenerateJWTToken(user User) (string, error)
	ValidateJWTToken(tokenString string) (*JWTClaims, error)
}

// InMemoryUserRepository stores users in memory; intended for early development and testing.
type InMemoryUserRepository struct {
	mu     sync.RWMutex
	users  []UserWithPassword
	nextID int
	config *UserConfig
}

// NewInMemoryUserRepository constructs a repository seeded with optional initial users.
func NewInMemoryUserRepository(initial []User, config *UserConfig) *InMemoryUserRepository {
	repo := &InMemoryUserRepository{nextID: 1, config: config}
	if len(initial) > 0 {
		repo.replaceAll(initial)
		// Set nextID to be higher than the highest existing ID
		for _, user := range initial {
			if len(user.ID) > 5 && user.ID[:5] == "user-" {
				if id, err := strconv.Atoi(user.ID[5:]); err == nil && id >= repo.nextID {
					repo.nextID = id + 1
				}
			}
		}
	}

	return repo
}

// NewInMemoryUserRepositoryWithoutConfig constructs a repository without JWT config (for testing).
func NewInMemoryUserRepositoryWithoutConfig(initial []User) *InMemoryUserRepository {
	repo := &InMemoryUserRepository{nextID: 1, config: nil}
	if len(initial) > 0 {
		repo.replaceAll(initial)
		// Set nextID to be higher than the highest existing ID
		for _, user := range initial {
			if len(user.ID) > 5 && user.ID[:5] == "user-" {
				if id, err := strconv.Atoi(user.ID[5:]); err == nil && id >= repo.nextID {
					repo.nextID = id + 1
				}
			}
		}
	}

	return repo
}

// SetConfig sets the configuration for the repository.
func (r *InMemoryUserRepository) SetConfig(config *UserConfig) {
	r.mu.Lock()
	r.config = config
	r.mu.Unlock()
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
		for i := start; i < end; i++ {
			slice[i-start] = r.users[i].User
		}
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

// CreateUser adds a new user to the repository.
func (r *InMemoryUserRepository) CreateUser(_ context.Context, req CreateUserRequest) (User, error) {
	if r == nil {
		return User{}, errors.New("repository is nil")
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	// Check for duplicate email
	for _, existing := range r.users {
		if existing.Email == req.Email {
			return User{}, fmt.Errorf("user with email %s already exists", req.Email)
		}
		if existing.Username == req.Username {
			return User{}, fmt.Errorf("user with username %s already exists", req.Username)
		}
	}

	now := time.Now().UTC()

	// Hash the password using bcrypt
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(req.Password), bcrypt.DefaultCost)
	if err != nil {
		return User{}, fmt.Errorf("failed to hash password: %w", err)
	}

	userWithPassword := UserWithPassword{
		User: User{
			ID:        fmt.Sprintf("user-%d", r.nextID),
			Email:     req.Email,
			Username:  req.Username,
			CreatedAt: now,
			UpdatedAt: now,
		},
		Password: string(hashedPassword),
	}

	r.nextID++
	r.users = append(r.users, userWithPassword)

	return userWithPassword.User, nil
}

// GetUserByID retrieves a user by their ID.
func (r *InMemoryUserRepository) GetUserByID(_ context.Context, id string) (User, error) {
	if r == nil {
		return User{}, errors.New("repository is nil")
	}

	r.mu.RLock()
	defer r.mu.RUnlock()

	for _, userWithPassword := range r.users {
		if userWithPassword.ID == id {
			return userWithPassword.User, nil
		}
	}

	return User{}, fmt.Errorf("user with ID %s not found", id)
}

// UpdateUser updates an existing user.
func (r *InMemoryUserRepository) UpdateUser(_ context.Context, id string, req UpdateUserRequest) (User, error) {
	if r == nil {
		return User{}, errors.New("repository is nil")
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	for i, userWithPassword := range r.users {
		if userWithPassword.ID == id {
			updated := userWithPassword
			updated.UpdatedAt = time.Now().UTC()

			if req.Email != nil {
				// Check for duplicate email with other users
				for j, other := range r.users {
					if j != i && other.Email == *req.Email {
						return User{}, fmt.Errorf("user with email %s already exists", *req.Email)
					}
				}
				updated.Email = *req.Email
			}

			if req.Username != nil {
				// Check for duplicate username with other users
				for j, other := range r.users {
					if j != i && other.Username == *req.Username {
						return User{}, fmt.Errorf("user with username %s already exists", *req.Username)
					}
				}
				updated.Username = *req.Username
			}

			r.users[i] = updated
			return updated.User, nil
		}
	}

	return User{}, fmt.Errorf("user with ID %s not found", id)
}

// DeleteUser removes a user by their ID.
func (r *InMemoryUserRepository) DeleteUser(_ context.Context, id string) error {
	if r == nil {
		return errors.New("repository is nil")
	}

	r.mu.Lock()
	defer r.mu.Unlock()

	for i, user := range r.users {
		if user.ID == id {
			// Remove user from slice
			r.users = append(r.users[:i], r.users[i+1:]...)
			return nil
		}
	}

	// Idempotent behavior - don't return error if user doesn't exist
	return nil
}

// AuthenticateUser validates user credentials and returns the user if valid.
func (r *InMemoryUserRepository) AuthenticateUser(_ context.Context, email, password string) (User, error) {
	if r == nil {
		return User{}, errors.New("repository is nil")
	}

	r.mu.RLock()
	defer r.mu.RUnlock()

	for _, userWithPassword := range r.users {
		if userWithPassword.Email == email {
			// Compare the provided password with the stored hashed password
			err := bcrypt.CompareHashAndPassword([]byte(userWithPassword.Password), []byte(password))
			if err == nil {
				return userWithPassword.User, nil
			}
			return User{}, errors.New("invalid credentials")
		}
	}

	return User{}, errors.New("invalid credentials")
}

// GenerateJWTToken creates a new JWT token for the given user.
func (r *InMemoryUserRepository) GenerateJWTToken(user User) (string, error) {
	r.mu.RLock()
	cfg := r.config
	r.mu.RUnlock()

	if cfg == nil || cfg.JWTSecret == "" {
		return "", errors.New("JWT configuration is missing")
	}

	claims := JWTClaims{
		UserID:   user.ID,
		Email:    user.Email,
		Username: user.Username,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Duration(jwtExpirationHours) * time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			Issuer:    jwtIssuer,
			Subject:   user.ID,
		},
	}

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString([]byte(cfg.JWTSecret))
}

// ValidateJWTToken validates a JWT token and returns the claims if valid.
func (r *InMemoryUserRepository) ValidateJWTToken(tokenString string) (*JWTClaims, error) {
	r.mu.RLock()
	cfg := r.config
	r.mu.RUnlock()

	if cfg == nil || cfg.JWTSecret == "" {
		return nil, errors.New("JWT configuration is missing")
	}

	token, err := jwt.ParseWithClaims(
		tokenString,
		&JWTClaims{},
		func(token *jwt.Token) (interface{}, error) {
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
			}
			return []byte(cfg.JWTSecret), nil
		},
		jwt.WithValidMethods([]string{jwt.SigningMethodHS256.Alg()}),
		jwt.WithIssuer(jwtIssuer),
		jwt.WithLeeway(30*time.Second),
	)

	if err != nil {
		return nil, err
	}

	if claims, ok := token.Claims.(*JWTClaims); ok && token.Valid {
		return claims, nil
	}

	return nil, errors.New("invalid token")
}

// generateRandomPassword creates a cryptographically secure random password
func generateRandomPassword(length int) (string, error) {
	if length < 8 {
		length = 16 // Default to 16 characters if too short
	}

	bytes := make([]byte, length)
	_, err := rand.Read(bytes)
	if err != nil {
		return "", err
	}

	return hex.EncodeToString(bytes)[:length], nil
}

// replaceAll swaps the internal user list for the provided one in a deterministic order.
// This function is used for test/dev purposes and generates secure random passwords for seeded users.
func (r *InMemoryUserRepository) replaceAll(users []User) {
	clone := make([]UserWithPassword, 0, len(users))
	for _, user := range users {
		// Generate a secure random password for each seeded user
		defaultPassword, err := generateRandomPassword(16)
		if err != nil {
			// If random generation fails, use a timestamp-based fallback
			defaultPassword = fmt.Sprintf("temp-%d", time.Now().UnixNano())
		}

		// Hash the generated password using bcrypt
		hashedPassword, err := bcrypt.GenerateFromPassword([]byte(defaultPassword), bcrypt.DefaultCost)
		if err != nil {
			// If hashing fails, skip this user and log the error
			fmt.Printf("Error hashing password for user %s: %v\n", user.ID, err)
			continue
		}

		clone = append(clone, UserWithPassword{
			User:     user,
			Password: string(hashedPassword),
		})
	}

	sort.Slice(clone, func(i, j int) bool {
		if clone[i].CreatedAt.Equal(clone[j].CreatedAt) {
			return clone[i].ID < clone[j].ID
		}
		return clone[i].CreatedAt.Before(clone[j].CreatedAt)
	})

	r.users = clone
}
