# =============================================================================
# AOS v5.0 Makefile -- Development, Build, Test, and Run shortcuts
#
# Usage:
#   make help          Show all available targets
#   make dev           Start development environment
#   make test          Run unit tests
#   make build         Build Docker image
#   make run           Run the full stack
# =============================================================================

.PHONY: help dev test test-all test-unit test-integration lint lint-fix \
        build build-api build-web build-frontend build-no-cache \
        run run-api run-web run-full stop clean clean-data clean-all \
        install install-dev deps verify setup migrate health docker-build \
        check-ast check smoke schema coverage

# ---- Variables ----
IMAGE_NAME ?= aos
IMAGE_TAG ?= v5.0
IMAGE_FULL = $(IMAGE_NAME):$(IMAGE_TAG)
PYTHON := python
PIP := pip
DOCKER := docker
COMPOSE := docker compose
COMPOSE_PROFILES := --profile full
ENV_FILE := .env

# Detect OS for platform-specific commands
ifeq ($(OS),Windows_NT)
    DETECTED_OS := windows
    PY := py
    RMDIR := rmdir /s /q
    DEL := del /q
    MKDIR := mkdir
    CP := copy
    SHELL := cmd.exe
else
    DETECTED_OS := unix
    PY := python3
    RMDIR := rm -rf
    DEL := rm -f
    MKDIR := mkdir -p
    CP := cp
    SHELL := /bin/bash
endif

# =============================================================================
# HELP
# =============================================================================

help: SHELL := /bin/bash
help:
	@echo ""
	@echo "AOS v5.0 -- Agent Operating System"
	@echo "=================================="
	@echo ""
	@printf "  \033[36m%-22s\033[0m %s\n" "make dev"              "Start development mode (API + Web UI)"
	@printf "  \033[36m%-22s\033[0m %s\n" "make test"             "Run unit tests"
	@printf "  \033[36m%-22s\033[0m %s\n" "make test-integration" "Run integration tests"
	@printf "  \033[36m%-22s\033[0m %s\n" "make test-all"         "Run all tests with coverage"
	@printf "  \033[36m%-22s\033[0m %s\n" "make lint"             "Run linting (ruff)"
	@printf "  \033[36m%-22s\033[0m %s\n" "make lint-fix"         "Auto-fix linting issues"
	@echo ""
	@printf "  \033[32m%-22s\033[0m %s\n" "make build"            "Build Docker image"
	@printf "  \033[32m%-22s\033[0m %s\n" "make build-no-cache"   "Build Docker image (no cache)"
	@printf "  \033[32m%-22s\033[0m %s\n" "make docker-build"     "Alias for build"
	@echo ""
	@printf "  \033[33m%-22s\033[0m %s\n" "make run"              "Run full stack (API + Web)"
	@printf "  \033[33m%-22s\033[0m %s\n" "make run-api"          "Run API server only"
	@printf "  \033[33m%-22s\033[0m %s\n" "make run-web"          "Run Web UI only"
	@printf "  \033[33m%-22s\033[0m %s\n" "make run-full"         "Run with all services (DB, Redis)"
	@printf "  \033[33m%-22s\033[0m %s\n" "make stop"             "Stop all containers"
	@echo ""
	@printf "  \033[35m%-22s\033[0m %s\n" "make install"          "Install dependencies"
	@printf "  \033[35m%-22s\033[0m %s\n" "make install-dev"      "Install dev dependencies"
	@printf "  \033[35m%-22s\033[0m %s\n" "make deps"             "Check/verify dependencies"
	@printf "  \033[35m%-22s\033[0m %s\n" "make verify"           "Verify system setup"
	@printf "  \033[35m%-22s\033[0m %s\n" "make setup"            "First-time setup"
	@echo ""
	@printf "  \033[31m%-22s\033[0m %s\n" "make clean"            "Remove build artifacts"
	@printf "  \033[31m%-22s\033[0m %s\n" "make clean-data"       "Remove data files"
	@printf "  \033[31m%-22s\033[0m %s\n" "make clean-all"        "Remove everything (clean + data)"
	@echo ""
	@printf "  \033[34m%-22s\033[0m %s\n" "make health"           "Check system health"
	@printf "  \033[34m%-22s\033[0m %s\n" "make migrate"          "Run database migrations"
	@echo ""

# =============================================================================
# INSTALLATION
# =============================================================================

install:
	@echo "Installing AOS dependencies..."
	@if [ ! -f "$(ENV_FILE)" ]; then \
		echo "Creating .env from template..."; \
		$(CP) .env.example $(ENV_FILE); \
	fi
	$(PIP) install -r requirements.txt
	@echo "  [提示] pyproject.toml 仅描述最小内核(aos-kernel, stdlib-only)打包, 完整运行时依赖见 requirements.txt"

install-dev: install
	@echo "Installing dev dependencies..."
	$(PIP) install pytest pytest-cov

deps: SHELL := /bin/bash
deps:
	@echo "Verifying dependencies (对照 requirements.txt)..."
	@$(PY) -c "import fastapi, uvicorn, pydantic, sqlmodel, aiosqlite" 2>/dev/null && echo "  [OK] Core API dependencies" || echo "  [FAIL] Missing core API dependencies (pip install -r requirements.txt)"
	@$(PY) -c "import aos_mcp, ag2, litellm" 2>/dev/null && echo "  [OK] Agent/MCP/LLM plane" || echo "  [WARN] Agent/MCP/LLM plane not installed"
	@$(PY) -c "import chromadb" 2>/dev/null && echo "  [OK] ChromaDB" || echo "  [WARN] ChromaDB not installed"
	@$(PY) -c "import streamlit" 2>/dev/null && echo "  [OK] Streamlit" || echo "  [WARN] Streamlit not installed"
	@$(PY) -c "import pytest" 2>/dev/null && echo "  [OK] Pytest" || echo "  [WARN] Pytest not installed"
	@$(PY) -c "import requests; r=requests.get('http://localhost:11434', timeout=2)" 2>/dev/null && echo "  [OK] Ollama running" || echo "  [INFO] Ollama not running (optional)"

verify:
	@echo "Verifying AOS system setup..."
	@$(PY) scripts/verify_setup.py 2>/dev/null || echo "  Run 'make setup' to initialize the system"

setup: install
	@echo "Running first-time setup..."
	@$(MKDIR) -p data/sqlite data/chroma outputs logs
	@if [ ! -f "$(ENV_FILE)" ]; then $(CP) .env.example $(ENV_FILE); fi
	@echo "Setup complete. Edit $(ENV_FILE) with your API keys."

# =============================================================================
# DEVELOPMENT
# =============================================================================

dev:
	@echo "Starting AOS in development mode..."
	@$(PY) launch.py

# =============================================================================
# TESTING
# =============================================================================

test:
	@echo "Running unit tests..."
	@$(PY) -m pytest tests/ -v --tb=short -m "not integration and not e2e"

test-unit:
	@echo "Running unit tests..."
	@$(PY) -m pytest tests/ -v --tb=short -m "unit"

test-integration:
	@echo "Running integration tests..."
	@$(PY) -m pytest tests/ -v --tb=short -m "integration"

test-all:
	@echo "Running all tests with coverage..."
	@$(PY) -m pytest tests/ -v --cov=src --cov-report=term-missing --cov-report=html --tb=short

coverage:
	@echo "Running tests with coverage report (terminal summary)..."
	@$(PY) -m pytest tests/ --cov=src --cov-report=term-missing --tb=short -q

test-watch:
	@echo "Running tests in watch mode..."
	@$(PY) -m pytest tests/ -v --watch

# =============================================================================
# LINTING & CODE QUALITY
# =============================================================================

lint:
	@echo "Running ruff linter..."
	@$(PY) -m ruff check src/ tests/ --output-format=text

lint-fix:
	@echo "Auto-fixing linting issues..."
	@$(PY) -m ruff check src/ tests/ --fix --show-fixes

format:
	@echo "Formatting code..."
	@$(PY) -m ruff format src/ tests/

typecheck:
	@echo "Running mypy type checker..."
	@$(PY) -m mypy src/ --ignore-missing-imports

# 检测「同作用域内重复 def/class 定义」(Python 只会保留最后一个，静默遮蔽)
# 详见 scripts/check_ast_duplicates.py
check-ast:
	@echo "Checking for duplicate method/function definitions (AST)..."
	@$(PY) scripts/check_ast_duplicates.py src

# 综合静态检查：ruff + AST 重复定义
check: lint check-ast
	@echo "All static checks passed."

# 轻量数据库层 smoke test：只需 sqlmodel + pydantic-settings，不依赖完整 AOS 依赖
# (brain/skills/chromadb 等)。可脱离 conftest 的 reset_singletons 直接验证 38 表 / ORM /
# persistence_bridge / memory FTS / meta_orchestrator 落库 / AST 检测全链路。
smoke:
	@echo "Running database-layer smoke test (no full AOS deps required)..."
	@$(PY) scripts/verify_db_layer.py

# 从 SQLModel 模型内省重新生成 docs/DATABASE_SCHEMA.md (修改模型后重跑以保持一致)
schema:
	@echo "Generating database schema doc from SQLModel metadata..."
	@$(PY) scripts/gen_schema_doc.py

# =============================================================================
# DOCKER BUILD
# =============================================================================

build:
	@echo "Building Docker image: $(IMAGE_FULL)"
	$(DOCKER) build -t $(IMAGE_FULL) --target production .

build-no-cache:
	@echo "Building Docker image (no cache): $(IMAGE_FULL)"
	$(DOCKER) build --no-cache -t $(IMAGE_FULL) --target production .

build-api:
	@echo "Building API-only image..."
	$(DOCKER) build -t $(IMAGE_NAME)-api:$(IMAGE_TAG) --target production .

build-frontend:
	@echo "Building Web UI only..."
	$(DOCKER) build -t $(IMAGE_NAME)-web:$(IMAGE_TAG) --target production .

docker-build: build

# =============================================================================
# DOCKER RUN
# =============================================================================

run: build
	@echo "Starting AOS (API + Web UI)..."
	$(COMPOSE) --profile api --profile web up $(IMAGE_NAME)-api $(IMAGE_NAME)-web --remove-orphans

run-api: build
	@echo "Starting AOS API server..."
	$(COMPOSE) --profile api up aos-api --remove-orphans

run-web: build
	@echo "Starting AOS Web UI..."
	$(COMPOSE) --profile web up aos-web --remove-orphans

run-full: build
	@echo "Starting full AOS stack..."
	$(COMPOSE) --profile full up --remove-orphans

run-ollama:
	@echo "Starting with Ollama (local LLM)..."
	$(COMPOSE) --profile full up ollama --remove-orphans

stop:
	@echo "Stopping all AOS containers..."
	$(COMPOSE) --profile full stop

down:
	@echo "Stopping and removing all containers..."
	$(COMPOSE) --profile full down

restart: stop run

# =============================================================================
# HEALTH & STATUS
# =============================================================================

health:
	@echo "Checking AOS health..."
	@curl -sf http://localhost:8000/health > /dev/null 2>&1 && echo "  [OK] API server healthy" || echo "  [FAIL] API server not responding"
	@curl -sf http://localhost:8501 > /dev/null 2>&1 && echo "  [OK] Web UI healthy" || echo "  [WARN] Web UI not running"
	@curl -sf http://localhost:11434/api/tags > /dev/null 2>&1 && echo "  [OK] Ollama running" || echo "  [INFO] Ollama not running"

migrate:
	@echo "Running database migrations..."
	@$(PY) scripts/migrate.py 2>/dev/null || echo "  No migrations found or migration script not present"

# =============================================================================
# CLEANUP
# =============================================================================

clean:
	@echo "Cleaning build artifacts..."
	@find . -type d -name "__pycache__" -exec $(RMDIR) {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec $(RMDIR) {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec $(RMDIR) {} + 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec $(RMDIR) {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -exec $(DEL) {} + 2>/dev/null || true
	@find . -type f -name "*.pyo" -exec $(DEL) {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec $(RMDIR) {} + 2>/dev/null || true
	@$(DOCKER) system prune -f --filter "label=com.docker.compose.project=aos" 2>/dev/null || true
	@echo "  Clean complete."

clean-data:
	@echo "Cleaning data files..."
	@$(RMDIR) data/sqlite 2>/dev/null || true
	@$(RMDIR) data/chroma 2>/dev/null || true
	@$(RMDIR) data/chroma_test 2>/dev/null || true
	@$(RMDIR) data/cognee 2>/dev/null || true
	@$(RMDIR) outputs 2>/dev/null || true
	@$(RMDIR) logs 2>/dev/null || true
	@$(RMDIR) .pytest_cache 2>/dev/null || true
	@$(DOCKER) volume rm aos-postgres-data aos-redis-data 2>/dev/null || true
	@echo "  Data cleaned."

clean-all: clean clean-data

# =============================================================================
# DOCKER UTILITIES
# =============================================================================

docker-logs:
	@$(COMPOSE) --profile full logs -f

docker-logs-api:
	@$(COMPOSE) --profile full logs -f aos-api

docker-logs-web:
	@$(COMPOSE) --profile full logs -f aos-web

docker-ps:
	@$(COMPOSE) --profile full ps

docker-clean:
	@echo "Deep cleaning Docker resources..."
	$(DOCKER) system prune -af --filter "label=com.docker.compose.project=aos"
	$(DOCKER) volume prune -f

# =============================================================================
# PACKAGE
# =============================================================================

package:
	@echo "Building distribution packages..."
	$(PY) -m build

wheel:
	@echo "Building wheel..."
	$(PY) -m build --wheel

sdist:
	@echo "Building source distribution..."
	$(PY) -m build --sdist

# =============================================================================
# DEFAULT TARGET
# =============================================================================

.DEFAULT_GOAL := help
