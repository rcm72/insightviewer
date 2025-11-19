FROM python:3.12-slim

# Optional: minimal build tools if some libs need compiling
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first to leverage layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code + entrypoint
COPY app.py .
COPY run.sh .
RUN chmod +x /app/run.sh

EXPOSE 5000

# Single entry point that decides dev/prod at runtime
CMD ["/app/run.sh"]

