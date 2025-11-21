FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Minimal build tools if some libs need compiling
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the whole InsightViewer project (app/, config.ini, etc.)
COPY . .

# InsightViewer Flask app listens on 5000 inside the container
EXPOSE 5000

# Main entrypoint: run your Flask app
CMD ["python", "app/app.py"]

