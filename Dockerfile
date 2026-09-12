# Backend image. Base pinned by digest (dependency-hygiene audit: floating tags
# drift silently). Refresh with:
#   curl -s https://hub.docker.com/v2/repositories/library/python/tags/3.12-slim | jq .digest
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6

# uv, pinned. Copying the binary from the official image avoids a curl|sh step.
COPY --from=ghcr.io/astral-sh/uv:0.12.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1

# Dependencies first so the layer caches; --locked fails the build if uv.lock
# is out of date instead of silently resolving something else.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . .
RUN uv sync --locked

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# Run migrations before the app so `make up` from a clean .env works.
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
# Host/port are the container contract; anything configurable is read from env
# by the app itself (see .env.example), not overridden here.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
