# lastunit

Flash-sale service: a shop lists a batch of goods at a special price for a
short window and there are more buyers than stock. Spec: `docs/acceptance.md`.
Plan: `docs/plan.md`. Status: scaffold, no product code yet.

## Run locally

```bash
make install   # creates .env with generated secrets, then installs backend and frontend deps
make up        # docker compose: db + backend + frontend
```

`.env` is never committed and has no default password: `make env` generates the
secrets, and `docker compose` refuses to start without them.
