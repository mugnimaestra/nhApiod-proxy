# nhApiod-proxy

A high-performance proxy service for nhentai with PDF generation capabilities and CDN support.

## Features

- 🚀 High-performance gallery data fetching
- 📄 Automatic PDF generation with background processing
- 💾 Intelligent caching system
- ☁️ Optional R2 storage integration for CDN delivery
- 🔒 Cloudflare challenge handling
- 🌐 RESTful API with OpenAPI documentation

## Architecture

The application follows a clean architecture pattern with the following components:

```
src/
├── api/              # API routes and response handling
├── config/           # Configuration management
├── core/             # Core components (cache, cookies)
├── services/         # Business logic services
└── utils/           # Utility functions
```

### Key Components

- **Gallery Service**: Handles gallery data fetching and processing
- **PDF Service**: Manages PDF generation and status tracking
- **Storage Service**: Handles R2 storage operations (optional)
- **Cache System**: Efficient gallery data caching
- **Cookie Manager**: Handles session management and Cloudflare challenges

## Setup

### Prerequisites

- Python 3.8+
- virtualenv (recommended)
- R2 Storage (optional)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/nhApiod-proxy.git
   cd nhApiod-proxy
   ```

2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

### Configuration

The following environment variables are supported:

```env
PORT=5001                      # Application port
DEBUG=false                    # Debug mode
CLOUDSCRAPER_DELAY=0.1        # Delay between requests
CLOUDSCRAPER_RETRIES=3        # Max retry attempts

# R2 Storage (optional)
CF_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_key_id
R2_SECRET_ACCESS_KEY=your_secret
R2_BUCKET_NAME=your_bucket
R2_PUBLIC_URL=your_public_url
```

## Usage

### Running the Application

```bash
python -m src.app
```

### API Endpoints

- `GET /health-check` - Service health check
- `GET /get?id={gallery_id}` - Get gallery data
- `GET /pdf-status/{gallery_id}` - Check PDF generation status
- `GET /docs` - API documentation

### API Documentation

The API documentation is available at `/docs` when the service is running. The OpenAPI specification is available at `/openapi.json`.

## Development

### Running Tests

```bash
pytest
```

### Code Style

The project follows PEP 8 guidelines. Use `black` for code formatting:

```bash
black src/
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
