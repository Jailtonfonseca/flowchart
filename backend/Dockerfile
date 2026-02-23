FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY app ./app

# Expose port
EXPOSE 8000

# Environment variables (default, can be overridden)
ENV SERVER_SECRET_KEY=dev-secret-key-change-me-in-prod
ENV BACKEND_HOST=0.0.0.0
ENV BACKEND_PORT=8000

# Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
