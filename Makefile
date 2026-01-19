APP := aprd
PYTHON := python3
TOOLS_DIR := tools
PREFIX ?= /usr/local
BINDIR ?= $(PREFIX)/bin

.PHONY: build install run clean tidy ci lint lint-go lint-py test test-go test-go-race test-py fmt fmt-go fmt-py typecheck typecheck-lenient

# Build targets
build:
	go mod tidy
	mkdir -p bin
	go build -o bin/$(APP) ./cmd/aprd

# Install target
# Usage:
#   make install              # Installs to /usr/local/bin (default PREFIX)
#   make install PREFIX=/usr  # Installs to /usr/bin
#   make install DESTDIR=/tmp/stage  # Stages installation under /tmp/stage for packaging
# Note: DESTDIR should not have a trailing slash for proper path handling
install: build
	mkdir -p $(DESTDIR)$(BINDIR)
	install -m 0755 bin/$(APP) $(DESTDIR)$(BINDIR)/$(APP)

run: build
	./bin/$(APP)

clean:
	rm -rf bin

tidy:
	go mod tidy

# CI target - runs all checks
ci: lint test test-go-race typecheck-lenient
	@echo "✅ All CI checks passed"

# Linting
lint: lint-go lint-py
	@echo "✅ All linting passed"

lint-go:
	@echo "🔍 Running golangci-lint..."
	golangci-lint run ./...

lint-py:
	@echo "🔍 Running ruff..."
	cd $(TOOLS_DIR) && ruff check auto_prd/

# Testing
test: test-go
	@echo "✅ All tests passed"

test-go:
	@echo "🧪 Running Go tests..."
	go test ./...

test-go-race:
	@echo "🧪 Running Go tests with race detector..."
	go test ./... -race

test-py:
	@echo "🧪 Running Python tests..."
	cd $(TOOLS_DIR) && uv run pytest tests/ -v

# Formatting
fmt: fmt-go fmt-py
	@echo "✅ All formatting complete"

fmt-go:
	@echo "📝 Formatting Go code..."
	goimports -w .

fmt-py:
	@echo "📝 Formatting Python code..."
	cd $(TOOLS_DIR) && ruff format auto_prd/

# Type checking
typecheck:
	@echo "🔎 Running type checks..."
	cd $(TOOLS_DIR) && $(PYTHON) -m mypy auto_prd/

# Type checking (lenient, for CI rollout)
typecheck-lenient:
	@echo "🔎 Running type checks (lenient mode)..."
	cd $(TOOLS_DIR) && $(PYTHON) -m mypy auto_prd/ --ignore-missing-imports || true
