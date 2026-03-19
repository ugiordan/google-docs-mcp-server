FROM registry.access.redhat.com/ubi9/python-312

USER 0
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

WORKDIR /app
COPY . /app

RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /usr/bin/python3.12 \
    --target /opt/app-root/lib/python3.12/site-packages \
    -r pyproject.toml

RUN chown -R 1001:0 /app /opt/app-root && chmod -R g=u /app /opt/app-root

USER 1001
ENTRYPOINT ["python3.12", "main.py"]
