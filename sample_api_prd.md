# Sample PRD - REST API Service

## Overview
Implement a comprehensive REST API service with CRUD operations, authentication, and data validation.

## Requirements

### Functional Requirements
- User authentication and authorization
- RESTful endpoints for resource management
- Request/response validation
- Error handling and status codes
- API documentation (OpenAPI/Swagger)
- Rate limiting and throttling
- Data pagination and filtering

### Non-Functional Requirements
- Security (HTTPS, input sanitization)
- Performance optimization
- Scalability considerations
- Monitoring and logging
- Database transactions
- Cache management

### API Endpoints
- GET /api/users - List users with pagination
- POST /api/users - Create new user
- GET /api/users/{id} - Get user by ID
- PUT /api/users/{id} - Update user
- DELETE /api/users/{id} - Delete user
- POST /api/auth/login - User authentication
- POST /api/auth/logout - User logout
- GET /api/resources - Resource management

### Data Models
- User: id, email, username, created_at, updated_at
- Resource: id, name, description, owner_id, created_at
- Authentication: JWT tokens, session management

### Technical Stack
- Backend: Go/Node.js/Python
- Database: PostgreSQL/MongoDB
- Authentication: JWT
- Documentation: OpenAPI 3.0
- Testing: Unit and integration tests

## Tasks

- [x] Bootstrap Go HTTP server with routing, configuration, and `/healthz` endpoint.
- [x] Create in-memory user repository and wire GET `/api/users` with pagination support.
- [x] Implement POST `/api/users` with payload validation and structured error responses.
- [x] Implement GET `/api/users/{id}` with not-found handling.
- [x] Implement PUT `/api/users/{id}` with update validation and optimistic locking placeholder.
- [x] Implement DELETE `/api/users/{id}` with idempotent behavior.
- [x] Add JWT-based authentication flows for login/logout endpoints.
- [x] Document the API with OpenAPI 3.0 and include request/response schemas.
- [x] Implement rate limiting and throttling middleware.
- [x] Add input sanitization and security headers.
- [x] Implement resource management endpoints (/api/resources) with CRUD operations.
- [x] Add authentication middleware to protect sensitive endpoints.
- [x] Update OpenAPI documentation with security schemes and resource endpoints.
