import os
import pytest
import tempfile
from typing import Generator, Dict, Any

from src.core.cookie_manager import CookieManager
from src.core.cache import GalleryCache
from src.services.storage import R2StorageService
from src.services.pdf import PDFService
from src.services.gallery import GalleryService
from src.config.settings import Settings

@pytest.fixture
def temp_cache_dir() -> Generator[str, None, None]:
    """Fixture to create a temporary cache directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def gallery_cache(temp_cache_dir: str) -> GalleryCache:
    """Fixture to create a gallery cache instance"""
    return GalleryCache(cache_dir=temp_cache_dir)

@pytest.fixture
def cookie_manager(mocker) -> CookieManager:
    """Fixture to create a mocked cookie manager"""
    manager = CookieManager()
    # Mock the session to avoid real requests
    mocker.patch.object(manager, 'session')
    manager.session.get.return_value.status_code = 200
    return manager

@pytest.fixture
def mock_r2_client(mocker):
    """Fixture to create a mocked R2 client"""
    mock_client = mocker.MagicMock()
    mocker.patch('boto3.client', return_value=mock_client)
    return mock_client

@pytest.fixture
def storage_service(mock_r2_client) -> R2StorageService:
    """Fixture to create a storage service with mocked R2 client"""
    # Mock R2 configuration
    Settings.R2_ACCOUNT_ID = "test_account"
    Settings.R2_ACCESS_KEY_ID = "test_key"
    Settings.R2_SECRET_ACCESS_KEY = "test_secret"
    Settings.R2_BUCKET_NAME = "test_bucket"
    Settings.R2_PUBLIC_URL = "https://test.com"
    
    return R2StorageService()

@pytest.fixture
def pdf_service(storage_service: R2StorageService) -> PDFService:
    """Fixture to create a PDF service"""
    return PDFService(storage_service)

@pytest.fixture
def gallery_service(
    cookie_manager: CookieManager,
    gallery_cache: GalleryCache,
    pdf_service: PDFService,
    storage_service: R2StorageService
) -> GalleryService:
    """Fixture to create a gallery service with all dependencies"""
    return GalleryService(
        cookie_manager=cookie_manager,
        gallery_cache=gallery_cache,
        pdf_service=pdf_service,
        storage_service=storage_service
    )

@pytest.fixture
def sample_gallery_data() -> Dict[str, Any]:
    """Fixture providing sample gallery data"""
    return {
        "id": 123456,
        "media_id": "test_media",
        "images": {
            "cover": {
                "url": "https://t.test.com/cover.jpg",
                "w": 350,
                "h": 500
            },
            "pages": [
                {
                    "url": "https://t.test.com/1.jpg",
                    "w": 1200,
                    "h": 1800
                },
                {
                    "url": "https://t.test.com/2.jpg",
                    "w": 1200,
                    "h": 1800
                }
            ]
        }
    } 