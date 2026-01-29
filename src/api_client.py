"""
AHPRA API Client - HTTP-based practitioner data fetching

Updated with proper browser fingerprinting headers to avoid CAPTCHA/WAF blocking.
Key additions: Sec-Fetch headers, proper session flow, Content-Type on POST.
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
        self.consecutive_failures = 0  # Track failures for adaptive delays
        self.last_request_time = 0  # Track timing

    def _setup_session(self):
        """Configure session with browser-like headers including Sec-Fetch headers."""
        # Use Mac Chrome user agent consistently (working scraper uses this)
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        self.session.headers.update({
            'User-Agent': ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-AU,en;q=0.9,en-US;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            # Critical Sec-Fetch headers for WAF bypass
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            # Additional browser headers
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        })

    def _init_cookies(self):
        """
        Initialize session cookies by visiting the search page first.
        CRITICAL: Updates headers after GET to simulate real browser behavior.
        """
        if self._cookies_initialized:
            return True

        try:
            logger.debug("Initializing session cookies...")
            response = self.session.get(AHPRA_SEARCH_URL, timeout=30)
            if response.status_code == 200:
                # CRITICAL: Update headers after initial GET (like a real browser)
                self.session.headers.update({
                    'Origin': 'https://www.ahpra.gov.au',
                    'Referer': AHPRA_SEARCH_URL,
                    'Sec-Fetch-Site': 'same-origin',  # Changes from 'none' to 'same-origin'
                })
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
        """
        Apply adaptive delay between requests - stays below WAF threshold.

        Strategy (from working scraper analysis):
        - Base delay: 15s = ~4 req/min (well below 20 req/min WAF threshold)
        - Adaptive backoff: +5s per consecutive failure (15s → 20s → 25s → 30s)
        - This ensures we never spike above WAF detection threshold
        """
        # Base delay of 15s keeps us at ~4 req/min (WAF threshold is ~20 req/min)
        base_delay = 15
        adaptive_extra = self.consecutive_failures * 5  # Add 5s per failure
        delay = base_delay + adaptive_extra

        # Add small randomization (±2s) to avoid pattern detection
        delay += random.uniform(-2, 2)
        delay = max(13, delay)  # Never go below 13s

        # Ensure minimum time since last request
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < delay:
            sleep_time = delay - time_since_last
            logger.debug(f"Throttling: waiting {sleep_time:.1f}s (base={base_delay}, adaptive=+{adaptive_extra})")
            time.sleep(sleep_time)

        self.last_request_time = time.time()

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
        
        # Explicit Content-Type header for POST (critical for WAF)
        post_headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        for attempt in range(MAX_RETRIES):
            try:
                self._apply_delay()

                response = self.session.post(
                    AHPRA_SEARCH_URL,
                    data=data,
                    headers=post_headers,
                    timeout=30,
                )

                if response.status_code == 200:
                    # Check for blocking indicators
                    html = response.text
                    if 'Request Rejected' in html or len(html) < 500:
                        logger.warning(f"Blocked response for {reg_id} (Request Rejected or too short)")
                        self.consecutive_failures += 1
                        continue
                    
                    # Success - reset failure counter
                    self.consecutive_failures = 0
                    logger.debug(f"Fetched {reg_id} successfully ({len(html)} bytes)")
                    return html
                else:
                    self.consecutive_failures += 1
                    logger.warning(f"HTTP {response.status_code} for {reg_id}")
                    if response.text:
                        logger.debug(f"Response body: {response.text[:500]}...")

            except requests.exceptions.Timeout:
                self.consecutive_failures += 1
                logger.warning(f"Timeout fetching {reg_id} (attempt {attempt + 1}/{MAX_RETRIES})")
            except requests.exceptions.RequestException as e:
                self.consecutive_failures += 1
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
