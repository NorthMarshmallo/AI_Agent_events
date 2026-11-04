# MCP-сервер слоя свежих знаний. Зависимости ставятся из uv.lock, версии образов закреплены.
FROM ghcr.io/astral-sh/uv:0.12.13 AS uv

FROM python:3.13.9-slim
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY events_agent ./events_agent
COPY data ./data
RUN uv sync --frozen --no-dev && useradd --uid 1000 --no-create-home agent
USER agent
ENV HOST=0.0.0.0 PORT=8090 KB_BASE=full
EXPOSE 8090 8091
CMD ["/opt/venv/bin/python", "-m", "events_agent.mcp_server.server"]
