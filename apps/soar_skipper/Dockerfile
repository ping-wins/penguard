FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app/apps/soar_skipper

RUN pip install --no-cache-dir uv==0.11.7

COPY apps/soar_skipper/pyproject.toml apps/soar_skipper/uv.lock ./
RUN uv sync --frozen --no-dev

COPY apps/soar_skipper/app ./app

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
