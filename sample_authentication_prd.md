# Sample PRD - User Authentication System

## Overview
Implement a user authentication system with JWT tokens and OAuth support.

## Requirements

### Functional Requirements
- User registration with email verification
- Login/logout functionality
- Password reset via email
- JWT token generation and validation
- OAuth integration (Google, GitHub)
- Session management

### Non-Functional Requirements
- Secure password hashing (bcrypt)
- Rate limiting on authentication endpoints
- Token expiration handling
- Account lockout after failed attempts

### Technical Requirements
- RESTful API endpoints
- Database integration (PostgreSQL)
- Redis for session storage
- Email service integration
- Comprehensive logging

## Success Criteria
- Users can register and verify email
- Users can login with valid credentials
- Password reset workflow functions
- OAuth providers work correctly
- All security measures are implemented