FROM ghcr.io/astral-sh/uv:python3.12-trixie-slim

WORKDIR /app

RUN apt update -y && apt install ffmpeg -y

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN uv sync --locked --no-dev

CMD ["uv", "run", "botik"]
