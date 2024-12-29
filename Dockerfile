FROM python:3.9-slim

# Install system dependencies required for headless operation
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create cache directory with proper permissions
RUN mkdir -p cache && chmod 777 cache

# Use PORT environment variable from Render.com
ENV PORT=5000
# Set Chrome to run in no-sandbox mode (required for containerized environment)
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_PATH=/usr/lib/chromium/
ENV CHROME_DRIVER_PATH=/usr/bin/chromedriver
ENV NO_SANDBOX=true

EXPOSE $PORT

# Use gunicorn with proper settings for production
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 wbs-apiod:app 