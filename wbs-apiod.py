from flask import Flask, send_from_directory
import os
import logging
import urllib3
from dotenv import load_dotenv
import yaml

# Import our refactored modules
from src.services.gallery import GalleryService
from src.services.pdf import PDFService
from src.services.storage import R2StorageService
from src.core.cookie_manager import CookieManager
from src.core.cache import GalleryCache
from src.api.routes import init_routes, api_bp, docs_bp
from src.config.settings import Settings

# Load environment variables from .env file in development
if os.path.exists('.env'):
    load_dotenv()

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def create_app() -> Flask:
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    # Configure Flask
    app.config.update({
        'SEND_FILE_MAX_AGE_DEFAULT': 0,
        'MAX_CONTENT_LENGTH': 100 * 1024 * 1024,  # 100MB max-length
        'JSONIFY_PRETTYPRINT_REGULAR': False,
        'DEBUG': Settings.DEBUG
    })
    
    # Initialize services
    cookie_manager = CookieManager()
    gallery_cache = GalleryCache(Settings.GALLERY_CACHE_DIR)
    
    # Initialize R2 storage if configured
    storage_service = R2StorageService() if Settings.is_r2_configured() else None
    
    pdf_service = PDFService(storage_service)
    gallery_service = GalleryService(
        cookie_manager=cookie_manager,
        gallery_cache=gallery_cache,
        storage_service=storage_service,
        pdf_service=pdf_service
    )
    
    # Initialize routes
    init_routes(gallery_service)
    app.register_blueprint(api_bp)
    app.register_blueprint(docs_bp)
    
    return app

if __name__ == "__main__":
    port = Settings.PORT
    app = create_app()
    app.run(
        host="0.0.0.0", 
        port=port,
        threaded=True
    )