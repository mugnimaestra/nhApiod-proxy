FROM python:3.9-slim

# Install dependencies for Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg2 \
    xvfb \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome using the recommended approach
RUN wget -q -O /tmp/chrome.key https://dl-ssl.google.com/linux/linux_signing_key.pub \
    && install -D /tmp/chrome.key /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && rm /tmp/chrome.key \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
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
# Update Chrome paths
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROME_PATH=/usr/bin/google-chrome
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