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

# Initialize session and cookie manager
try:
    session = cfSession(directory=cfDirectory(CACHE_DIR), headless_mode=True)
    cookie_manager = CookieManager(session, WEB_TARGET)
    
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
        done = jsonned.get("status")
        return {"status_code": status,"isDone": done,"json": jsonned}
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
        json_regex = r'JSON\.parse\("(.*?)"\)'
        script = re.search(json_regex, (soup.find_all("script")[2].contents[0]).strip()).group(1).encode("utf-8").decode("unicode-escape")
        return (json.loads(script), 200)
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
    except ValueError:
        return json_resp({"status": False, "reason": "Invalid code"})
    except TypeError:
        return json_resp({"status": False, "reason": "Code not specified"})
    
    # Retry logic for gallery fetch
    max_retries = 2
    for attempt in range(max_retries):
        try:
            res = session.get(f'{WEB_TARGET}/g/{code}', verify=False)
            
            if res.status_code == 403 and attempt < max_retries - 1:
                cookie_manager.ensure_valid_cookies()
                continue
                    
            json_api = get_json_web(res)
            if not json_api.get("isDone"):
                return json_resp(json_api['json'], status=json_api["status_code"])
            return json_resp(json_api, status=200)
            
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