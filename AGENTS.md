# AOS v5.0 Agent Team Setup
# This file defines the AI agent team that works on this codebase.
# It is consumed by OpenCode/Codex/Cursor/Aider/Devin/Gemini CLI and similar tools.

version: "1"
name: aos-agent-team
description: >
  AOS (Agent Operating System) v5.0 -- A multi-agent AI system combining
  Hermes Agent (NousResearch) for chat/reasoning and DeerFlow (ByteDance)
  for workflow orchestration. Built with FastAPI, Streamlit, LangGraph,
  ChromaDB, and 25+ integrated skills.

# =============================================================================
# PROJECT CONTEXT
# =============================================================================

project:
  type: python
  language: python
  min_python: "3.10"
  package_dir: src
  test_framework: pytest
  linter: ruff
  formatter: ruff format
  type_checker: mypy

# =============================================================================
# CODE CONVENTIONS
# =============================================================================

conventions:
  style_guide: PEP 8 + Google docstrings
  line_length: 120
  import_order: stdlib, third_party, local
  max_function_length: 100
  max_module_length: 500

  naming:
    classes: PascalCase
    functions: snake_case
    constants: UPPER_SNAKE_CASE
    private: _leading_underscore
    protected: __double_underscore

  patterns:
    - Use dataclasses for simple data structures
    - Use Pydantic for validated models (API schemas, config)
    - Use ABC for abstract base classes
    - Use Protocol for structural typing
    - Singleton pattern: use module-level _instance with get_X() factory
    - Error handling: log at WARNING level, never crash silently

  forbidden:
    - exec() / eval() with user input
    - Hardcoded credentials or secrets
    - Blocking operations in async context
    - print() for logging (use logging module)
    - Mutable default arguments
    - Importing from src inside __init__.py (circular deps)

# =============================================================================
# ARCHITECTURE ROLES
# =============================================================================

roles:
  orchestrator:
    name: Mavis
    role: Root orchestrator
    description: >
      Coordinates all sub-agents, manages task routing, handles user
      communication, ensures quality gate at every handoff.
    instructions:
      - Break complex tasks into subtasks for specialists
      - Always verify before reporting completion
      - Use the todo list for tasks with 3+ steps
      - For code changes, check neighboring files first
      - Never leave the codebase in a broken state

  backend-dev:
    name: Backend Dev
    role: Python/FastAPI specialist
    description: >
      Handles API design, database operations, business logic,
      integration with external frameworks (Hermes, DeerFlow).
    instructions:
      - Follow FastAPI best practices (dependency injection, schemas)
      - Use Pydantic for all API request/response models
      - Write async code properly (no blocking in async functions)
      - Add proper error handling with HTTPException
      - Document all endpoints with docstrings
    tools:
      - read, write, edit, grep, glob
      - bash (for running tests, servers)
    files:
      - src/api/**/*
      - src/core/**/*
      - src/deerflow/**/*
      - src/hermes/**/*
      - src/memory/**/*
      - src/execution/**/*

  skills-dev:
    name: Skills Dev
    role: Skill system specialist
    description: >
      Implements and maintains the 25+ AOS skills, skill registry,
      skill composition, and skill marketplace.
    instructions:
      - Follow the Skill base class pattern (src/skills/base.py)
      - Each skill needs: name, description, category, _execute_impl
      - Register skills in src/skills/__init__.py
      - Add tests for new skills in tests/test_skills.py
    tools:
      - read, write, edit, glob, grep
    files:
      - src/skills/**/*
      - tests/test_skills.py

  frontend-dev:
    name: Frontend Dev
    role: Streamlit UI specialist
    description: >
      Maintains the Streamlit web interface, UI components,
      page layouts, and user experience.
    instructions:
      - Follow Streamlit patterns from existing pages
      - Use session_state for state management
      - Handle API errors gracefully with try/except
      - Keep pages focused and well-organized
    tools:
      - read, write, edit, glob
    files:
      - src/web/**/*

  compliance-dev:
    name: Compliance Dev
    role: Audit, identity, and tracing specialist
    description: >
      Maintains GB/Z 185-2026 compliant audit logging, identity
      management, and distributed tracing.
    instructions:
      - All significant operations must be audited
      - Use AuditEvent enum for event types
      - Identity AID format: "aos-{role}-{random}"
      - Trace spans for cross-component operations
    tools:
      - read, write, edit
    files:
      - src/compliance/**/*

  test-dev:
    name: Test Dev
    role: Testing specialist
    description: >
      Writes and maintains unit tests, integration tests,
      and end-to-end tests. Ensures code quality.
    instructions:
      - All new features need tests
      - Use pytest fixtures from conftest.py
      - Mock external dependencies (API calls, file I/O)
      - Aim for 80%+ coverage on core modules
    tools:
      - read, write, bash (pytest)
    files:
      - tests/**/*
      - pytest.ini
      - conftest.py

  infra-dev:
    name: Infra Dev
    role: DevOps / Infrastructure specialist
    description: >
      Maintains Docker, docker-compose, CI/CD, deployment configs,
      and system-level dependencies.
    instructions:
      - Multi-stage Dockerfile (builder + production)
      - Health checks on all services
      - Resource limits in docker-compose
      - Use Makefile for common operations
    tools:
      - read, write, bash (docker, docker compose)
    files:
      - Dockerfile
      - docker-compose.yml
      - Makefile
      - configs/**/*

# =============================================================================
# TASK ROUTING
# =============================================================================

routing:
  "API endpoint" / "REST" / "FastAPI" -> backend-dev
  "chat" / "conversation" / "Hermes" / "reasoning" -> backend-dev
  "skill" / "capability" / "tool" -> skills-dev
  "web UI" / "Streamlit" / "interface" / "page" -> frontend-dev
  "audit" / "identity" / "trace" / "compliance" -> compliance-dev
  "test" / "pytest" / "coverage" -> test-dev
  "Docker" / "docker" / "deploy" / "CI" / "infrastructure" -> infra-dev
  "memory" / "database" / "storage" -> backend-dev
  "config" / "settings" / ".env" -> backend-dev
  "read me" / "documentation" / "README" -> orchestrator
  "complex task" / "multi-step" / "large change" -> orchestrator

# =============================================================================
# QUALITY GATES
# =============================================================================

quality_gates:
  - name: lint
    command: ruff check src/ tests/
    pass_threshold: 0 errors (warnings allowed)

  - name: typecheck
    command: mypy src/ --ignore-missing-imports
    pass_threshold: 0 errors

  - name: tests
    command: pytest tests/ -v --tb=short
    pass_threshold: >80% pass rate

  - name: health
    command: curl -sf http://localhost:8000/health
    pass_threshold: HTTP 200 with status=healthy

# =============================================================================
# DEPENDENCY GRAPH
# =============================================================================

dependency_graph:
  src.api.main:
    depends_on: [src.core.brain, src.utils.config]
    imports: [src.mcp, src.router, src.api.security]

  src.core.brain:
    depends_on: [src.hermes.agent, src.deerflow.scheduler, src.memory.memory]
    imports: [src.skills, src.subagents, src.compliance, src.mcp]

  src.deerflow.scheduler:
    depends_on: [src.memory.memory]
    imports: [src.deerflow.deep_deerflow, src.deerflow.sandbox_bridge,
              src.deerflow.guardrails_bridge, src.deerflow.agents_bridge,
              src.deerflow.subagent_executor]

  src.hermes.agent:
    depends_on: [src.memory.memory, src.skills]
    imports: [src.router, src.hermes.deep_hermes]

  src.skills:
    depends_on: [src.memory.memory]
    imports: []

  src.web.app:
    depends_on: [src.core.brain]
    imports: [src.compliance.audit, src.utils.config]

  tests/:
    depends_on: [src/**/*]
    imports: []
