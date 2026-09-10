---
name: workflow-scaffolding
description: Set up verification tooling for a new client-server project — linters,
  formatters, type checkers, tests with thresholds, pre-commit, Makefile, CI, containers,
  and the repository settings audits look for (branch protection, first green run).
when_to_use: starting a new project, scaffold tooling, add pre-commit hooks, new repository
  setup, project lacks linter or type checker, missing Makefile or CI configuration,
  enable branch protection, first push to GitHub
---

# Scaffold project verification tooling

When a repo lacks verification infrastructure, set it up before feature work. Ask before
adding anything heavy. Infer specifics from the stack — don't cargo-cult the template if
the project already has conventions (see `inherited-codebases.md`: find the existing
mechanism first, never shadow it).

## Enforcement hierarchy (strongest first)

Branch protection > CI > pre-commit hooks > `make check` > rules in `.claude/rules/` > prose

Push every rule as high as it goes. A check that only exists in CLAUDE.md prose will
eventually be skipped; a CI check that isn't *required* on `main` is advisory.

## Steps

The template already ships the files; the steps are what to fill in and verify.

1. **Backend toolchain** — `ruff.toml` (standalone, `select` not `extend-select`,
   `target-version` explicit — already in the template), `mypy` strict in
   `pyproject.toml`:
   ```toml
   [tool.mypy]
   strict = true

   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   addopts = "--cov=app --cov-fail-under=70"   # start where the first real suite lands
   ```
   Commit `uv.lock`; CI installs with `uv sync --locked`.

2. **Frontend toolchain** — `frontend/` in the template is a verified Vite + Vue 3 +
   TypeScript skeleton: ESLint 9 with `eslint-plugin-vue` (template rules included),
   Prettier, `vue-tsc`, Vitest + `@vue/test-utils` (+ coverage threshold in
   `vite.config.ts`) and `npm run check`. Keep the scripts' names: `make check` and CI
   call them. If the project must use React, regenerate with `npm create vite@latest
   frontend -- --template react-ts` and port `package.json` scripts, `.prettierrc`,
   `vite.config.ts` (test + proxy + `sourcemap: false`) and the `App` test over; drop
   `frontend-vue.md` from `.claude/rules/`.

3. **Pre-commit** — `.pre-commit-config.yaml` ships ruff, mypy, gitleaks and a
   frontend lint hook scoped to `frontend/`. Run `pre-commit autoupdate`, then
   `make install-hooks`. Tests stay in CI, not in pre-commit.

4. **Makefile** — `make check` must cover every surface (backend + frontend);
   `make audit` runs `uv audit` + `npm audit` (needs uv >= 0.12); `make up` starts the compose stack.
   Tell the user to run `make install && make install-hooks` once.

5. **Containers** — `Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml` are in
   the template with base images pinned by digest. Refresh digests when bumping a
   tag (command in each Dockerfile's header). `make docker-build` must pass before
   the first push; CI runs it.

6. **Configuration contract** — copy `.env.example`, make the Settings class match it
   field for field, and add the env-contract test (`config-hygiene.md`). Do this
   before the first feature: retrofitting it is what config audits penalise.

7. **CI** — `.github/workflows/ci.yml` runs backend, frontend, audit and docker jobs
   with `permissions: contents: read` and actions pinned by SHA. When bumping an
   action, pin the new SHA and keep the version in the trailing comment:
   `git ls-remote --tags https://github.com/<owner>/<action> | grep 'v<X.Y.Z>'`.
   If tests need Postgres, uncomment the `services:` block. `.github/dependabot.yml`
   refreshes those SHA pins, image digests and both lockfiles weekly — it maintains
   the pins, the `audit` job is still the gate.

8. **Repository settings (GitHub)** — files can't do these; do them right after the
   first push, they are what a CI/CD audit scores first:
   - Push the scaffold *before* feature code so Actions registers a green run on
     `main` immediately.
   - Branch protection on `main` (Settings → Branches, or `gh api`): require status
     checks `backend`, `frontend`, `audit`, `docker`; require PRs (self-merge is
     fine for a solo repo); block force-push.
   - Leave Issues enabled (auditors read them for intent); add `SECURITY.md`
     contact.

9. **Documentation files** — fill the TODOs in `CLAUDE.md` and `README.md` (the
   required sections from `documentation.md`), start `DECISIONS.md` with the stack
   choice, and commit.

## Path-scoped rules

After copying rule modules into `.claude/rules/`, add `paths:` frontmatter to modules
that only apply to part of the codebase — e.g. `frontend-vue.md` scoped to
`frontend/**`, `transactional-web.md` left global (it covers the whole request path).
