from flask import Flask, jsonify, request, Response
from CFSession import cfSession, cfDirectory, Options
from CFSession import cf
import threading
import os
from typing import Union, Dict
from bs4 import BeautifulSoup
import re
import json
import logging
import urllib3
import requests
import time
import concurrent.futures
import boto3
import hashlib
from botocore.config import Config
import io
from PIL import Image
import img2pdf
import tempfile
from dotenv import load_dotenv

# Load environment variables from .env file in development
if os.path.exists('.env'):
    load_dotenv()

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,  # Changed back to INFO for production
    format='%(asctime)s - %(levelname)s - %(message)s'  # Simplified format
)
logger = logging.getLogger(__name__)

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CACHE_DIR = os.path.join(os.getcwd(),"cache")
WEB_TARGET = "https://nhentai.net"
app = Flask(__name__)

# Add these near the top with other constants
MAX_WORKERS = min(32, (os.cpu_count() or 1) * 4)  # Default to CPU count * 4, max 32
CHUNK_SIZE = 10  # Number of pages to process in each batch
REQUEST_DELAY = 0.1  # 100ms delay between requests in the same thread

# Add these constants with the others
GALLERY_CACHE_DIR = os.path.join(os.getcwd(), "gallery_cache")
CACHE_DURATION = 60 * 60 * 24  # 24 hours in seconds

# R2 Configuration
R2_ACCOUNT_ID = os.environ.get('CF_ACCOUNT_ID')
R2_ACCESS_KEY_ID = os.environ.get('R2_ACCESS_KEY_ID')
R2_SECRET_ACCESS_KEY = os.environ.get('R2_SECRET_ACCESS_KEY')
R2_BUCKET_NAME = os.environ.get('R2_BUCKET_NAME')
R2_PUBLIC_URL = os.environ.get('R2_PUBLIC_URL')  # Your custom domain or public bucket URL

# Initialize R2 client if credentials are available
r2_client = None
if all([R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID]):
    r2_client = boto3.client(
        service_name='s3',
        endpoint_url=f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com',
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(
            region_name='auto',
            s3={'addressing_style': 'virtual'}
        )
    )

def upload_to_r2(file_data: bytes, key: str, content_type: str = 'application/pdf') -> str:
    """
    Upload a file to R2 storage and return its public URL
    """
    if not r2_client:
        raise Exception("R2 client not initialized. Check your environment variables.")
    
    try:
        r2_client.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=key,
            Body=file_data,
            ContentType=content_type
        )
        return f"{R2_PUBLIC_URL.rstrip('/')}/{key}"
    except Exception as e:
        logger.error(f"Failed to upload to R2: {str(e)}")
        raise

def get_from_r2(key: str) -> Union[bytes, None]:
    """
    Get a file from R2 storage
    """
    if not r2_client:
        return None
    
    try:
        response = r2_client.get_object(
            Bucket=R2_BUCKET_NAME,
            Key=key
        )
        return response['Body'].read()
    except r2_client.exceptions.NoSuchKey:
        return None
    except Exception as e:
        logger.error(f"Failed to get from R2: {str(e)}")
        return None

def get_cdn_url(original_url: str, gallery_id: str) -> str:
    """Generate CDN URL for an image"""
    if not r2_client or not R2_PUBLIC_URL:
        return original_url
        
    # Create a unique but consistent path for the image
    url_hash = hashlib.md5(original_url.encode()).hexdigest()
    extension = original_url.split('.')[-1]
    cdn_path = f"galleries/{gallery_id}/{url_hash}.{extension}"
    
    return f"{R2_PUBLIC_URL.rstrip('/')}/{cdn_path}"

async def mirror_to_cdn(original_url: str, gallery_id: str) -> str:
    """Mirror an image to R2 and return CDN URL"""
    if not r2_client:
        return original_url
        
    try:
        # Download image
        response = session.get(original_url, verify=False, stream=True)
        if response.status_code != 200:
            logger.error(f"Failed to download image {original_url}: {response.status_code}")
            return original_url
            
        # Generate CDN path
        url_hash = hashlib.md5(original_url.encode()).hexdigest()
        extension = original_url.split('.')[-1]
        cdn_path = f"galleries/{gallery_id}/{url_hash}.{extension}"
        
        # Check if already exists in R2
        try:
            r2_client.head_object(Bucket=R2_BUCKET_NAME, Key=cdn_path)
            logger.info(f"Image already exists in CDN: {cdn_path}")
            return get_cdn_url(original_url, gallery_id)
        except:
            # Upload to R2
            r2_client.upload_fileobj(
                response.raw,
                R2_BUCKET_NAME,
                cdn_path,
                ExtraArgs={
                    'ContentType': response.headers.get('content-type', 'image/webp'),
                    'CacheControl': 'public, max-age=31536000'  # Cache for 1 year
                }
            )
            logger.info(f"Uploaded image to CDN: {cdn_path}")
            
        return get_cdn_url(original_url, gallery_id)
    except Exception as e:
        logger.error(f"Failed to mirror image to CDN: {str(e)}")
        return original_url

def download_image(url: str, session: cfSession) -> bytes:
    """Download an image from a URL and return its bytes"""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            response = session.get(url, verify=False, timeout=10)
            
            if response.status_code == 403:
                retry_count += 1
                if retry_count < max_retries:
                    logger.info(f"Got 403, retrying download...")
                    response = session.get(WEB_TARGET, verify=False, timeout=10)
                    time.sleep(2)
                    continue
                else:
                    logger.error(f"Failed to download image after {max_retries} attempts")
                    return None
            
            if response.status_code != 200:
                logger.error(f"Failed to download image: status {response.status_code}")
                return None
                
            return response.content
            
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            retry_count += 1
            if retry_count < max_retries:
                time.sleep(2)
                continue
            return None
    
    return None

def create_pdf_from_images(images: list[bytes], gallery_id: str) -> bytes:
    """Create a PDF from a list of image bytes"""
    try:
        # Convert images to PIL Images and save as temporary files
        temp_files = []
        image_files = []
        
        for img_bytes in images:
            if not img_bytes:
                continue
                
            try:
                # Create a temporary file
                temp = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                temp_files.append(temp.name)
                
                # Convert to RGB if needed and save as JPEG
                img = Image.open(io.BytesIO(img_bytes))
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                img.save(temp.name, 'JPEG', quality=85)
                image_files.append(temp.name)
            except Exception as e:
                logger.error(f"Failed to process image: {str(e)}")
                continue
        
        if not image_files:
            raise Exception("No valid images to create PDF")
            
        # Create PDF
        pdf_bytes = img2pdf.convert(image_files)
        
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                os.remove(temp_file)
            except:
                pass
                
        return pdf_bytes
    except Exception as e:
        logger.error(f"Failed to create PDF: {str(e)}")
        return None

def get_json_web(html_content: str) -> Dict:
    """Extract JSON data from HTML content"""
    try:
        # Find the gallery JSON data in the HTML
        match = re.search(r'JSON\.parse\(["\'](.+?)["\']\)', html_content)
        if not match:
            logger.error("Failed to find JSON data in HTML")
            return None
            
        # Unescape the JSON string and parse it
        json_str = match.group(1).encode('utf-8').decode('unicode_escape')
        data = json.loads(json_str)
        logger.info(f"Extracted JSON data: {json.dumps(data)[:200]}...")  # Log first 200 chars
        
        # Debug image URLs
        if 'images' in data and 'pages' in data['images']:
            logger.debug("Found image pages in JSON data")
            for i, page in enumerate(data['images']['pages']):
                original_url = page.get('url', '')
                logger.debug(f"Page {i+1} URL: {original_url}")
                # Try to convert t*.nhentai.net to i*.nhentai.net
                if original_url.startswith('https://t'):
                    new_url = original_url.replace('//t', '//i', 1)
                    logger.debug(f"Converting URL from {original_url} to {new_url}")
                    page['url'] = new_url
                
        return data
    except Exception as e:
        logger.error(f"Failed to extract JSON data: {str(e)}", exc_info=True)
        return None

def process_gallery_images(data: Dict, gallery_id: str) -> Dict:
    """Process gallery images and create PDF if R2 is available"""
    try:
        logger.info(f"Processing gallery {gallery_id}")
        
        # Process cover image if exists
        if 'images' in data and 'cover' in data['images']:
            cover = data['images']['cover']
            if 'url' in cover:
                original_url = cover.get('url', '')
                if original_url.startswith('https://t'):
                    cover['url'] = original_url.replace('//t', '//i', 1)
                if r2_client:
                    cover['cdn_url'] = get_cdn_url(cover['url'], gallery_id)
        
        # Process all page images
        if 'images' in data and 'pages' in data['images']:
            total_pages = len(data['images']['pages'])
            logger.info(f"Processing {total_pages} pages")
            
            # If R2 is available, test first page download
            if r2_client:
                try:
                    cf_session = cfSession(directory=cfDirectory(CACHE_DIR), headless_mode=True)
                    cf_session.get(WEB_TARGET, verify=False, timeout=10)
                    
                    # Test download of first page
                    first_page = data['images']['pages'][0]
                    if 'url' in first_page:
                        url = first_page['url']
                        if url.startswith('https://t'):
                            url = url.replace('//t', '//i', 1)
                        img_bytes = download_image(url, cf_session)
                        if not img_bytes:
                            logger.error("Failed to download first page")
                            data['pdf_error'] = "Failed to download test page"
                            # Process CDN URLs and return early
                            for page in data['images']['pages']:
                                if r2_client:
                                    if 'url' in page:
                                        page['cdn_url'] = get_cdn_url(page['url'], gallery_id)
                                    if 'thumbnail' in page:
                                        page['thumbnail_cdn'] = get_cdn_url(page['thumbnail'], gallery_id)
                            return data
                        
                        logger.info("First page download successful")
                        image_bytes = [img_bytes]
                        failed_pages = []
                        
                        # Process remaining pages
                        for i, page in enumerate(data['images']['pages'][1:], 2):
                            if 'url' in page:
                                url = page['url']
                                if url.startswith('https://t'):
                                    url = url.replace('//t', '//i', 1)
                                img_bytes = download_image(url, cf_session)
                                if img_bytes:
                                    image_bytes.append(img_bytes)
                                else:
                                    logger.error(f"Failed to download page {i}")
                                    failed_pages.append(i)
                            time.sleep(2)
                        
                        if failed_pages:
                            logger.warning(f"Failed to download pages: {failed_pages}")
                            data['failed_pages'] = failed_pages
                        
                        if image_bytes:
                            logger.info("Creating PDF")
                            pdf_bytes = create_pdf_from_images(image_bytes, gallery_id)
                            if pdf_bytes:
                                pdf_key = f"galleries/{gallery_id}/full.pdf"
                                try:
                                    r2_client.put_object(
                                        Bucket=R2_BUCKET_NAME,
                                        Key=pdf_key,
                                        Body=pdf_bytes,
                                        ContentType='application/pdf',
                                        CacheControl='public, max-age=31536000'
                                    )
                                    data['pdf_url'] = f"{R2_PUBLIC_URL.rstrip('/')}/{pdf_key}"
                                    logger.info(f"PDF created and uploaded successfully")
                                except Exception as e:
                                    logger.error(f"Failed to upload PDF: {str(e)}")
                                    data['pdf_error'] = "Failed to upload PDF to storage"
                except Exception as e:
                    logger.error(f"PDF creation failed: {str(e)}")
                    data['pdf_error'] = "Failed to create PDF"
            
            # Process individual pages
            for page in data['images']['pages']:
                if r2_client:
                    if 'url' in page:
                        page['cdn_url'] = get_cdn_url(page['url'], gallery_id)
                    if 'thumbnail' in page:
                        page['thumbnail_cdn'] = get_cdn_url(page['thumbnail'], gallery_id)
                else:
                    if 'thumbnail' in page:
                        page['thumbnail'] = page.get('thumbnail', '')
                    if 'url' in page:
                        page['url'] = page.get('url', '')
        
        return data
    except Exception as e:
        logger.error(f"Gallery processing error: {str(e)}")
        return data

class CookieManager:
    def __init__(self, session: cfSession, target: str):
        self.session = session
        self.target = target
        self.last_renewal = 0
        self.renewal_interval = 30  # Reduced from 60 to 30 seconds
        self.lock = threading.Lock()
        self._renewing = False
        self.max_retries = 3
        
    def ensure_valid_cookies(self) -> bool:
        """Ensures cookies are valid, renews if necessary"""
        with self.lock:
            current_time = time.time()
            
            if self._renewing:
                time.sleep(2)
                return True
            
            if current_time - self.last_renewal > self.renewal_interval:
                return self._renew_cookies()
            
            try:
                response = self.session.session.get(self.target, verify=False, timeout=10)
                if response.status_code != 200:
                    return self._renew_cookies()
                return True
            except Exception as e:
                logger.error(f"Cookie validation failed: {str(e)}", exc_info=True)
                return self._renew_cookies()
    
    def _renew_cookies(self) -> bool:
        """Internal method to handle cookie renewal"""
        if self._renewing:
            return True
            
        self._renewing = True
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                logger.info(f"Attempting to renew cookies (attempt {retry_count + 1}/{self.max_retries})")
                response = self.session.get(self.target, verify=False, timeout=10)
                success = response.status_code == 200
                
                if success:
                    self.last_renewal = time.time()
                    logger.info("Cookie renewal completed successfully")
                    self._renewing = False
                    return True
                    
                logger.error(f"Cookie renewal failed: status {response.status_code}")
                retry_count += 1
                if retry_count < self.max_retries:
                    time.sleep(2)  # Wait before retrying
                    continue
                    
            except Exception as e:
                logger.error(f"Cookie renewal error: {str(e)}", exc_info=True)
                retry_count += 1
                if retry_count < self.max_retries:
                    time.sleep(2)  # Wait before retrying
                    continue
                    
        self._renewing = False
        return False

class GalleryCache:
    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        logger.info(f"Initializing gallery cache at: {cache_dir}")
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_path(self, gallery_id: int) -> str:
        path = os.path.join(self.cache_dir, f"{gallery_id}.json")
        logger.debug(f"Cache path for gallery {gallery_id}: {path}")
        return path
    
    def get(self, gallery_id: int) -> Union[Dict, None]:
        """Get gallery data from cache if it exists and is not expired"""
        cache_path = self._get_cache_path(gallery_id)
        logger.info(f"Checking cache for gallery {gallery_id} at {cache_path}")
        try:
            if os.path.exists(cache_path):
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    # Check if cache is expired
                    if time.time() - cached_data['cached_at'] < CACHE_DURATION:
                        logger.info(f"Cache hit for gallery {gallery_id}")
                        return cached_data['data']
                    else:
                        logger.info(f"Cache expired for gallery {gallery_id}")
                        os.remove(cache_path)  # Clean up expired cache
            logger.info(f"No cache found for gallery {gallery_id}")
            return None
        except Exception as e:
            logger.error(f"Cache read error for gallery {gallery_id}: {str(e)}")
            return None
    
    def set(self, gallery_id: int, data: Dict):
        """Save gallery data to cache"""
        cache_path = self._get_cache_path(gallery_id)
        logger.info(f"Attempting to cache gallery {gallery_id} at {cache_path}")
        try:
            cache_data = {
                'cached_at': time.time(),
                'data': data
            }
            logger.info(f"Prepared cache data for gallery {gallery_id}")
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            
            # Write to a temporary file first
            temp_path = cache_path + '.tmp'
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False)
            logger.info(f"Wrote temporary cache file for gallery {gallery_id}")
            
            # Rename temp file to final file (atomic operation)
            os.replace(temp_path, cache_path)
            logger.info(f"Successfully cached gallery {gallery_id}")
        except Exception as e:
            logger.error(f"Cache write error for gallery {gallery_id}: {str(e)}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

# Initialize session and cookie manager
try:
    session = cfSession(directory=cfDirectory(CACHE_DIR), headless_mode=True)
    cookie_manager = CookieManager(session, WEB_TARGET)
    gallery_cache = GalleryCache(GALLERY_CACHE_DIR)
    
    # Initial cookie setup
    if not cookie_manager.ensure_valid_cookies():
        logger.warning("Initial cookie setup failed, will retry on requests")
except Exception as e:
    logger.error(f"Application initialization failed: {str(e)}")
    raise

def json_resp(jsondict, status=200):
    resp = jsonify(jsondict)
    resp.status_code = status
    return resp

def conditioner(func):
    def wrapper(*args, **kwargs):
        jsonned, status = func(*args, **kwargs)
        return jsonned, status  # Return the tuple directly without wrapping
    return wrapper

def isSiteValid(url):
    try:
        response = session.session.get(url, verify=False)
        return response.status_code == 200
    except Exception:
        return False

@conditioner
def get_json_web(response) -> Union[None, Dict]:
    if response.status_code != 200:
        return ({"status": False, "reason": f"Error, backend returned {response.status_code}"}, response.status_code)
    elif response.status_code == 404:
        return ({"status": False, "reason": "Error, cannot find what you're looking for"}, response.status_code)
    
    try:
        page = response.content
        soup = BeautifulSoup(page, "html.parser")
        
        # Get the JSON data first
        json_regex = r'JSON\.parse\("(.*?)"\)'
        script = re.search(json_regex, (soup.find_all("script")[2].contents[0]).strip()).group(1).encode("utf-8").decode("unicode-escape")
        data = json.loads(script)
        logger.info(f"Extracted JSON data: {json.dumps(data)[:200]}...")  # Log first 200 chars
        
        # Extract thumbnail URLs from the gallery page
        thumbs_div = soup.find("div", class_="thumbs")
        if thumbs_div:
            if 'images' in data and 'pages' in data['images']:
                for i, (thumb_container, page_data) in enumerate(zip(thumbs_div.find_all("div", class_="thumb-container"), data['images']['pages']), 1):
                    img = thumb_container.find("img")
                    if img:
                        thumb_url = img.get("data-src", "")
                        if thumb_url:
                            page_data['thumbnail'] = thumb_url
                            # Set fallback URL by removing 't' from thumbnail
                            page_data['url'] = thumb_url.replace("t.", ".")
        
        # Process images for CDN if available
        if r2_client and 'media_id' in data:
            data = process_gallery_images(data, data['media_id'])
        
        return (data, 200)  # Return raw data without wrapping
    except Exception as e:
        logger.error(f"JSON extraction failed: {str(e)}")
        return ({"status": False, "reason": f"Error processing data: {str(e)}"}, 500)

@app.route("/",methods=["GET"])
def getmain():
    return json_resp({"status": False, "reason": "Invalid path"}, status=404)

@app.route("/health-check", methods=["GET"])
def health_check():
    try:
        # Check if cookie manager is initialized and working
        cookies_ok = cookie_manager.ensure_valid_cookies()
        return json_resp({
            "status": True,
            "service": "nhApiod-proxy",
            "timestamp": time.time(),
            "cookies_ok": cookies_ok
        })
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return json_resp({
            "status": False,
            "service": "nhApiod-proxy",
            "timestamp": time.time(),
            "error": str(e)
        }, status=500)

@app.route("/get",methods=["GET"])
def getdata():
    if not cookie_manager.ensure_valid_cookies():
        return json_resp({"status": False, "reason": "Failed to establish valid connection"}, status=500)
    
    try:
        code = int(request.args['id'])
        logger.info(f"Fetching gallery {code}")
    except ValueError:
        return json_resp({"status": False, "reason": "Invalid code"})
    except TypeError:
        return json_resp({"status": False, "reason": "Code not specified"})
    
    # Check cache first
    cached_data = gallery_cache.get(code)
    if cached_data:
        logger.info(f"Returning cached data for gallery {code}")
        return json_resp(cached_data, status=200)
    
    # Retry logic for gallery fetch
    max_retries = 2
    for attempt in range(max_retries):
        try:
            logger.info(f"Fetching gallery {code} from source (attempt {attempt + 1}/{max_retries})")
            res = session.get(f'{WEB_TARGET}/g/{code}', verify=False)
            
            if res.status_code == 403 and attempt < max_retries - 1:
                cookie_manager.ensure_valid_cookies()
                continue
                    
            data, status = get_json_web(res)  # Unpack the tuple directly
            logger.info(f"Got response for gallery {code}: status={status}")
            
            if status == 200:  # Successful response
                gallery_cache.set(code, data)
                return json_resp(data, status=200)
            else:
                return json_resp(data, status=status)
            
        except Exception as e:
            if attempt < max_retries - 1:
                continue
            logger.error(f"Gallery fetch failed for ID {code}: {str(e)}")
            return json_resp({"status": False, "reason": f"Error: {str(e)}"}, status=500)
    
    return json_resp({"status": False, "reason": "Maximum retries exceeded"}, status=500)

@app.errorhandler(404)
def notFound(e):
    return json_resp({"code": 404, "status": "You are lost"}, status=404)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)