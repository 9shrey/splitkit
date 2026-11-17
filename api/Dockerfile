FROM python:3.12-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.11.29 && uv sync --frozen --no-dev --no-install-project
COPY app ./app
RUN useradd --create-home app
USER app
ENV PATH=/app/.venv/bin:$PATH ENV=production
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
