FROM python:3.9-slim

# Install dependencies for Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    xvfb \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install specific version of Chrome (131.0.6778.204)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable=131.0.6778.204-1 \
    && apt-mark hold google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create cache directory with proper permissions
RUN mkdir -p cache && chmod 777 cache
RUN mkdir -p gallery_cache && chmod 777 gallery_cache

# Generate Swagger UI documentation
RUN python generate_swagger_ui.py

# Use PORT environment variable from Render.com
ENV PORT=5000
# Update Chrome paths and version
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROME_PATH=/usr/bin/google-chrome
ENV CHROME_VERSION=131.0.6778.204
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