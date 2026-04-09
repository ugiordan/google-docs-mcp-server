FROM registry.access.redhat.com/ubi9/python-312@sha256:4837df9a6d7b26fb86f2989157bd5f7b77a5510207ef48038ab0679cfd9882d1

USER 0
COPY --from=ghcr.io/astral-sh/uv:0.7.8@sha256:f81058a76ddb615ee220df733b982091565707a5813f581f2cbe8c10551e5c9e /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

WORKDIR /app
COPY pyproject.toml uv.lock main.py /app/
COPY mcp_server/ /app/mcp_server/

RUN --mount=type=cache,target=/root/.cache/uv \
    UV_PROJECT_ENVIRONMENT=/opt/app-root \
    uv sync --frozen --no-dev

RUN chown -R 1001:0 /app /opt/app-root && chmod -R g=u /app /opt/app-root

USER 1001
ENTRYPOINT ["python3.12", "main.py"]
