import os
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options

def get_chrome_options():
    """
    Configure Chrome options for the Render.com environment
    """
    chrome_options = uc.ChromeOptions()
    
    # Set Chrome version to match the installed version
    chrome_version = os.getenv('CHROME_VERSION', '131.0.6778.204')
    chrome_options.browser_version = chrome_version
    
    # Required for running in Docker
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    # Set binary location if specified in environment
    chrome_binary = os.getenv('CHROME_BIN')
    if chrome_binary:
        chrome_options.binary_location = chrome_binary
    
    return chrome_options

def create_browser():
    """
    Create and configure the Chrome browser instance
    """
    options = get_chrome_options()
    try:
        driver = uc.Chrome(
            options=options,
            driver_executable_path=os.getenv('CHROME_DRIVER_PATH'),
            browser_executable_path=os.getenv('CHROME_BIN'),
            version_main=131  # Match with installed Chrome version
        )
        return driver
    except Exception as e:
        raise Exception(f"Failed to initialize Chrome browser: {str(e)}")