import re
import logging
from typing import Dict, Optional, Any, Tuple
from bs4 import BeautifulSoup
import json

from src.core.cookie_manager import CookieManager
from src.core.cache import GalleryCache
from src.services.pdf import PDFService
from src.services.storage import R2StorageService
from src.config.settings import Settings

logger = logging.getLogger(__name__)

class GalleryService:
    """Service for handling gallery data processing"""
    
    def __init__(
        self,
        cookie_manager: CookieManager,
        gallery_cache: GalleryCache,
        pdf_service: Optional[PDFService] = None,
        storage_service: Optional[R2StorageService] = None
    ):
        """
        Initialize the gallery service
        
        Args:
            cookie_manager: Cookie manager instance
            gallery_cache: Gallery cache instance
            pdf_service: Optional PDF service instance
            storage_service: Optional storage service instance
        """
        self.cookie_manager = cookie_manager
        self.gallery_cache = gallery_cache
        self.pdf_service = pdf_service
        self.storage_service = storage_service
    
    def get_gallery(self, gallery_id: int, check_pdf_status: bool = False) -> Tuple[Dict[str, Any], int]:
        """
        Get gallery data by ID
        
        Args:
            gallery_id: Gallery ID to fetch
            check_pdf_status: Whether to check PDF processing status
            
        Returns:
            Tuple[Dict[str, Any], int]: Gallery data and HTTP status code
        """
        # Validate gallery ID
        if gallery_id <= 0:
            return {
                "status": False,
                "reason": "Invalid gallery ID"
            }, 400

        # Ensure valid connection
        if not self.cookie_manager.ensure_valid_cookies():
            return {
                "status": False,
                "reason": "Failed to establish valid connection"
            }, 500
        
        # Check PDF status if requested
        if check_pdf_status and self.pdf_service:
            status = self.pdf_service.get_status(str(gallery_id))
            if status:
                return {
                    "status": True,
                    "pdf_status": status.status,
                    "error": status.error,
                    "pdf_url": status.pdf_url
                }, 200
        
        # Check cache
        cached_data = self.gallery_cache.get(gallery_id)
        if cached_data:
            logger.info(f"Found cached data for gallery {gallery_id}")
            return cached_data, 200
        
        # Fetch from source
        for attempt in range(Settings.MAX_RETRIES):
            try:
                logger.info(f"Fetching gallery {gallery_id} (attempt {attempt + 1}/{Settings.MAX_RETRIES})")
                response = self.cookie_manager.get(
                    f'{Settings.WEB_TARGET}/g/{gallery_id}',
                    timeout=10
                )
                
                if not response:
                    continue
                
                if response.status_code == 403 and attempt < Settings.MAX_RETRIES - 1:
                    self.cookie_manager.ensure_valid_cookies()
                    continue
                
                if response.status_code != 200:
                    return {
                        "status": False,
                        "reason": f"Backend returned {response.status_code}"
                    }, response.status_code
                
                # Extract and process data
                data = self._extract_gallery_data(response.text)
                if not data:
                    return {
                        "status": False,
                        "reason": "Failed to extract gallery data"
                    }, 500
                
                # Process images and cache
                processed_data = self._process_gallery_data(data, str(gallery_id))
                self.gallery_cache.set(gallery_id, processed_data)
                
                return {
                    "status": True,
                    "data": processed_data
                }, 200
                
            except Exception as e:
                if attempt < Settings.MAX_RETRIES - 1:
                    continue
                logger.error(f"Gallery fetch failed: {str(e)}")
                return {
                    "status": False,
                    "reason": f"Error: {str(e)}"
                }, 500
        
        return {
            "status": False,
            "reason": "Maximum retries exceeded"
        }, 500
    
    def _extract_gallery_data(self, html_content: str) -> Optional[Dict[str, Any]]:
        """
        Extract gallery data from HTML content
        
        Args:
            html_content: HTML content to parse
            
        Returns:
            Optional[Dict[str, Any]]: Extracted gallery data if successful
        """
        try:
            # Find JSON data in script tag
            match = re.search(r'JSON\.parse\(["\'](.+?)["\']\)', html_content)
            if not match:
                return None
            
            # Parse JSON data
            json_str = match.group(1).encode('utf-8').decode('unicode-escape')
            data = json.loads(json_str)
            
            # Extract thumbnail URLs
            soup = BeautifulSoup(html_content, "html.parser")
            thumbs_div = soup.find("div", class_="thumbs")
            
            if thumbs_div and 'images' in data and 'pages' in data['images']:
                for i, (thumb_container, page_data) in enumerate(
                    zip(thumbs_div.find_all("div", class_="thumb-container"),
                        data['images']['pages']), 1):
                    img = thumb_container.find("img")
                    if img:
                        thumb_url = img.get("data-src", "")
                        if thumb_url:
                            page_data['thumbnail'] = thumb_url
                            # Set fallback URL
                            page_data['url'] = thumb_url.replace("t.", ".")
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to extract gallery data: {str(e)}")
            return None
    
    def _process_gallery_data(self, data: Dict[str, Any], gallery_id: str) -> Dict[str, Any]:
        """
        Process gallery data and prepare for response
        
        Args:
            data: Raw gallery data
            gallery_id: Gallery ID
            
        Returns:
            Dict[str, Any]: Processed gallery data
        """
        try:
            # Process cover image
            if 'images' in data and 'cover' in data['images']:
                cover = data['images']['cover']
                if 'url' in cover:
                    original_url = cover.get('url', '')
                    if original_url.startswith('https://t'):
                        cover['url'] = original_url.replace('//t', '//i', 1)
                    if self.storage_service and 'media_id' in data:
                        cover['cdn_url'] = self.storage_service.get_cdn_url(
                            cover['url'],
                            data['media_id']
                        )
            
            # Process page images
            if 'images' in data and 'pages' in data['images']:
                for page in data['images']['pages']:
                    if 'url' in page:
                        url = page['url']
                        if url.startswith('https://t'):
                            page['url'] = url.replace('//t', '//i', 1)
                        if self.storage_service and 'media_id' in data:
                            page['cdn_url'] = self.storage_service.get_cdn_url(
                                page['url'],
                                data['media_id']
                            )
                    if 'thumbnail' in page and self.storage_service and 'media_id' in data:
                        page['thumbnail_cdn'] = self.storage_service.get_cdn_url(
                            page['thumbnail'],
                            data['media_id']
                        )
            
            # Handle PDF status
            if not self.pdf_service or 'media_id' not in data:
                data['pdf_status'] = "unavailable"
            else:
                # Check if PDF exists
                if self.storage_service:
                    existing_pdf_url = self.storage_service.check_pdf_exists(gallery_id)
                    if existing_pdf_url:
                        data['pdf_url'] = existing_pdf_url
                        data['pdf_status'] = "completed"
                    else:
                        # Start PDF processing
                        status = self.pdf_service.get_status(gallery_id)
                        if status:
                            data['pdf_status'] = status.status
                        else:
                            self.pdf_service.process_gallery(data, gallery_id)
                            data['pdf_status'] = "processing"
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to process gallery data: {str(e)}")
            data['pdf_status'] = "error"
            return data
    
    def _process_cached_data(self, data: Dict[str, Any], gallery_id: str) -> Dict[str, Any]:
        """
        Process cached gallery data
        
        Args:
            data: Cached gallery data
            gallery_id: Gallery ID
            
        Returns:
            Dict[str, Any]: Processed gallery data
        """
        # If PDF URL exists, return as is
        if 'pdf_url' in data:
            return data
            
        # Check PDF status
        if self.pdf_service:
            status = self.pdf_service.get_status(gallery_id)
            if status:
                data['pdf_status'] = status.status
            elif self.storage_service:
                # Start PDF processing if not already started
                self.pdf_service.process_gallery(data, gallery_id)
                data['pdf_status'] = "processing"
        
        return data 