"""
Browser management using Playwright for AHPRA scraper.
"""

import random
from typing import Optional
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from loguru import logger

from config.settings import (
    HEADLESS,
    BROWSER_TIMEOUT,
    PAGE_LOAD_TIMEOUT,
    VIEWPORT_WIDTH,
    VIEWPORT_HEIGHT,
    USER_AGENTS,
)


class BrowserManager:
    """
    Manages Playwright browser instances for web scraping.
    """

    def __init__(self, headless: bool = None):
        """
        Initialize browser manager.

        Args:
            headless: Run browser in headless mode (default from settings)
        """
        self.headless = headless if headless is not None else HEADLESS
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._user_agent = None

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def start(self) -> None:
        """
        Start the browser and create a new context and page.
        """
        logger.info(f"Starting browser (headless={self.headless})")

        self.playwright = sync_playwright().start()

        # Use Chromium for best compatibility
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )

        # Rotate user agent
        self._user_agent = random.choice(USER_AGENTS)

        # Create context with custom settings
        self.context = self.browser.new_context(
            viewport={'width': VIEWPORT_WIDTH, 'height': VIEWPORT_HEIGHT},
            user_agent=self._user_agent,
            locale='en-AU',
            timezone_id='Australia/Sydney',
        )

        # Set default timeouts
        self.context.set_default_timeout(BROWSER_TIMEOUT)
        self.context.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT)

        # Create page
        self.page = self.context.new_page()

        logger.info(f"Browser started with user agent: {self._user_agent[:50]}...")

    def close(self) -> None:
        """
        Close the browser and cleanup resources.
        """
        logger.info("Closing browser")

        if self.page:
            self.page.close()
            self.page = None

        if self.context:
            self.context.close()
            self.context = None

        if self.browser:
            self.browser.close()
            self.browser = None

        if self.playwright:
            self.playwright.stop()
            self.playwright = None

    def navigate(self, url: str, wait_until: str = "networkidle") -> bool:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: Wait condition ('load', 'domcontentloaded', 'networkidle')

        Returns:
            True if navigation successful, False otherwise
        """
        try:
            logger.debug(f"Navigating to: {url}")
            self.page.goto(url, wait_until=wait_until)
            return True
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False

    def wait_for_selector(self, selector: str, timeout: int = None) -> bool:
        """
        Wait for a selector to appear on the page.

        Args:
            selector: CSS selector to wait for
            timeout: Custom timeout in milliseconds

        Returns:
            True if element found, False otherwise
        """
        try:
            self.page.wait_for_selector(selector, timeout=timeout or BROWSER_TIMEOUT)
            return True
        except Exception as e:
            logger.warning(f"Selector not found: {selector} - {e}")
            return False

    def get_page_content(self) -> str:
        """
        Get the current page's HTML content.

        Returns:
            HTML content string
        """
        return self.page.content()

    def fill_input(self, selector: str, value: str) -> bool:
        """
        Fill an input field.

        Args:
            selector: CSS selector for input
            value: Value to fill

        Returns:
            True if successful, False otherwise
        """
        try:
            self.page.fill(selector, value)
            return True
        except Exception as e:
            logger.error(f"Failed to fill input {selector}: {e}")
            return False

    def click(self, selector: str) -> bool:
        """
        Click an element.

        Args:
            selector: CSS selector for element

        Returns:
            True if successful, False otherwise
        """
        try:
            self.page.click(selector)
            return True
        except Exception as e:
            logger.error(f"Failed to click {selector}: {e}")
            return False

    def select_option(self, selector: str, value: str = None, label: str = None) -> bool:
        """
        Select an option from a dropdown.

        Args:
            selector: CSS selector for select element
            value: Option value to select
            label: Option label to select

        Returns:
            True if successful, False otherwise
        """
        try:
            if value:
                self.page.select_option(selector, value=value)
            elif label:
                self.page.select_option(selector, label=label)
            return True
        except Exception as e:
            logger.error(f"Failed to select option in {selector}: {e}")
            return False

    def get_elements(self, selector: str) -> list:
        """
        Get all elements matching a selector.

        Args:
            selector: CSS selector

        Returns:
            List of element handles
        """
        return self.page.query_selector_all(selector)

    def get_element_text(self, selector: str) -> Optional[str]:
        """
        Get text content of an element.

        Args:
            selector: CSS selector

        Returns:
            Text content or None
        """
        try:
            element = self.page.query_selector(selector)
            if element:
                return element.text_content()
        except Exception as e:
            logger.debug(f"Failed to get text for {selector}: {e}")
        return None

    def get_element_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """
        Get attribute value of an element.

        Args:
            selector: CSS selector
            attribute: Attribute name

        Returns:
            Attribute value or None
        """
        try:
            element = self.page.query_selector(selector)
            if element:
                return element.get_attribute(attribute)
        except Exception as e:
            logger.debug(f"Failed to get attribute {attribute} for {selector}: {e}")
        return None

    def screenshot(self, path: str) -> None:
        """
        Take a screenshot of the current page.

        Args:
            path: Path to save screenshot
        """
        self.page.screenshot(path=path)
        logger.debug(f"Screenshot saved to: {path}")

    def rotate_user_agent(self) -> None:
        """
        Rotate to a new user agent by creating a new context.
        """
        logger.info("Rotating user agent")

        # Close current page and context
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()

        # Create new context with different user agent
        self._user_agent = random.choice(USER_AGENTS)
        self.context = self.browser.new_context(
            viewport={'width': VIEWPORT_WIDTH, 'height': VIEWPORT_HEIGHT},
            user_agent=self._user_agent,
            locale='en-AU',
            timezone_id='Australia/Sydney',
        )
        self.context.set_default_timeout(BROWSER_TIMEOUT)
        self.context.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT)
        self.page = self.context.new_page()

        logger.info(f"New user agent: {self._user_agent[:50]}...")
