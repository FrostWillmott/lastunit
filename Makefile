.PHONY: help env install install-hooks seed check fix lint format typecheck test \
        test-unit test-integration \
        frontend-install frontend-check frontend-fix frontend-test frontend-build \
        audit docker-build up down pre-commit ci clean

# Frontend targets are no-ops when frontend/ is absent, so the same Makefile
# serves a backend-only project.
HAS_FRONTEND := $(wildcard frontend/package.json)

help:
	@echo "Project Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make env              - Create .env from .env.example with random secrets (no-op if present)"
	@echo "  make install          - make env, then backend deps (uv) and frontend deps (npm ci)"
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

# .env.example lists every variable; secrets are left empty there. This target
# copies it and fills each empty value with a random one, so a clean checkout
# runs with one command and never with a shared default password. An empty
# .env counts as missing. `sed -i.bak` works on both BSD and GNU sed.
env:
	@test -s .env || { \
	  cp .env.example .env; \
	  for key in $$(grep -E '^[A-Z_]+=$$' .env.example | cut -d= -f1); do \
	    sed -i.bak "s/^$$key=$$/$$key=$$(openssl rand -hex 24)/" .env; \
	  done; \
	  rm -f .env.bak; \
	  echo "Created .env from .env.example with generated secrets"; \
	}

install: env frontend-install
	uv sync --all-extras

# Create the demo shop user from SEED_SHOP_* in .env (idempotent). Like the
# integration conftest, derive DATABASE_URL from POSTGRES_* for the localhost DB.
seed:
	@set -a && . ./.env && set +a && \
	DATABASE_URL="postgresql+asyncpg://$${POSTGRES_USER:-app}:$${POSTGRES_PASSWORD}@localhost:5432/$${POSTGRES_DB:-app}" \
	uv run python -m app.seed

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

test: test-unit test-integration

test-unit:
	# --no-cov: unit tests run without a database, so their partial coverage of
	# `app` is not the number the threshold (on the integration suite) enforces.
	uv run pytest tests/unit -v --no-cov

test-integration:
	uv run pytest tests/integration -v

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

up: env
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
