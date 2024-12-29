FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create cache directory
RUN mkdir -p cache && chmod 777 cache

# Use PORT environment variable from Render.com
ENV PORT=5000
EXPOSE $PORT

# Use gunicorn with proper settings for production
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 wbs-apiod:app 