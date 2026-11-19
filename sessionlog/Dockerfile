# Build from the repo root: docker build -f sessionlog/Dockerfile -t paddock-sessionlog:0.1.0 .
FROM python:3.12-slim
WORKDIR /app
COPY sessionlog/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sessionlog/sessionlog.py sessionlog/harness.py sessionlog/kagent_sync.py evals/mcp_client.py ./
RUN useradd --uid 10001 --no-create-home app
USER 10001
CMD ["python", "harness.py"]
