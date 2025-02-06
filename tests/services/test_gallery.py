import pytest
from typing import Dict, Any, Tuple

from src.services.gallery import GalleryService

# Test cases for gallery data processing
process_gallery_data_cases = [
    pytest.param(
        {
            "id": 123,
            "media_id": "test",
            "images": {
                "cover": {"url": "https://t.test.com/cover.jpg"},
                "pages": [{"url": "https://t.test.com/1.jpg"}]
            }
        },
        {
            "id": 123,
            "media_id": "test",
            "images": {
                "cover": {
                    "url": "https://i.test.com/cover.jpg",
                    "cdn_url": "https://test.com/galleries/test/cover"
                },
                "pages": [{
                    "url": "https://i.test.com/1.jpg",
                    "cdn_url": "https://test.com/galleries/test/1"
                }]
            },
            "pdf_status": "processing"
        },
        id="basic_gallery_processing"
    ),
    pytest.param(
        {
            "id": 123,
            "images": {
                "cover": {"url": "https://i.test.com/cover.jpg"},
                "pages": [{"url": "https://i.test.com/1.jpg"}]
            }
        },
        {
            "id": 123,
            "images": {
                "cover": {"url": "https://i.test.com/cover.jpg"},
                "pages": [{"url": "https://i.test.com/1.jpg"}]
            },
            "pdf_status": "unavailable"
        },
        id="gallery_without_media_id"
    )
]

@pytest.mark.parametrize("input_data,expected", process_gallery_data_cases)
def test_process_gallery_data(
    gallery_service: GalleryService,
    input_data: Dict[str, Any],
    expected: Dict[str, Any],
    mocker
) -> None:
    """Test gallery data processing with different inputs"""
    # Mock storage service get_cdn_url to return predictable values
    if gallery_service.storage_service:
        mocker.patch.object(
            gallery_service.storage_service,
            'get_cdn_url',
            side_effect=lambda url, media_id: f"https://test.com/galleries/{media_id}/{'cover' if 'cover' in url else '1'}"
        )
        
        # Mock check_pdf_exists to return None
        mocker.patch.object(
            gallery_service.storage_service,
            'check_pdf_exists',
            return_value=None
        )
    
    result = gallery_service._process_gallery_data(input_data, str(input_data['id']))
    assert result == expected

# Test cases for gallery fetching
get_gallery_cases = [
    pytest.param(
        123456,  # gallery_id
        False,   # check_status
        (
            {
                "status": True,
                "data": {
                    "id": 123456,
                    "media_id": "test",
                    "images": {"pages": []},
                    "pdf_status": "processing"
                }
            },
            200
        ),
        id="successful_fetch"
    ),
    pytest.param(
        -1,      # gallery_id
        False,   # check_status
        (
            {
                "status": False,
                "reason": "Invalid gallery ID"
            },
            400
        ),
        id="invalid_gallery_id"
    )
]

@pytest.mark.parametrize("gallery_id,check_status,expected", get_gallery_cases)
def test_get_gallery(
    gallery_service: GalleryService,
    mocker,
    gallery_id: int,
    check_status: bool,
    expected: Tuple[Dict[str, Any], int]
) -> None:
    """Test gallery fetching with different scenarios"""
    # Mock cookie manager
    mocker.patch.object(
        gallery_service.cookie_manager,
        'ensure_valid_cookies',
        return_value=True
    )

    # Mock storage service
    if gallery_service.storage_service:
        mocker.patch.object(
            gallery_service.storage_service,
            'check_pdf_exists',
            return_value=None
        )

    # Mock the response for successful case
    if gallery_id > 0:
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.text = '''
            <html>
                <script>
                    var gallery = JSON.parse('{"id": 123456, "media_id": "test", "images": {"pages": []}}');
                </script>
            </html>
        '''
        mocker.patch.object(
            gallery_service.cookie_manager,
            'get',
            return_value=mock_response
        )

    result = gallery_service.get_gallery(gallery_id, check_status)
    assert result == expected

def test_gallery_caching(
    gallery_service: GalleryService,
    sample_gallery_data: Dict[str, Any],
    mocker
) -> None:
    """Test that gallery data is properly cached"""
    gallery_id = sample_gallery_data['id']

    # Mock cookie manager
    mocker.patch.object(
        gallery_service.cookie_manager,
        'ensure_valid_cookies',
        return_value=True
    )

    # Cache the data
    gallery_service.gallery_cache.set(gallery_id, sample_gallery_data)

    # Mock storage service
    if gallery_service.storage_service:
        mocker.patch.object(
            gallery_service.storage_service,
            'check_pdf_exists',
            return_value=None
        )

    # Fetch it back
    result, status = gallery_service.get_gallery(gallery_id)

    assert status == 200
    assert result == sample_gallery_data

def test_pdf_status_check(
    gallery_service: GalleryService,
    sample_gallery_data: Dict[str, Any],
    mocker
) -> None:
    """Test PDF status checking"""
    gallery_id = sample_gallery_data['id']
    
    # Mock cookie manager
    mocker.patch.object(
        gallery_service.cookie_manager,
        'ensure_valid_cookies',
        return_value=True
    )
    
    # Start PDF processing
    gallery_service.pdf_service.process_gallery(sample_gallery_data, str(gallery_id))
    
    # Check status
    result, status = gallery_service.get_gallery(gallery_id, check_pdf_status=True)
    
    assert status == 200
    assert result['status'] is True
    assert 'pdf_status' in result
    assert result['pdf_status'] in ['processing', 'completed', 'error'] 