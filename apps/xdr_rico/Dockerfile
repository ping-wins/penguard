FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app/apps/xdr_rico

RUN pip install --no-cache-dir uv==0.11.7

COPY apps/xdr_rico/pyproject.toml apps/xdr_rico/uv.lock ./
RUN uv sync --frozen --no-dev

COPY apps/xdr_rico/app ./app

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
