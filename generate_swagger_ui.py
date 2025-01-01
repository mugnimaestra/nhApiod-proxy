import yaml
import os
from string import Template
from dotenv import load_dotenv

# Load environment variables
if os.path.exists('.env'):
    load_dotenv()

# Read OpenAPI spec
with open('openapi.yaml', 'r', encoding='utf-8') as f:
    spec = yaml.safe_load(f)

# Determine environment and set appropriate URL
IS_PRODUCTION = os.getenv('RENDER', '').lower() == 'true'
if IS_PRODUCTION:
    # In production, use the Render URL
    API_URL = os.getenv('RENDER_EXTERNAL_URL', 'https://nhApiod-proxy.onrender.com')
else:
    # In development, use local URL or custom API_URL
    API_URL = os.getenv('API_URL', 'http://localhost:5001')

# Update server URLs
if 'servers' in spec:
    # Keep localhost for development testing
    spec['servers'] = [
        {
            'url': API_URL,
            'description': 'Current environment'
        },
        {
            'url': 'http://localhost:5001',
            'description': 'Local development'
        }
    ]

# Convert spec to JSON string for embedding
import json
spec_json = json.dumps(spec)

# Swagger UI HTML template
TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="description" content="SwaggerUI" />
    <title>nhApiod-proxy API Documentation</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css" />
    <style>
        body {
            margin: 0;
            padding: 0;
        }
        #swagger-ui {
            max-width: 1460px;
            margin: 0 auto;
            padding: 20px;
        }
        .swagger-ui .topbar {
            display: none;
        }
        .download-url-wrapper {
            display: flex;
            align-items: center;
            margin: 1em 0;
        }
        .download-url-button {
            background-color: #4990e2;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            margin-left: 10px;
        }
        .download-url-button:hover {
            background-color: #357abd;
        }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js" crossorigin></script>
    <script>
        window.onload = () => {
            window.ui = SwaggerUIBundle({
                spec: $spec_json,
                dom_id: '#swagger-ui',
                deepLinking: true,
                defaultModelsExpandDepth: -1,
                displayRequestDuration: true,
                filter: true,
                withCredentials: true,
                persistAuthorization: true,
                tryItOutEnabled: true,
                supportedSubmitMethods: ['get', 'post'],
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
                plugins: [
                    SwaggerUIBundle.plugins.DownloadUrl
                ],
                urls: [
                    {
                        name: "OpenAPI Specification",
                        url: "./openapi.json"
                    }
                ],
                "urls.primaryName": "OpenAPI Specification"
            });
        };
    </script>
</body>
</html>
"""

# Generate HTML
html = Template(TEMPLATE).substitute(spec_json=spec_json)

# Create docs directory if it doesn't exist
os.makedirs('docs', exist_ok=True)

# Write HTML file
with open('docs/swagger.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"Swagger UI has been generated at docs/swagger.html")
print(f"Using API URL: {API_URL}")
print(f"Environment: {'Production' if IS_PRODUCTION else 'Development'}") 