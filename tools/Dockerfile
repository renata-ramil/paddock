FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
# Running as a non-root user
RUN useradd --uid 10001 --no-create-home app
USER 10001
EXPOSE 8000
CMD ["python", "server.py"]
