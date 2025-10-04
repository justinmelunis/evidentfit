FROM python:3.11-slim

WORKDIR /app

# Copy shared library
COPY ../shared/ /opt/shared/
RUN pip install -e /opt/shared

# Copy banking agent files
COPY . .

# Install dependencies
RUN pip install -r requirements.txt

# Set environment variables
ENV PYTHONPATH=/app:/opt/shared
ENV BANKING_CACHE_DIR=/app

# Default command
CMD ["python", "run_banking_init.py"]
