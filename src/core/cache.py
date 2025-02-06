import os
import json
import time
import logging
import threading
from typing import Dict, Optional, Any

from src.config.settings import Settings

logger = logging.getLogger(__name__)

class GalleryCache:
    """Cache manager for gallery data"""
    
    def __init__(self, cache_dir: str = Settings.GALLERY_CACHE_DIR):
        """
        Initialize the gallery cache
        
        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = cache_dir
        logger.info(f"Initializing gallery cache at: {cache_dir}")
        os.makedirs(cache_dir, exist_ok=True)
        self.lock = threading.Lock()
    
    def _get_cache_path(self, gallery_id: int) -> str:
        """
        Get the cache file path for a gallery
        
        Args:
            gallery_id: The gallery ID
            
        Returns:
            str: Path to the cache file
        """
        path = os.path.join(self.cache_dir, f"{gallery_id}.json")
        logger.debug(f"Cache path for gallery {gallery_id}: {path}")
        return path
    
    def get(self, gallery_id: int) -> Optional[Dict[str, Any]]:
        """
        Get cached data for a gallery
        
        Args:
            gallery_id: The gallery ID
            
        Returns:
            Optional[Dict[str, Any]]: Cached data if available and valid, None otherwise
        """
        cache_path = self._get_cache_path(gallery_id)
        logger.info(f"Checking cache for gallery {gallery_id}")
        
        with self.lock:
            try:
                if os.path.exists(cache_path):
                    try:
                        with open(cache_path, 'r', encoding='utf-8') as f:
                            cached_data = json.load(f)
                            if time.time() - cached_data['cached_at'] < Settings.CACHE_DURATION:
                                return cached_data['data']
                            else:
                                self._remove_cache_file(cache_path)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.error(f"Cache read error for gallery {gallery_id}: {str(e)}")
                        self._remove_cache_file(cache_path)
                return None
            except Exception as e:
                logger.error(f"Unexpected cache read error: {str(e)}")
                return None
    
    def set(self, gallery_id: int, data: Dict[str, Any]) -> bool:
        """
        Cache data for a gallery
        
        Args:
            gallery_id: The gallery ID
            data: The data to cache
            
        Returns:
            bool: True if cache was successful, False otherwise
        """
        cache_path = self._get_cache_path(gallery_id)
        logger.info(f"Caching gallery {gallery_id}")
        
        with self.lock:
            try:
                cache_data = {
                    'cached_at': time.time(),
                    'data': data
                }
                
                temp_path = cache_path + '.tmp'
                try:
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        json.dump(cache_data, f, ensure_ascii=False)
                    
                    if os.path.exists(cache_path):
                        os.remove(cache_path)
                    os.rename(temp_path, cache_path)
                    return True
                finally:
                    if os.path.exists(temp_path):
                        self._remove_cache_file(temp_path)
            except Exception as e:
                logger.error(f"Cache write error: {str(e)}")
                self._remove_cache_file(cache_path)
                return False
    
    def _remove_cache_file(self, path: str) -> None:
        """
        Safely remove a cache file
        
        Args:
            path: Path to the cache file
        """
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as e:
            logger.error(f"Failed to remove cache file {path}: {str(e)}")
    
    def clear(self) -> None:
        """Clear all cached data"""
        with self.lock:
            try:
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith('.json'):
                        self._remove_cache_file(os.path.join(self.cache_dir, filename))
            except Exception as e:
                logger.error(f"Failed to clear cache: {str(e)}")
    
    def cleanup_expired(self) -> None:
        """Remove expired cache entries"""
        with self.lock:
            try:
                current_time = time.time()
                for filename in os.listdir(self.cache_dir):
                    if not filename.endswith('.json'):
                        continue
                        
                    file_path = os.path.join(self.cache_dir, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            cached_data = json.load(f)
                            if current_time - cached_data['cached_at'] >= Settings.CACHE_DURATION:
                                self._remove_cache_file(file_path)
                    except (json.JSONDecodeError, KeyError, OSError):
                        self._remove_cache_file(file_path)
            except Exception as e:
                logger.error(f"Failed to cleanup expired cache: {str(e)}") 