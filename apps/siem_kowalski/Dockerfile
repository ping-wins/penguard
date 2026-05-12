FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app/apps/siem_kowalski

RUN pip install --no-cache-dir uv==0.11.7

COPY apps/siem_kowalski/pyproject.toml apps/siem_kowalski/uv.lock ./
RUN uv sync --frozen --no-dev

COPY apps/siem_kowalski/app ./app

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
