import logging
from flask import Flask
from typing import Optional

from src.config.settings import Settings
from src.core.cookie_manager import CookieManager
from src.core.cache import GalleryCache
from src.services.storage import R2StorageService
from src.services.pdf import PDFService
from src.services.gallery import GalleryService
from src.api.routes import api_bp, docs_bp, init_routes

logger = logging.getLogger(__name__)

def create_app(gallery_service: Optional[GalleryService] = None) -> Flask:
    """
    Create and configure the Flask application
    
    Args:
        gallery_service: Optional gallery service instance for testing
    
    Returns:
        Flask: Configured Flask application
    """
    # Initialize Flask app
    app = Flask(__name__)
    
    # Configure app
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max-length
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
    
    try:
        if gallery_service is None:
            # Initialize services
            # Core services
            cookie_manager = CookieManager()
            gallery_cache = GalleryCache()
            
            # Optional services
            storage_service: Optional[R2StorageService] = None
            pdf_service: Optional[PDFService] = None
            
            # Initialize R2 storage if configured
            if Settings.is_r2_configured():
                try:
                    storage_service = R2StorageService()
                    pdf_service = PDFService(storage_service)
                    logger.info("R2 storage and PDF service initialized")
                except Exception as e:
                    logger.error(f"Failed to initialize R2 services: {str(e)}")
            
            # Initialize gallery service
            gallery_service = GalleryService(
                cookie_manager=cookie_manager,
                gallery_cache=gallery_cache,
                pdf_service=pdf_service,
                storage_service=storage_service
            )
        
        # Initialize routes
        init_routes(gallery_service)
        
        # Register blueprints
        app.register_blueprint(api_bp)
        app.register_blueprint(docs_bp)
        
        logger.info("Application initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")
        raise
    
    return app

def run_app():
    """Run the Flask application"""
    app = create_app()
    app.run(
        host="0.0.0.0",
        port=Settings.PORT,
        debug=Settings.DEBUG,
        threaded=True
    )

if __name__ == "__main__":
    run_app() 