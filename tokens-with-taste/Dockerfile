FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY twt ./twt
COPY twt_service.py ./
RUN python -m venv /app/venv && /app/venv/bin/pip install --no-cache-dir -e .
EXPOSE 8000
ENTRYPOINT ["/app/venv/bin/python", "/app/twt_service.py", "--uds", "/run/twt/gateway.sock"]
