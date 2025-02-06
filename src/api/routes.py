import logging
from typing import Optional
from flask import Blueprint, request, send_from_directory
import yaml

from src.services.gallery import GalleryService
from src.api.responses import error_response, success_response, json_response, APIResponse

logger = logging.getLogger(__name__)

# Create blueprints
api_bp = Blueprint('api', __name__)
docs_bp = Blueprint('docs', __name__)

# Global service instance
_gallery_service: Optional[GalleryService] = None

def init_routes(gallery_service: GalleryService) -> None:
    """
    Initialize routes with required services
    
    Args:
        gallery_service: Gallery service instance
    """
    global _gallery_service
    _gallery_service = gallery_service

@api_bp.route("/", methods=["GET"])
def get_main():
    """Root endpoint"""
    return error_response("Resource not found", status=404)

@api_bp.route("/health-check", methods=["GET"])
def health_check():
    """Health check endpoint"""
    try:
        cookies_ok = _gallery_service.cookie_manager.ensure_valid_cookies()
        return success_response({
            "service": "nhApiod-proxy",
            "timestamp": _gallery_service.cookie_manager.last_renewal,
            "cookies_ok": cookies_ok
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return error_response(f"Health check failed: {str(e)}")

@api_bp.route("/get", methods=["GET"])
def get_data():
    """Get gallery data endpoint"""
    try:
        # Validate gallery ID
        try:
            gallery_id = int(request.args['id'])
        except (KeyError, ValueError, TypeError):
            return error_response(
                "Invalid or missing gallery ID",
                status=400
            )
        
        # Check if only status check is requested
        check_status = request.args.get('check_status', '').lower() == 'true'
        
        # Get gallery data
        data, status = _gallery_service.get_gallery(gallery_id, check_status)
        
        return json_response(data, status=status)
        
    except Exception as e:
        logger.error(f"Failed to get gallery data: {str(e)}")
        return error_response(str(e))

@api_bp.route("/pdf-status/<int:gallery_id>", methods=["GET"])
def check_pdf_status(gallery_id: int):
    """Check PDF processing status endpoint"""
    try:
        # Get gallery data with status check
        data, status = _gallery_service.get_gallery(gallery_id, check_pdf_status=True)
        return json_response(data, status=status)
        
    except Exception as e:
        logger.error(f"Failed to check PDF status: {str(e)}")
        return error_response(str(e))

@api_bp.errorhandler(404)
def not_found(e):
    """404 error handler"""
    return error_response("Resource not found", status=404)

@api_bp.route("/invalid", methods=["GET"])
def invalid_endpoint():
    """Invalid endpoint handler"""
    return error_response("Resource not found", status=404)

@docs_bp.route("/docs")
def api_docs():
    """Serve API documentation"""
    return send_from_directory('docs', 'swagger.html')

@docs_bp.route("/openapi.json")
def openapi_spec():
    """Serve OpenAPI specification"""
    try:
        with open('openapi.yaml', 'r', encoding='utf-8') as f:
            spec = yaml.safe_load(f)
        return success_response(spec)
    except Exception as e:
        logger.error(f"Failed to serve OpenAPI spec: {str(e)}")
        return error_response("Failed to load OpenAPI specification") 