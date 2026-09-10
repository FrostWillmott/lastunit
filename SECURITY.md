# Security policy

## Reporting a vulnerability

Do not open a public issue. Email the maintainer listed in `pyproject.toml`
(or the repository owner) with a description and reproduction steps. You will
get an acknowledgement within 7 days.

## Scope

- Backend API, frontend, CI workflows, and container images in this repo.
- Out of scope: third-party services this project only calls.

## What we do on our side

- Dependencies are locked (`uv.lock`, `frontend/package-lock.json`) and
  audited in CI (`make audit`).
- Secrets never enter git: `.env` is ignored, `gitleaks` runs at pre-commit.
- CI workflows run with read-only token permissions and pinned action SHAs.
