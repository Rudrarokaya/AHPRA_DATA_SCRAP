"""
AHPRA API Client - HTTP-based practitioner data fetching
"""

import random
import time
from typing import Optional

import requests
from loguru import logger

from config.settings import (
    AHPRA_SEARCH_URL,
    USER_AGENTS,
    MIN_DELAY,
    MAX_DELAY,
    MAX_RETRIES,
    RETRY_DELAY,
)


class AHPRAClient:
    """HTTP client for fetching practitioner data from AHPRA API."""

    def __init__(self):
        self.session = requests.Session()
        self._setup_session()
        self.request_count = 0
        self._cookies_initialized = False

    def _setup_session(self):
        """Configure session with default headers."""
        self.session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-AU,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': AHPRA_SEARCH_URL,
            'Origin': 'https://www.ahpra.gov.au',
        })
        self._rotate_user_agent()

    def _init_cookies(self):
        """Initialize session cookies by visiting the search page first."""
        if self._cookies_initialized:
            return True

        try:
            logger.debug("Initializing session cookies...")
            response = self.session.get(AHPRA_SEARCH_URL, timeout=30)
            if response.status_code == 200:
                self._cookies_initialized = True
                logger.debug(f"Cookies initialized: {len(self.session.cookies)} cookies")
                return True
            else:
                logger.warning(f"Failed to init cookies: HTTP {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"Failed to init cookies: {e}")
            return False

    def _rotate_user_agent(self):
        """Rotate to a random user agent."""
        ua = random.choice(USER_AGENTS)
        self.session.headers['User-Agent'] = ua

    def _apply_delay(self):
        """Apply random delay between requests."""
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        time.sleep(delay)

    def fetch_practitioner(self, reg_id: str) -> Optional[str]:
        """
        Fetch practitioner details via POST request.

        Args:
            reg_id: Practitioner registration ID (e.g., NMW0001234567)

        Returns:
            HTML content of the practitioner detail page, or None on failure
        """
        # Initialize session cookies if not done
        if not self._cookies_initialized:
            self._init_cookies()

        # Rotate user agent periodically
        self.request_count += 1
        if self.request_count % 10 == 0:
            self._rotate_user_agent()

        # Form data for POST request
        data = {
            'health-profession': '',
            'state': '',
            'suburb': '',
            'postcode': '',
            'name-reg': '',
            'practitioner-row-id': reg_id,
        }

        for attempt in range(MAX_RETRIES):
            try:
                self._apply_delay()

                response = self.session.post(
                    AHPRA_SEARCH_URL,
                    data=data,
                    timeout=30,
                )

                if response.status_code == 200:
                    logger.debug(f"Fetched {reg_id} successfully ({len(response.text)} bytes)")
                    return response.text
                else:
                    logger.warning(f"HTTP {response.status_code} for {reg_id}")

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout fetching {reg_id} (attempt {attempt + 1}/{MAX_RETRIES})")
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error for {reg_id}: {e} (attempt {attempt + 1}/{MAX_RETRIES})")

            # Wait before retry
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)

        logger.error(f"Failed to fetch {reg_id} after {MAX_RETRIES} attempts")
        return None

    def test_connection(self) -> bool:
        """Test if AHPRA API is accessible."""
        try:
            response = self.session.get(AHPRA_SEARCH_URL, timeout=10)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def close(self):
        """Close the session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
