import pytest
from typing import Dict, Any, Optional
import tempfile
import os

from src.services.pdf import PDFService, PDFStatus

# Test cases for PDF status
pdf_status_cases = [
    pytest.param(
        "123",  # gallery_id
        None,   # initial status
        None,   # expected status
        id="no_status"
    ),
    pytest.param(
        "123",  # gallery_id
        PDFStatus(gallery_id="123", status="processing"),  # initial status
        "processing",  # expected status
        id="processing_status"
    ),
    pytest.param(
        "123",  # gallery_id
        PDFStatus(
            gallery_id="123",
            status="completed",
            pdf_url="https://test.com/123.pdf"
        ),  # initial status
        "completed",  # expected status
        id="completed_status"
    )
]

@pytest.mark.parametrize("gallery_id,initial_status,expected", pdf_status_cases)
def test_get_status(
    pdf_service: PDFService,
    gallery_id: str,
    initial_status: Optional[PDFStatus],
    expected: Optional[str]
) -> None:
    """Test PDF status retrieval with different scenarios"""
    if initial_status:
        pdf_service.processing_status[gallery_id] = initial_status
    
    status = pdf_service.get_status(gallery_id)
    
    if expected is None:
        assert status is None
    else:
        assert status is not None
        assert status.status == expected

def test_process_gallery(
    pdf_service: PDFService,
    sample_gallery_data: Dict[str, Any],
    mocker
) -> None:
    """Test gallery PDF processing"""
    gallery_id = str(sample_gallery_data['id'])
    
    # Mock image download
    mock_response = mocker.MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake_image_data"
    mocker.patch('requests.get', return_value=mock_response)
    
    # Mock PDF generation
    mocker.patch('img2pdf.convert', return_value=b"fake_pdf_data")
    
    # Start processing
    pdf_service.process_gallery(sample_gallery_data, gallery_id)
    
    # Check initial status
    status = pdf_service.get_status(gallery_id)
    assert status is not None
    assert status.status == "processing"
    
    # Wait for background processing
    mocker.patch.object(pdf_service.storage_service, 'upload_pdf')
    pdf_service._process_pdf_in_background(sample_gallery_data, gallery_id)
    
    # Check final status
    status = pdf_service.get_status(gallery_id)
    assert status is not None
    assert status.status == "completed"

def test_generate_pdf_with_invalid_data(
    pdf_service: PDFService,
    mocker
) -> None:
    """Test PDF generation with invalid gallery data"""
    invalid_data = {
        "id": 123,
        "images": {}  # Missing required image data
    }
    
    with pytest.raises(ValueError, match="Invalid gallery data format"):
        pdf_service._generate_pdf(invalid_data)

def test_download_image(pdf_service: PDFService, mocker) -> None:
    """Test image downloading functionality"""
    # Create temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock successful download
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"fake_image_data"
        mocker.patch('requests.get', return_value=mock_response)
        
        # Test successful download
        result = pdf_service._download_image(
            "https://test.com/image.jpg",
            tmpdir,
            0
        )
        
        assert result is not None
        assert os.path.exists(result)
        
        # Mock failed download
        mock_response.status_code = 404
        mocker.patch('requests.get', return_value=mock_response)
        
        # Test failed download
        result = pdf_service._download_image(
            "https://test.com/not_found.jpg",
            tmpdir,
            1
        )
        
        assert result is None 