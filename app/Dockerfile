FROM ghcr.io/astral-sh/uv:python3.15-alpine

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

RUN uv sync --locked --no-dev

COPY . .

CMD ["uv", "run", "botik"]
