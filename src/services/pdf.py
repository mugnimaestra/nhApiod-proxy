import os
import time
import logging
import tempfile
import threading
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, List
import requests
import img2pdf
from dataclasses import dataclass

from src.config.settings import Settings
from src.services.storage import R2StorageService

logger = logging.getLogger(__name__)

@dataclass
class PDFStatus:
    """Status of PDF processing"""
    gallery_id: str
    status: str
    error: Optional[str] = None
    pdf_url: Optional[str] = None

class PDFService:
    """Service for handling PDF generation and processing"""
    
    def __init__(self, storage_service: R2StorageService):
        """
        Initialize the PDF service
        
        Args:
            storage_service: R2 storage service instance
        """
        self.storage_service = storage_service
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.processing_status: Dict[str, PDFStatus] = {}
        self.lock = threading.Lock()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_status,
            daemon=True
        )
        self._cleanup_thread.start()
    
    def get_status(self, gallery_id: str) -> Optional[PDFStatus]:
        """
        Get the current PDF processing status
        
        Args:
            gallery_id: Gallery ID to check
            
        Returns:
            Optional[PDFStatus]: Current status if available
        """
        with self.lock:
            return self.processing_status.get(gallery_id)
    
    def process_gallery(self, gallery_data: Dict, gallery_id: str) -> None:
        """
        Start PDF processing for a gallery in the background
        
        Args:
            gallery_data: Gallery data containing image URLs
            gallery_id: Gallery ID
        """
        with self.lock:
            # Check if already processing
            if gallery_id in self.processing_status:
                return
            
            # Initialize status
            self.processing_status[gallery_id] = PDFStatus(
                gallery_id=gallery_id,
                status="processing"
            )
        
        # Submit processing task
        self.executor.submit(
            self._process_pdf_in_background,
            gallery_data,
            gallery_id
        )
    
    def _process_pdf_in_background(self, gallery_data: Dict, gallery_id: str) -> None:
        """
        Background task to generate and upload PDF
        
        Args:
            gallery_data: Gallery data containing image URLs
            gallery_id: Gallery ID
        """
        try:
            logger.info(f"Starting PDF processing for gallery {gallery_id}")
            
            # Generate PDF
            pdf_bytes = self._generate_pdf(gallery_data)
            
            # Upload to storage
            pdf_key = f"galleries/{gallery_id}/full.pdf"
            pdf_url = self.storage_service.upload_pdf(pdf_key, pdf_bytes)
            
            # Update status
            with self.lock:
                self.processing_status[gallery_id] = PDFStatus(
                    gallery_id=gallery_id,
                    status="completed",
                    pdf_url=pdf_url
                )
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"PDF processing failed for gallery {gallery_id}: {error_msg}")
            
            with self.lock:
                self.processing_status[gallery_id] = PDFStatus(
                    gallery_id=gallery_id,
                    status="error",
                    error=error_msg
                )
    
    def _generate_pdf(self, gallery_data: Dict) -> bytes:
        """
        Generate PDF from gallery images
        
        Args:
            gallery_data: Gallery data containing image URLs
            
        Returns:
            bytes: Generated PDF data
            
        Raises:
            Exception: If PDF generation fails
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            image_files: List[str] = []
            
            # Download and process images
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                
                # Extract image URLs
                if 'images' not in gallery_data or 'pages' not in gallery_data['images']:
                    raise ValueError("Invalid gallery data format")
                
                for i, page in enumerate(gallery_data['images']['pages']):
                    url = page.get('url') or page.get('cdn_url')
                    if not url:
                        raise ValueError(f"No URL found for page {i}")
                    
                    futures.append(executor.submit(
                        self._download_image,
                        url,
                        tmpdir,
                        i
                    ))
                
                # Wait for all downloads
                for future in concurrent.futures.as_completed(futures):
                    img_path = future.result()
                    if img_path:
                        image_files.append(img_path)
            
            if not image_files:
                raise Exception("No images were successfully downloaded")
            
            # Convert to PDF
            return img2pdf.convert(sorted(image_files))
    
    def _download_image(self, url: str, tmpdir: str, index: int) -> Optional[str]:
        """
        Download an image and save it to a temporary file
        
        Args:
            url: Image URL
            tmpdir: Temporary directory path
            index: Image index
            
        Returns:
            Optional[str]: Path to downloaded image if successful
        """
        try:
            response = requests.get(url, verify=False, timeout=30)
            if response.status_code == 200:
                # Determine file extension
                ext = url.split('.')[-1].lower()
                if ext not in ['jpg', 'jpeg', 'png']:
                    ext = 'jpg'
                
                file_path = os.path.join(tmpdir, f"{index:03d}.{ext}")
                with open(file_path, 'wb') as f:
                    f.write(response.content)
                return file_path
            else:
                logger.error(f"Failed to download image {url}: status {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error downloading image {url}: {str(e)}")
            return None
    
    def _cleanup_status(self) -> None:
        """Background task to clean up old status entries"""
        while True:
            try:
                time.sleep(3600)  # Clean up every hour
                with self.lock:
                    # Remove completed/error statuses older than 1 hour
                    current_time = time.time()
                    to_remove = []
                    for gallery_id, status in self.processing_status.items():
                        if status.status in ["completed", "error"]:
                            to_remove.append(gallery_id)
                    
                    for gallery_id in to_remove:
                        del self.processing_status[gallery_id]
                        
            except Exception as e:
                logger.error(f"Status cleanup error: {str(e)}") 