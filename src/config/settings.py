import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file in development
if os.path.exists('.env'):
    load_dotenv()

class Settings:
    """Centralized configuration settings"""
    
    # Application settings
    PORT: int = int(os.environ.get("PORT", 5001))
    DEBUG: bool = os.environ.get("DEBUG", "false").lower() == "true"
    
    # Directory settings
    CACHE_DIR: str = os.path.join(os.getcwd(), "cache")
    GALLERY_CACHE_DIR: str = os.path.join(os.getcwd(), "gallery_cache")
    
    # Web settings
    WEB_TARGET: str = "https://nhentai.net"
    MAX_WORKERS: int = min(32, (os.cpu_count() or 1) * 4)
    REQUEST_DELAY: float = float(os.getenv('CLOUDSCRAPER_DELAY', '0.1'))
    MAX_RETRIES: int = int(os.getenv('CLOUDSCRAPER_RETRIES', '3'))
    
    # Cache settings
    CACHE_DURATION: int = 60 * 60 * 24  # 24 hours
    
    # R2 Storage settings
    R2_ACCOUNT_ID: Optional[str] = os.environ.get('CF_ACCOUNT_ID')
    R2_ACCESS_KEY_ID: Optional[str] = os.environ.get('R2_ACCESS_KEY_ID')
    R2_SECRET_ACCESS_KEY: Optional[str] = os.environ.get('R2_SECRET_ACCESS_KEY')
    R2_BUCKET_NAME: Optional[str] = os.environ.get('R2_BUCKET_NAME')
    R2_PUBLIC_URL: Optional[str] = os.environ.get('R2_PUBLIC_URL')
    
    @classmethod
    def is_r2_configured(cls) -> bool:
        """Check if R2 storage is properly configured"""
        return all([
            cls.R2_ACCESS_KEY_ID,
            cls.R2_SECRET_ACCESS_KEY,
            cls.R2_ACCOUNT_ID,
            cls.R2_BUCKET_NAME,
            cls.R2_PUBLIC_URL
        ])
    
    @classmethod
    def ensure_directories(cls) -> None:
        """Ensure required directories exist"""
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
        os.makedirs(cls.GALLERY_CACHE_DIR, exist_ok=True)

# Create directories on module import
Settings.ensure_directories() 