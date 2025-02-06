import logging
import hashlib
from typing import Optional
import boto3
from botocore.config import Config

from src.config.settings import Settings

logger = logging.getLogger(__name__)

class R2StorageService:
    """Service for handling R2 storage operations"""
    
    def __init__(self):
        """Initialize the R2 storage service"""
        if not Settings.is_r2_configured():
            raise ValueError("R2 storage is not properly configured")
        
        self.client = boto3.client(
            service_name='s3',
            endpoint_url=f'https://{Settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
            aws_access_key_id=Settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=Settings.R2_SECRET_ACCESS_KEY,
            config=Config(
                region_name='auto',
                s3={'addressing_style': 'virtual'}
            )
        )
        self.bucket_name = Settings.R2_BUCKET_NAME
        self.public_url = Settings.R2_PUBLIC_URL.rstrip('/')
    
    def upload_pdf(self, key: str, data: bytes) -> str:
        """
        Upload PDF data to R2 storage
        
        Args:
            key: Storage key for the PDF
            data: PDF data to upload
            
        Returns:
            str: Public URL of the uploaded PDF
            
        Raises:
            Exception: If upload fails
        """
        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType='application/pdf'
            )
            return f"{self.public_url}/{key}"
        except Exception as e:
            logger.error(f"Failed to upload PDF {key}: {str(e)}")
            raise
    
    def check_pdf_exists(self, gallery_id: str) -> Optional[str]:
        """
        Check if a gallery PDF exists in storage
        
        Args:
            gallery_id: Gallery ID to check
            
        Returns:
            Optional[str]: Public URL of the PDF if it exists, None otherwise
        """
        try:
            pdf_key = f"galleries/{gallery_id}/full.pdf"
            self.client.head_object(
                Bucket=self.bucket_name,
                Key=pdf_key
            )
            return f"{self.public_url}/{pdf_key}"
        except self.client.exceptions.ClientError as e:
            if e.response['Error']['Code'] == '404':
                return None
            logger.error(f"R2 check error for gallery {gallery_id}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Failed to check PDF existence for gallery {gallery_id}: {str(e)}")
            return None
    
    def get_cdn_url(self, url: str, media_id: str) -> str:
        """
        Generate CDN URL for an image
        
        Args:
            url: Original image URL
            media_id: Media ID for the gallery
            
        Returns:
            str: CDN URL for the image
        """
        key = f"galleries/{media_id}/{hashlib.sha256(url.encode()).hexdigest()}"
        return f"{self.public_url}/{key}" 