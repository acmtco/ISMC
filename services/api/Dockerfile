FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY services ./services
COPY scripts ./scripts

RUN pip install --no-cache-dir .

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
