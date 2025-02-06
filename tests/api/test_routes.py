import pytest
from typing import Dict, Any
from flask import Flask
from flask.testing import FlaskClient

from src.app import create_app
from src.services.gallery import GalleryService
from src.api.routes import init_routes, api_bp, docs_bp

# Test cases for gallery endpoint
gallery_endpoint_cases = [
    pytest.param(
        "/get?id=123456",
        200,
        {"id": 123456, "media_id": "test", "images": {"pages": []}, "pdf_status": "processing"},
        id="valid_gallery_id"
    ),
    pytest.param(
        "/get?id=-1",
        400,
        {"status": False, "reason": "Invalid gallery ID"},
        id="invalid_gallery_id"
    ),
    pytest.param(
        "/get",
        400,
        {"status": False, "reason": "Invalid or missing gallery ID"},
        id="missing_gallery_id"
    ),
    pytest.param(
        "/get?id=abc",
        400,
        {"status": False, "reason": "Invalid or missing gallery ID"},
        id="non_numeric_gallery_id"
    )
]

@pytest.fixture
def app(gallery_service: GalleryService, mocker) -> Flask:
    """Create Flask application for testing"""
    # Mock the gallery service responses
    def mock_get_gallery(gallery_id: int, check_status: bool = False) -> tuple:
        if gallery_id <= 0:
            return {"status": False, "reason": "Invalid gallery ID"}, 400
        return {
            "id": gallery_id,
            "media_id": "test",
            "images": {"pages": []},
            "pdf_status": "processing"
        }, 200
    
    mocker.patch.object(gallery_service, 'get_gallery', side_effect=mock_get_gallery)
    
    # Create app using factory function
    app = create_app(gallery_service)
    app.config['TESTING'] = True
    
    return app

@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create test client"""
    return app.test_client()

@pytest.mark.parametrize("endpoint,status_code,expected_response", gallery_endpoint_cases)
def test_gallery_endpoint(
    client: FlaskClient,
    endpoint: str,
    status_code: int,
    expected_response: Dict[str, Any]
) -> None:
    """Test gallery endpoint with different scenarios"""
    response = client.get(endpoint)
    assert response.status_code == status_code
    if status_code == 200:
        assert response.json == expected_response
    else:
        assert response.json == expected_response

def test_health_check(client: FlaskClient, gallery_service: GalleryService, mocker) -> None:
    """Test health check endpoint"""
    # Mock cookie manager's ensure_valid_cookies to return True
    mocker.patch.object(
        gallery_service.cookie_manager,
        'ensure_valid_cookies',
        return_value=True
    )
    
    response = client.get("/health-check")
    assert response.status_code == 200
    assert response.json["status"] is True
    assert response.json["data"]["service"] == "nhApiod-proxy"
    assert "timestamp" in response.json["data"]
    assert response.json["data"]["cookies_ok"] is True

def test_pdf_status_endpoint(
    client: FlaskClient,
    gallery_service: GalleryService,
    sample_gallery_data: Dict[str, Any],
    mocker
) -> None:
    """Test PDF status endpoint"""
    gallery_id = sample_gallery_data['id']

    # Mock gallery service get_gallery method
    mocker.patch.object(
        gallery_service,
        'get_gallery',
        return_value=({
            "status": True,
            "pdf_status": "processing"
        }, 200)
    )

    # Check status
    response = client.get(f"/pdf-status/{gallery_id}")
    assert response.status_code == 200
    assert response.json["status"] is True
    assert response.json["pdf_status"] == "processing"

def test_invalid_endpoint(client: FlaskClient) -> None:
    """Test invalid endpoint handling"""
    response = client.get("/invalid")
    assert response.status_code == 404
    assert response.json == {
        "status": False,
        "reason": "Resource not found"
    }

@pytest.mark.skip(reason="Documentation endpoints require static files")
def test_docs_endpoint(client: FlaskClient) -> None:
    """Test documentation endpoints"""
    # Test Swagger UI
    response = client.get("/docs")
    assert response.status_code == 200
    assert b"swagger" in response.data.lower()
    
    # Test OpenAPI spec
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "openapi" in response.json 