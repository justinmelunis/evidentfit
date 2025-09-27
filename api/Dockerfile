FROM python:3.11-slim

# Prevent Python from writing .pyc files / buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install system deps (build tools for any wheels)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    rm -rf /var/lib/apt/lists/*

# Create app user & dirs
WORKDIR /app
RUN useradd -m appuser
COPY api/requirements.txt /app/requirements.txt

# Install Python deps
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy source
COPY api/ /app/

# Change ownership and drop root
RUN chown -R appuser:appuser /app
USER appuser

# Expose port and start
EXPOSE 8000
WORKDIR /app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
