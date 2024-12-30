FROM python:3.9-slim

# Install system dependencies required for headless operation
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create cache directory with proper permissions
RUN mkdir -p cache && chmod 777 cache
RUN mkdir -p gallery_cache && chmod 777 gallery_cache

# Use PORT environment variable from Render.com
ENV PORT=5000
# Set Chrome to run in no-sandbox mode (required for containerized environment)
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_PATH=/usr/lib/chromium/
ENV CHROME_DRIVER_PATH=/usr/bin/chromedriver
ENV NO_SANDBOX=true
ENV DISPLAY=:99

# R2 Configuration (to be provided at runtime)
ENV CF_ACCOUNT_ID=""
ENV R2_ACCESS_KEY_ID=""
ENV R2_SECRET_ACCESS_KEY=""
ENV R2_BUCKET_NAME=""
ENV R2_PUBLIC_URL=""

# Add a non-root user
RUN useradd -m myuser && chown -R myuser:myuser /app
USER myuser

EXPOSE $PORT

# Use gunicorn with proper settings for production
CMD xvfb-run --server-args="-screen 0 1280x1024x24" gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 wbs-apiod:app 