import time
import threading
import logging
import undetected_chromedriver as uc
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from typing import Optional

from src.config.settings import Settings

logger = logging.getLogger(__name__)

class CookieManager:
    """Manages browser session and cookies for web scraping using undetected-chromedriver"""
    
    def __init__(self):
        """Initialize the cookie manager with undetected Chrome browser"""
        self.driver = None
        self.target = Settings.WEB_TARGET
        self.last_renewal = 0
        self.renewal_interval = 30
        self.lock = threading.Lock()
        self._renewing = False
        self.max_retries = Settings.MAX_RETRIES
        
        # Browser fingerprint data
        self.browser_data = {
            'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'plugins': 'PDF Viewer,Chrome PDF Viewer,Chromium PDF Viewer,Microsoft Edge PDF Viewer,WebKit built-in PDF',
            'resolution': '1920x1080'
        }
        
        # Initialize browser with fingerprinting
        self._init_browser()
    
    def _init_browser(self):
        """Initialize undetected Chrome with fingerprinting"""
        try:
            options = uc.ChromeOptions()
            
            # Set fingerprinting headers and preferences
            options.add_argument(f'--user-agent={self.browser_data["user_agent"]}')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-infobars')
            options.add_argument('--disable-web-security')
            options.add_argument('--disable-site-isolation-trials')
            options.add_argument('--disable-features=IsolateOrigins,site-per-process')
            
            # Add headless mode arguments
            options.add_argument('--headless=new')  # New headless mode
            options.add_argument('--disable-gpu')
            options.add_argument('--no-sandbox')
            options.add_argument('--window-size=1920,1080')
            
            # Configure experimental options
            prefs = {
                'profile.default_content_setting_values': {
                    'images': 2,  # Disable images for faster loading
                    'plugins': 2,  # Disable plugins
                    'popups': 2,  # Disable popups
                    'geolocation': 2,  # Disable geolocation
                    'notifications': 2  # Disable notifications
                },
                'credentials_enable_service': False,
                'profile.password_manager_enabled': False
            }
            options.add_experimental_option('prefs', prefs)
            
            # Initialize undetected Chrome with auto version detection
            self.driver = uc.Chrome(
                options=options,
                use_subprocess=True,
                version_main=132  # Match the installed Chrome version
            )
            
            # Set browser fingerprinting properties via JavaScript
            self._set_browser_fingerprint()
            
            # Initial page load to establish session
            self.driver.get(self.target)
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )
            self.last_renewal = time.time()
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {str(e)}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            raise
    
    def _set_browser_fingerprint(self):
        """Set browser fingerprint using JavaScript execution"""
        fingerprint_script = f"""
        Object.defineProperty(navigator, 'webdriver', {{
            get: () => false
        }});
        
        Object.defineProperty(navigator, 'plugins', {{
            get: () => [{self._format_plugins()}]
        }});
        
        Object.defineProperty(screen, 'width', {{ value: {self.browser_data['resolution'].split('x')[0]} }});
        Object.defineProperty(screen, 'height', {{ value: {self.browser_data['resolution'].split('x')[1]} }});
        """
        
        self.driver.execute_script(fingerprint_script)
    
    def _format_plugins(self):
        """Format plugins data for JavaScript injection"""
        return ",".join([
            f"{{'name': '{p}', 'description': '{p}', 'filename': '{p}.plugin'}}" 
            for p in self.browser_data['plugins'].split(',')
        ])
    
    def ensure_valid_cookies(self) -> bool:
        """
        Ensure browser session is valid and renew if necessary
        
        Returns:
            bool: True if session is valid, False otherwise
        """
        with self.lock:
            if self._renewing:
                time.sleep(2)
                return True
            
            if time.time() - self.last_renewal > self.renewal_interval:
                return self._renew_session()
            
            try:
                self.driver.get(self.target)
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, 'body'))
                )
                return True
            except (TimeoutException, WebDriverException) as e:
                logger.error(f"Session validation failed: {str(e)}")
                return self._renew_session()
    
    def _renew_session(self) -> bool:
        """
        Renew browser session and cookies
        
        Returns:
            bool: True if renewal successful, False otherwise
        """
        self._renewing = True
        retry_count = 0
        
        try:
            while retry_count < self.max_retries:
                try:
                    logger.info(f"Renewing session (attempt {retry_count + 1})")
                    
                    # Clean up old session
                    if self.driver:
                        self.driver.quit()
                    
                    # Initialize new session
                    self._init_browser()
                    
                    # Navigate through verification steps
                    self._pass_verification_steps()
                    
                    self.last_renewal = time.time()
                    logger.info("Session renewal successful")
                    return True
                
                except Exception as e:
                    logger.error(f"Renewal attempt failed: {str(e)}")
                    retry_count += 1
                    time.sleep(2 ** retry_count)
        
        finally:
            self._renewing = False
        
        return False
    
    def _pass_verification_steps(self):
        """Handle potential verification steps"""
        try:
            # Initial page load
            self.driver.get(self.target)
            
            # Wait for page to be fully loaded
            WebDriverWait(self.driver, 30).until(
                lambda d: d.execute_script(
                    'return document.readyState === "complete"'
                )
            )
            
            # Check for challenge iframe
            if self._is_challenge_present():
                self._solve_challenge()
            
            # Verify successful access
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )
            
        except TimeoutException:
            raise Exception("Timeout during verification steps")
    
    def _is_challenge_present(self):
        """Check for Cloudflare challenge elements"""
        try:
            return self.driver.find_element(By.ID, 'challenge-form') is not None
        except:
            return False
    
    def _solve_challenge(self):
        """Automate challenge solving"""
        logger.info("Solving Cloudflare challenge...")
        time.sleep(5)  # Allow challenge to fully load
        
        try:
            # Click verify button if present
            verify_button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, '//input[@type="checkbox"]'))
            )
            verify_button.click()
            time.sleep(5)  # Wait for verification
            
        except Exception as e:
            logger.error(f"Failed to solve challenge: {str(e)}")
            raise
    
    def get(self, url: str, **kwargs) -> Optional[str]:
        """
        Make a request using the undetected browser
        
        Args:
            url: The URL to request
            **kwargs: Additional arguments (ignored in this implementation)
            
        Returns:
            Optional[str]: The page source if successful, None otherwise
        """
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.TAG_NAME, 'body'))
            )
            return self.driver.page_source
        except Exception as e:
            logger.error(f"Failed to load {url}: {str(e)}")
            return None
    
    def __del__(self):
        """Clean up browser instance on deletion"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass 