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

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,  # Changed from DEBUG to INFO
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

class CookieManager:
    def __init__(self, session: cfSession, target: str):
        self.session = session
        self.target = target
        self.last_renewal = 0
        self.renewal_interval = 60  # Renew every 60 seconds
        self.lock = threading.Lock()
        self._renewing = False
        
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
                response = self.session.session.get(self.target, verify=False)
                if response.status_code != 200:
                    return self._renew_cookies()
                return True
            except Exception as e:
                logger.error(f"Cookie validation failed: {str(e)}")
                return self._renew_cookies()
    
    def _renew_cookies(self) -> bool:
        """Internal method to handle cookie renewal"""
        if self._renewing:
            return True
            
        self._renewing = True
        try:
            response = self.session.get(self.target, verify=False)
            success = response.status_code == 200
            if success:
                self.last_renewal = time.time()
                logger.info("Cookie renewal completed")
            else:
                logger.error(f"Cookie renewal failed: status {response.status_code}")
            return success
        except Exception as e:
            logger.error(f"Cookie renewal error: {str(e)}")
            return False
        finally:
            self._renewing = False

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
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)