.PHONY: help install install-hooks check fix lint format typecheck test \
        frontend-install frontend-check frontend-fix frontend-test frontend-build \
        audit docker-build up down pre-commit ci clean

# Frontend targets are no-ops when frontend/ is absent, so the same Makefile
# serves a backend-only project.
HAS_FRONTEND := $(wildcard frontend/package.json)

help:
	@echo "Project Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          - Install backend deps (uv) and frontend deps (npm ci)"
	@echo "  make install-hooks    - Install pre-commit hooks"
	@echo "  make up / make down   - Start / stop the local stack (docker compose)"
	@echo ""
	@echo "Code Quality (make check runs ALL of these — run before finishing any task):"
	@echo "  make check            - backend lint + format + types + tests, then frontend-check"
	@echo "  make fix              - Auto-fix lint/format issues (backend + frontend)"
	@echo "  make lint / format / typecheck / test - individual backend checks"
	@echo "  make frontend-check   - frontend lint + format + types + tests"
	@echo "  make frontend-build   - production build of the frontend"
	@echo "  make audit            - known-vulnerability scan (uv audit + npm audit)"
	@echo "  make docker-build     - build all images (no push)"
	@echo "  make pre-commit       - Run all pre-commit hooks"
	@echo "  make ci               - Everything CI runs, locally"

install: frontend-install
	uv sync --all-extras

install-hooks:
	uv run pre-commit install

check: lint format typecheck test frontend-check

fix: frontend-fix
	uv run ruff check --fix .
	uv run ruff format .

lint:
	uv run ruff check .

format:
	uv run ruff format --check .

typecheck:
	uv run mypy .

test:
	uv run pytest tests/ -v

# ---- frontend -------------------------------------------------------------
frontend-install:
ifneq ($(HAS_FRONTEND),)
	cd frontend && npm ci --ignore-scripts
endif

frontend-check:
ifneq ($(HAS_FRONTEND),)
	cd frontend && npm run lint && npm run format:check && npm run typecheck && npm run test:coverage
endif

frontend-fix:
ifneq ($(HAS_FRONTEND),)
	cd frontend && npm run format
endif

frontend-test:
ifneq ($(HAS_FRONTEND),)
	cd frontend && npm run test
endif

frontend-build:
ifneq ($(HAS_FRONTEND),)
	cd frontend && npm run build
endif

# ---- supply chain / containers --------------------------------------------
# `uv audit` (uv >= 0.12, preview) queries OSV against uv.lock directly — no
# export, no second tool. The version guard gives a clear message instead of
# "unrecognized subcommand" on an old uv.
audit:
	@uv audit --help >/dev/null 2>&1 || { echo "make audit needs uv >= 0.12 — run: uv self update"; exit 1; }
	uv audit --locked --no-dev --preview-features audit-command
ifneq ($(HAS_FRONTEND),)
	cd frontend && npm audit --audit-level=high
endif

docker-build:
	docker compose build

up:
	@test -f .env || cp .env.example .env
	docker compose up --build -d

down:
	docker compose down

pre-commit:
	uv run pre-commit run --all-files

ci: check frontend-build audit
	@echo "All CI checks passed!"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	rm -rf frontend/dist frontend/coverage
