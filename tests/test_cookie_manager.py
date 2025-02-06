import pytest
from unittest.mock import MagicMock, patch
from src.core.cookie_manager import CookieManager
from src.config.settings import Settings
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

@pytest.fixture
def mock_element():
    """Fixture to create a mock web element"""
    element = MagicMock()
    element.is_displayed.return_value = True
    element.get_attribute.return_value = "test"
    element.click.return_value = None
    return element

@pytest.fixture
def mock_driver(mock_element):
    """Fixture to create a mock Chrome driver"""
    driver = MagicMock()
    driver.page_source = "<html><body>Test content</body></html>"
    
    # Mock find_element to return our mock element
    driver.find_element.return_value = mock_element
    
    # Mock execute_script for fingerprinting and readyState
    def mock_execute_script(script):
        if 'document.readyState' in script:
            return 'complete'
        return None
    
    driver.execute_script.side_effect = mock_execute_script
    
    return driver

@pytest.fixture
def mock_webdriver_wait():
    """Create a WebDriverWait class mock that can be configured per test"""
    class MockWebDriverWait:
        def __init__(self, driver, timeout):
            self.driver = driver
            self.timeout = timeout
            self.mock_element = MagicMock()
            self.mock_element.is_displayed.return_value = True
        
        def until(self, condition):
            # Handle different types of conditions
            if isinstance(condition, type(EC.presence_of_element_located)):
                return self.mock_element
            elif callable(condition):
                # For custom lambda conditions
                return condition(self.driver)
            return True
    
    return MockWebDriverWait

@pytest.fixture
def cookie_manager(mock_driver, mock_webdriver_wait):
    """Fixture to create a cookie manager instance with mocked browser"""
    with patch('undetected_chromedriver.Chrome', return_value=mock_driver), \
         patch('selenium.webdriver.support.wait.WebDriverWait', mock_webdriver_wait):
        manager = CookieManager()
        yield manager
        if manager.driver:
            manager.driver.quit()

def test_cookie_manager_initialization(cookie_manager, mock_driver):
    """Test that cookie manager initializes correctly"""
    assert cookie_manager.driver == mock_driver
    assert cookie_manager.target == Settings.WEB_TARGET
    assert cookie_manager._renewing is False
    assert cookie_manager.renewal_interval == 30

@pytest.mark.parametrize("challenge_present,expected_result", [
    (False, True),  # No challenge case
    (True, True),   # Challenge present but solved
])
def test_ensure_valid_cookies(cookie_manager, mock_driver, challenge_present, expected_result):
    """Test that cookie manager can establish a valid session"""
    # Setup mock behavior for find_element
    def mock_find_element(by, value):
        if by == By.ID and value == 'challenge-form':
            return MagicMock() if challenge_present else None
        return MagicMock()  # Return mock element for other queries
    
    mock_driver.find_element.side_effect = mock_find_element
    
    # Setup mock behavior for execute_script
    mock_driver.execute_script.return_value = 'complete'
    
    is_valid = cookie_manager.ensure_valid_cookies()
    assert is_valid is expected_result
    
    # Verify driver interactions
    mock_driver.get.assert_called_with(Settings.WEB_TARGET)

def test_session_renewal(cookie_manager, mock_driver):
    """Test that cookie manager can renew session"""
    # Force a session renewal
    cookie_manager.last_renewal = 0
    
    # Setup mock behavior for successful renewal
    mock_driver.execute_script.return_value = True
    
    is_renewed = cookie_manager._renew_session()
    assert is_renewed is True
    assert cookie_manager.last_renewal > 0
    
    # Verify browser was reinitialized
    mock_driver.quit.assert_called()

@pytest.mark.parametrize("test_url,expected_content", [
    (Settings.WEB_TARGET, "<html><body>Test content</body></html>"),
    ("https://test.com", "<html><body>Test content</body></html>"),
])
def test_get_request(cookie_manager, mock_driver, test_url, expected_content):
    """Test that cookie manager can handle get requests"""
    content = cookie_manager.get(test_url)
    assert content == expected_content
    mock_driver.get.assert_called_with(test_url)

def test_multiple_requests(cookie_manager, mock_driver):
    """Test that cookie manager can handle multiple requests"""
    # Make multiple requests to test session stability
    for _ in range(3):
        content = cookie_manager.get(Settings.WEB_TARGET)
        assert content == "<html><body>Test content</body></html>"
        mock_driver.get.assert_called_with(Settings.WEB_TARGET)
        time.sleep(0.1)  # Small delay between requests

if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 