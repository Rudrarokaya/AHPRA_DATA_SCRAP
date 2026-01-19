"""
Stage 1: Discovery module for AHPRA scraper.

Discovers all practitioner URLs by:
1. Using recursive prefix search on names
2. Collecting registration IDs and profile URLs
3. Saving progress for resumability
"""

import re
from typing import List, Dict, Optional, Tuple
from collections import deque
from loguru import logger

from config.settings import (
    AHPRA_SEARCH_URL,
    MAX_RESULTS_PER_PAGE,
    PAGINATION_LIMIT,
    MAX_RETRIES,
    RETRY_DELAY,
)
from config.professions import PROFESSIONS, STATES, STATE_ABBREVIATIONS, ALPHABET, MAJOR_SUBURBS
from src.browser import BrowserManager
from src.checkpoint import CheckpointManager
from src.search import SearchOrchestrator
from src.utils import random_delay, ui_delay, sidebar_filter_delay, get_timestamp


class DiscoveryEngine:
    """
    Discovers practitioner URLs from AHPRA search interface.

    Supports three search modes:
    - Adaptive: Starts with A-Z, expands deeper only when needed
    - Comprehensive: Systematically searches all depths (A-Z, AA-ZZ, AAA-ZZZ)
    - Multi-dimensional: Searches by profession × state × suburb × prefix
    """

    # CSS Selectors for AHPRA page (verified Jan 2026)
    SELECTORS = {
        # Search form elements (HOME PAGE)
        'search_input': '#name-reg',
        'profession_dropdown': '#health-profession-dropdown',
        'state_dropdown': '#state-dropdown',
        'suburb_input': '#suburb',  # Suburb filter (if available)
        'search_button': '#predictiveSearchHomeBtn',
        'name_input_alt': 'input[placeholder*="Name or Registration"]',

        # Results elements
        'results_table': '.search-results-table-body',
        'result_row': '.search-results-table-row[data-practitioner-row-id]',
        'result_count': '.search-results-summary',
        'no_results': '.no-results-message',
        'loading': '.loading, .spinner',

        # Row data extraction
        'practitioner_name': 'a',
        'profession': '.search-results-table-col:nth-child(2) .text p',
        'division': '.col.division .text p',
        'reg_type': '.col.reg-type .text p',
        'location': '.search-results-table-col:last-child .text p',

        # Pagination
        'load_more': 'button:has-text("Load more"), .load-more-btn',
        'next_page': 'button:has-text("Load more"), .load-more-btn, .pagination .next',
        'pagination': '.pagination',

        # SIDEBAR FILTERS (RESULTS PAGE) - For optimized filtering without page reload
        'sidebar_filters': '.search-results-filters',
        'sidebar_clear_all': '.clear-filters',

        # Sidebar: Health Profession filter (checkboxes)
        'sidebar_profession_section': '.health-profession-filters',
        'sidebar_profession_title': '.health-profession-filters > a.title',
        'sidebar_profession_list': '.health-profession-filters ul',
        'sidebar_profession_checkbox': 'input[name^="health-profession-"]',

        # Sidebar: Location/State filter (custom dropdown)
        'sidebar_location_section': '.location-filters',
        'sidebar_location_title': '.location-filters > a.title',
        'sidebar_state_dropdown': '.location-filters #state-dropdown',
        'sidebar_state_select': '.location-filters #state-dropdown .select',
        'sidebar_state_options': '.location-filters #state-dropdown ul li span',
        'sidebar_suburb_input': '#suburb-postcode',

        # Sidebar: Sex filter (radio buttons)
        'sidebar_sex_section': '.sex-filters',
        'sidebar_sex_radio': 'input[name="gender-select"]',

        # CAPTCHA detection selectors
        'captcha_iframe': 'iframe[src*="recaptcha"], iframe[src*="captcha"], iframe[title*="reCAPTCHA"]',
        'captcha_checkbox': '.recaptcha-checkbox, .g-recaptcha',
        'captcha_challenge': '#recaptcha, .g-recaptcha, [class*="captcha"]',
        'captcha_text': 'text="I\'m not a robot", text="verify you are human"',
    }

    # Profession checkbox ID mapping (matches AHPRA's IDs)
    PROFESSION_CHECKBOX_IDS = {
        "Aboriginal and Torres Strait Islander Health Practitioner": "001",
        "Chinese Medicine Practitioner": "002",
        "Chiropractor": "003",
        "Dental Practitioner": "004",
        "Medical Practitioner": "005",
        "Medical Radiation Practitioner": "006",
        "Midwife": "007",
        "Nurse": "008",
        "Occupational Therapist": "009",
        "Optometrist": "010",
        "Osteopath": "011",
        "Paramedic": "012",
        "Pharmacist": "013",
        "Physiotherapist": "014",
        "Podiatrist": "015",
        "Psychologist": "016",
    }

    def __init__(
        self,
        browser: BrowserManager,
        checkpoint: CheckpointManager,
        comprehensive: bool = False,
        multi_dimensional: bool = False,
        include_suburbs: bool = False,
        max_depth: int = 3,
        test_prefix: Optional[str] = None,
        use_optimized: bool = True  # NEW: Use sidebar filters for faster discovery
    ):
        """
        Initialize discovery engine.

        Args:
            browser: Browser manager instance
            checkpoint: Checkpoint manager instance
            comprehensive: Use comprehensive search (all depths) vs adaptive
            multi_dimensional: Use multi-dimensional search (profession × state × prefix)
            include_suburbs: Include suburb-level searches (multi-dimensional only)
            max_depth: Maximum prefix depth (1-4, default 3 for AAA-ZZZ)
            test_prefix: Optional single prefix for testing (e.g., 'A')
            use_optimized: Use sidebar filters for faster discovery (default True)
                          When True, only navigates to home page once per prefix,
                          then uses sidebar filters to change profession/state.
        """
        self.browser = browser
        self.checkpoint = checkpoint
        self.comprehensive = comprehensive
        self.multi_dimensional = multi_dimensional
        self.include_suburbs = include_suburbs
        self.max_depth = max_depth
        self.test_prefix = test_prefix
        self.use_optimized = use_optimized
        self.orchestrator = SearchOrchestrator(
            comprehensive=comprehensive,
            multi_dimensional=multi_dimensional,
            include_suburbs=include_suburbs,
            max_depth=max_depth,
            test_prefix=test_prefix
        )
        self._search_queue = deque()
        self._combination_queue = deque()  # For multi-dimensional search
        self._retry_counts: Dict[str, int] = {}  # Track retries per combination/prefix

    def initialize(self) -> bool:
        """
        Initialize the discovery engine by navigating to search page.

        Returns:
            True if successful
        """
        logger.info("Initializing discovery engine")

        # Use 'domcontentloaded' instead of 'networkidle' for faster initial load
        if not self.browser.navigate(AHPRA_SEARCH_URL, wait_until='domcontentloaded'):
            logger.error("Failed to navigate to AHPRA search page")
            return False

        # Wait for page to stabilize (server was just hit, use main delay)
        random_delay()

        # Verify the search form is present
        logger.info(f"Page loaded: {self.browser.page.url}")

        logger.info("Discovery engine initialized")
        return True

    def run_discovery(self, resume: bool = True) -> int:
        """
        Run the discovery process.

        Args:
            resume: Whether to resume from checkpoint

        Returns:
            Number of practitioners discovered
        """
        logger.info("Starting discovery process")

        # Load checkpoint if resuming
        if resume:
            self.checkpoint.load()

        self.checkpoint.start_session()

        # Use multi-dimensional or prefix-based discovery
        if self.multi_dimensional:
            # Use optimized sidebar filter approach if enabled
            if self.use_optimized:
                logger.info("Using OPTIMIZED sidebar filter mode (faster)")
                return self._run_optimized_multi_dimensional_discovery()
            else:
                logger.info("Using STANDARD multi-dimensional mode (navigates home for each combination)")
                return self._run_multi_dimensional_discovery()
        else:
            return self._run_prefix_discovery()

    def _run_prefix_discovery(self) -> int:
        """Run prefix-based discovery (adaptive or comprehensive mode)."""
        # Initialize search queue
        initial_prefixes = self.orchestrator.get_discovery_queue(
            self.checkpoint.completed_prefixes
        )
        self._search_queue = deque(initial_prefixes)

        # Resume from current position if applicable
        if self.checkpoint.current_prefix:
            # Put current prefix at front of queue
            if self.checkpoint.current_prefix in self._search_queue:
                self._search_queue.remove(self.checkpoint.current_prefix)
            self._search_queue.appendleft(self.checkpoint.current_prefix)

        total_discovered = self.checkpoint.stats['total_discovered']
        logger.info(f"Queue initialized with {len(self._search_queue)} prefixes")

        while self._search_queue:
            prefix = self._search_queue.popleft()

            # Skip if already completed
            if self.checkpoint.is_prefix_completed(prefix):
                continue

            logger.info(f"Searching prefix: '{prefix}' (queue size: {len(self._search_queue)})")

            try:
                count = self._search_prefix(prefix)

                # Check if we need to expand this prefix
                children = self.orchestrator.handle_search_result(
                    prefix, count, self.checkpoint.completed_prefixes
                )

                if children:
                    # Add children to front of queue
                    for child in reversed(children):
                        self._search_queue.appendleft(child)
                else:
                    # Mark prefix as completed
                    self.checkpoint.mark_prefix_completed(prefix)

                # Save checkpoint periodically
                self.checkpoint.auto_save_if_needed()

            except Exception as e:
                logger.error(f"Error searching prefix '{prefix}': {e}")
                self.checkpoint.increment_errors()

                # Track retry count
                self._retry_counts[prefix] = self._retry_counts.get(prefix, 0) + 1

                if self._retry_counts[prefix] < MAX_RETRIES:
                    # Re-add to end of queue for retry
                    logger.info(f"Retrying prefix '{prefix}' (attempt {self._retry_counts[prefix] + 1}/{MAX_RETRIES})")
                    self._search_queue.append(prefix)
                else:
                    # Max retries reached, skip this prefix
                    logger.warning(f"Skipping prefix '{prefix}' after {MAX_RETRIES} failed attempts")

                random_delay(RETRY_DELAY, RETRY_DELAY * 2)

        # Final save and cleanup
        self.checkpoint.save()
        self.checkpoint.close_raw_backup()

        new_discovered = self.checkpoint.stats['total_discovered'] - total_discovered
        logger.info(f"Discovery complete. New practitioners found: {new_discovered}")

        return new_discovered

    def _run_multi_dimensional_discovery(self) -> int:
        """Run multi-dimensional discovery (profession × state × suburb × prefix)."""
        # Initialize combination queue
        combinations = self.orchestrator.get_multi_dimensional_queue(
            self.checkpoint.completed_combinations
        )
        self._combination_queue = deque(combinations)

        total_discovered = self.checkpoint.stats['total_discovered']
        total_combinations = len(self._combination_queue)
        logger.info(f"Multi-dimensional queue: {total_combinations:,} combinations")

        processed = 0
        while self._combination_queue:
            profession, state, suburb, prefix = self._combination_queue.popleft()

            # Create combination key
            combo_key = self.checkpoint.make_combination_key(profession, state, prefix, suburb)

            # Skip if already completed
            if self.checkpoint.is_combination_completed(combo_key):
                continue

            # Log progress
            processed += 1
            remaining = len(self._combination_queue)
            if suburb:
                logger.info(
                    f"[{processed}/{total_combinations}] Searching: {profession} | {state} | {suburb} | '{prefix}'"
                )
            else:
                logger.info(
                    f"[{processed}/{total_combinations}] Searching: {profession} | {state} | '{prefix}'"
                )

            try:
                self.checkpoint.set_current_combination(combo_key)

                # Search with all filters
                count = self._search_combination(prefix, profession, state, suburb)

                # Mark combination as completed
                self.checkpoint.mark_combination_completed(combo_key)

                # Save checkpoint after each combination (more reliable for long-running processes)
                self.checkpoint.save()

                # Log discovery count periodically
                if processed % 50 == 0:
                    current_discovered = self.checkpoint.stats['total_discovered']
                    new_so_far = current_discovered - total_discovered
                    logger.info(f"Progress: {processed}/{total_combinations} | New discoveries: {new_so_far:,}")

            except Exception as e:
                logger.error(f"Error searching combination '{combo_key}': {e}")
                self.checkpoint.increment_errors()

                # Track retry count
                self._retry_counts[combo_key] = self._retry_counts.get(combo_key, 0) + 1

                if self._retry_counts[combo_key] < MAX_RETRIES:
                    # Re-add to end of queue for retry
                    logger.info(f"Retrying combination '{combo_key}' (attempt {self._retry_counts[combo_key] + 1}/{MAX_RETRIES})")
                    self._combination_queue.append((profession, state, suburb, prefix))
                else:
                    # Max retries reached, skip this combination
                    logger.warning(f"Skipping combination '{combo_key}' after {MAX_RETRIES} failed attempts")

                random_delay(RETRY_DELAY, RETRY_DELAY * 2)

        # Final save and cleanup
        self.checkpoint.save()
        self.checkpoint.close_raw_backup()

        new_discovered = self.checkpoint.stats['total_discovered'] - total_discovered
        logger.info(f"Multi-dimensional discovery complete. New practitioners found: {new_discovered:,}")

        return new_discovered

    def _search_combination(
        self,
        prefix: str,
        profession: str,
        state: str,
        suburb: Optional[str] = None
    ) -> int:
        """
        Search for practitioners with specific profession/state/suburb/prefix.

        Args:
            prefix: Name prefix to search
            profession: Profession filter
            state: State filter
            suburb: Optional suburb filter

        Returns:
            Total number of results found
        """
        # Navigate to fresh search page
        if not self.browser.navigate(AHPRA_SEARCH_URL, wait_until='domcontentloaded'):
            logger.warning("Failed to navigate to search page")
            return 0

        random_delay()

        # Perform search with filters
        if not self._perform_search(prefix, profession, state, suburb):
            logger.warning(f"Search failed for combination")
            return 0

        random_delay()

        # Get result count
        result_count = self._get_result_count()

        if result_count == 0:
            return 0

        # Process all pages
        page = 1
        total_collected = 0

        while page <= PAGINATION_LIMIT:
            # Collect practitioners from current page
            collected = self._collect_practitioners_from_page(prefix)
            total_collected += collected

            logger.debug(f"Page {page}: collected {collected} practitioners")

            # Check for next page
            if not self._has_next_page() or collected == 0:
                break

            # Go to next page
            if not self._go_to_next_page():
                break

            page += 1
            random_delay()

            # Save checkpoint periodically
            if self.checkpoint.should_save(total_collected):
                self.checkpoint.save()

        return result_count

    def _search_prefix(self, prefix: str) -> int:
        """
        Search for practitioners with a given name prefix.

        Args:
            prefix: Name prefix to search

        Returns:
            Total number of results found
        """
        self.checkpoint.set_current_position(prefix, 0)

        # Always navigate to fresh search page to ensure clean state
        logger.debug(f"Navigating to search page for prefix '{prefix}'")
        if not self.browser.navigate(AHPRA_SEARCH_URL, wait_until='domcontentloaded'):
            logger.warning(f"Failed to navigate to search page for prefix '{prefix}'")
            return 0

        # Respectful delay after server navigation
        random_delay()

        # Perform search
        if not self._perform_search(prefix):
            logger.warning(f"Search failed for prefix '{prefix}'")
            return 0

        random_delay()

        # Get result count
        result_count = self._get_result_count()
        logger.info(f"Prefix '{prefix}': {result_count} results")

        if result_count == 0:
            return 0

        # Process all pages
        page = 1
        total_collected = 0

        while page <= PAGINATION_LIMIT:
            self.checkpoint.set_current_position(prefix, page)

            # Collect practitioners from current page
            collected = self._collect_practitioners_from_page(prefix)
            total_collected += collected

            logger.debug(f"Page {page}: collected {collected} practitioners")

            # Check for next page
            if not self._has_next_page() or collected == 0:
                break

            # Go to next page
            if not self._go_to_next_page():
                break

            page += 1
            random_delay()

            # Save checkpoint periodically
            if self.checkpoint.should_save(total_collected):
                self.checkpoint.save()

        return result_count

    def _perform_search(
        self,
        search_term: str,
        profession: str = None,
        state: str = None,
        suburb: str = None
    ) -> bool:
        """
        Perform a search on AHPRA.

        Args:
            search_term: Name or registration number to search
            profession: Optional profession filter
            state: Optional state filter
            suburb: Optional suburb filter

        Returns:
            True if search successful
        """
        try:
            # Find the search input - try primary selector first, then alternative
            search_input = self.browser.page.query_selector(self.SELECTORS['search_input'])
            if not search_input or not search_input.is_visible():
                search_input = self.browser.page.query_selector(self.SELECTORS['name_input_alt'])

            if not search_input:
                logger.warning("Search input not found")
                return False

            # Clear and fill search input (UI interaction - no server hit)
            search_input.click()
            search_input.fill('')
            ui_delay()
            search_input.fill(search_term)
            ui_delay()

            # Set profession filter if specified (custom dropdown)
            if profession:
                if not self._select_from_dropdown(
                    self.SELECTORS['profession_dropdown'],
                    profession
                ):
                    logger.warning(f"Failed to select profession: {profession}")
                    return False

            # Set state filter if specified (custom dropdown)
            # AHPRA uses abbreviations (VIC, NSW, etc.) in the dropdown
            if state:
                state_abbrev = STATE_ABBREVIATIONS.get(state, state)
                logger.debug(f"Selecting state: {state} -> {state_abbrev}")
                if not self._select_from_dropdown(
                    self.SELECTORS['state_dropdown'],
                    state_abbrev
                ):
                    logger.warning(f"Failed to select state: {state} ({state_abbrev})")
                    return False

            # Set suburb filter if specified
            if suburb:
                suburb_input = self.browser.page.query_selector(self.SELECTORS['suburb_input'])
                if suburb_input and suburb_input.is_visible():
                    suburb_input.click()
                    suburb_input.fill('')
                    ui_delay()
                    suburb_input.fill(suburb)
                    ui_delay()

            # Click search button
            search_button = self.browser.page.query_selector(self.SELECTORS['search_button'])
            if search_button and search_button.is_visible():
                search_button.click()
            else:
                # Try pressing Enter in search field
                search_input.press('Enter')

            # Wait for results to load (server was hit, use main delay)
            random_delay()

            # Wait for either results or no-results message
            try:
                self.browser.page.wait_for_selector(
                    '.search-results-table-row[data-practitioner-row-id], .no-results-message',
                    timeout=15000
                )
            except:
                pass

            ui_delay(1, 2)  # Brief pause after selector wait
            return True

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return False

    def _select_from_dropdown(self, dropdown_selector: str, option_text: str) -> bool:
        """
        Select an option from a custom dropdown.

        Args:
            dropdown_selector: CSS selector for the dropdown trigger
            option_text: Text of the option to select

        Returns:
            True if selection successful
        """
        try:
            # Click the dropdown to open it
            dropdown = self.browser.page.query_selector(dropdown_selector)
            if not dropdown:
                logger.debug(f"Dropdown not found: {dropdown_selector}")
                return False

            dropdown.click()
            ui_delay()  # UI interaction

            # Find and click the option
            # Try finding option by text content
            option = self.browser.page.query_selector(f'text="{option_text}"')
            if option and option.is_visible():
                option.click()
                ui_delay()  # UI interaction
                return True

            # Alternative: look for list items
            options = self.browser.page.query_selector_all('li, .dropdown-item, [role="option"]')
            for opt in options:
                if option_text.lower() in (opt.text_content() or '').lower():
                    opt.click()
                    ui_delay()  # UI interaction
                    return True

            logger.debug(f"Option '{option_text}' not found in dropdown")
            return False

        except Exception as e:
            logger.debug(f"Dropdown selection failed: {e}")
            return False

    def _get_result_count(self) -> int:
        """
        Get the total number of search results.

        Returns:
            Result count, or 0 if not found
        """
        try:
            # Count visible result rows (most reliable method)
            result_rows = self.browser.page.query_selector_all(self.SELECTORS['result_row'])
            count = len(result_rows)

            if count > 0:
                return count

            # Fallback: check no results message
            no_results = self.browser.page.query_selector(self.SELECTORS['no_results'])
            if no_results and no_results.is_visible():
                return 0

            return 0

        except Exception as e:
            logger.debug(f"Could not get result count: {e}")
            return 0

    def _collect_practitioners_from_page(self, current_prefix: str) -> int:
        """
        Collect practitioner reg_ids from the current results page.

        Only extracts registration IDs - full data will be fetched
        via API in the extraction stage.

        Args:
            current_prefix: Current search prefix (for logging)

        Returns:
            Number of practitioners collected
        """
        collected = 0

        try:
            # Get all result rows with data-practitioner-row-id attribute
            result_rows = self.browser.page.query_selector_all(self.SELECTORS['result_row'])

            for row in result_rows:
                try:
                    # Get registration ID from data attribute
                    reg_id = row.get_attribute('data-practitioner-row-id')
                    if not reg_id:
                        continue

                    # Save reg_id (handles deduplication internally)
                    if self.checkpoint.save_reg_id(reg_id):
                        collected += 1

                except Exception as e:
                    logger.debug(f"Error processing result row: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error collecting practitioners: {e}")

        # IMMEDIATELY save after collecting from page to prevent data loss
        if collected > 0:
            self.checkpoint.save()
            logger.debug(f"Saved {collected} new IDs immediately after page collection")

        return collected

    def _extract_reg_id(self, url: str, item) -> Optional[str]:
        """
        Extract registration ID from URL or result item.

        Args:
            url: Profile URL
            item: Result item element

        Returns:
            Registration ID or None
        """
        # Try to extract from URL (e.g., ?id=MED0001234567)
        match = re.search(r'[?&]id=([A-Z]{3}\d+)', url)
        if match:
            return match.group(1)

        # Try common URL patterns
        match = re.search(r'/([A-Z]{3}\d{10,})', url)
        if match:
            return match.group(1)

        # Try to find in item text
        try:
            text = item.text_content()
            match = re.search(r'([A-Z]{3}\d{10,})', text)
            if match:
                return match.group(1)
        except:
            pass

        return None

    def _extract_profession_from_result(self, item) -> Optional[str]:
        """
        Try to extract profession from result item.

        Args:
            item: Result item element

        Returns:
            Profession name or None
        """
        try:
            text = item.text_content().lower()
            for profession in PROFESSIONS:
                if profession.lower() in text:
                    return profession
        except:
            pass
        return None

    def _has_next_page(self) -> bool:
        """
        Check if there's a next page of results (Load more button).

        Returns:
            True if next page exists
        """
        try:
            # Try multiple selectors for load more / next page
            selectors_to_try = [
                self.SELECTORS['next_page'],
                self.SELECTORS['load_more'],
                'button:has-text("Load more")',
                '.load-more-btn',
            ]

            for selector in selectors_to_try:
                try:
                    next_button = self.browser.page.query_selector(selector)
                    if next_button and next_button.is_visible():
                        # Check if button is disabled
                        disabled = next_button.get_attribute('disabled')
                        aria_disabled = next_button.get_attribute('aria-disabled')
                        if disabled or aria_disabled == 'true':
                            return False
                        return True
                except:
                    continue

        except Exception as e:
            logger.debug(f"Error checking for next page: {e}")

        return False

    def _go_to_next_page(self) -> bool:
        """
        Navigate to the next page of results (click Load more).

        Returns:
            True if successful
        """
        try:
            # Try multiple selectors for load more / next page
            selectors_to_try = [
                self.SELECTORS['next_page'],
                self.SELECTORS['load_more'],
                'button:has-text("Load more")',
                '.load-more-btn',
            ]

            for selector in selectors_to_try:
                try:
                    next_button = self.browser.page.query_selector(selector)
                    if next_button and next_button.is_visible():
                        # Get current row count before clicking
                        current_rows = len(self.browser.page.query_selector_all(self.SELECTORS['result_row']))

                        next_button.click()

                        # Wait for new results to load
                        try:
                            self.browser.page.wait_for_function(
                                f"document.querySelectorAll('{self.SELECTORS['result_row']}').length > {current_rows}",
                                timeout=10000
                            )
                        except:
                            # Fallback: wait for network idle
                            self.browser.page.wait_for_load_state('networkidle', timeout=10000)

                        ui_delay()
                        return True
                except:
                    continue

        except Exception as e:
            logger.debug(f"Failed to go to next page: {e}")

        return False

    def get_progress(self) -> Dict:
        """
        Get current discovery progress.

        Returns:
            Progress dictionary with mode-specific breakdown
        """
        if self.multi_dimensional:
            # Multi-dimensional progress
            return {
                'mode': 'multi_dimensional',
                'queue_size': len(self._combination_queue),
                'completed_combinations': len(self.checkpoint.completed_combinations),
                'total_discovered': self.checkpoint.stats['total_discovered'],
                'current_combination': self.checkpoint.current_combination,
                'errors': self.checkpoint.stats['errors'],
                'include_suburbs': self.include_suburbs,
                'discovery_started_at': self.checkpoint.discovery_started_at,
                'discovery_last_updated': self.checkpoint.discovery_last_updated,
            }
        else:
            # Prefix-based progress
            depth_progress = self.orchestrator.get_progress_by_depth(
                self.checkpoint.completed_prefixes
            )

            return {
                'mode': 'comprehensive' if self.comprehensive else 'adaptive',
                'queue_size': len(self._search_queue),
                'completed_prefixes': len(self.checkpoint.completed_prefixes),
                'total_discovered': self.checkpoint.stats['total_discovered'],
                'current_prefix': self.checkpoint.current_prefix,
                'errors': self.checkpoint.stats['errors'],
                'max_depth': self.max_depth,
                'depth_progress': depth_progress,
                'discovery_started_at': self.checkpoint.discovery_started_at,
                'discovery_last_updated': self.checkpoint.discovery_last_updated,
            }

    # =========================================================================
    # SIDEBAR FILTER METHODS (Optimized - avoids full page navigation)
    # =========================================================================

    def _expand_sidebar_section(self, section_selector: str) -> bool:
        """
        Expand a collapsed sidebar filter section.

        Args:
            section_selector: CSS selector for the section (e.g., '.health-profession-filters')

        Returns:
            True if expanded successfully
        """
        try:
            section = self.browser.page.query_selector(section_selector)
            if not section:
                logger.debug(f"Sidebar section not found: {section_selector}")
                return False

            # Find the title/toggle element
            title = section.query_selector('a.title')
            if not title:
                return True  # Section might already be expanded

            # Check if the content is hidden (collapsed)
            content = section.query_selector('ul.hide, .form-group.hide')
            if content:
                # Click to expand
                title.click()
                ui_delay()

            return True

        except Exception as e:
            logger.debug(f"Failed to expand sidebar section: {e}")
            return False

    def _select_sidebar_profession(self, profession: str, select: bool = True) -> bool:
        """
        Select or deselect a profession checkbox in the sidebar filter.

        Args:
            profession: Profession name (must match PROFESSION_CHECKBOX_IDS keys)
            select: True to check, False to uncheck

        Returns:
            True if successful
        """
        try:
            # Get checkbox ID
            checkbox_id = self.PROFESSION_CHECKBOX_IDS.get(profession)
            if not checkbox_id:
                logger.warning(f"Unknown profession for sidebar filter: {profession}")
                return False

            # Expand the profession section first
            self._expand_sidebar_section(self.SELECTORS['sidebar_profession_section'])
            ui_delay()

            # Find the checkbox using ATTRIBUTE selectors (CSS IDs can't start with digits!)
            # Try multiple selector patterns as AHPRA may use different ID formats
            checkbox_selectors = [
                f'input[id="_{checkbox_id}"]',  # e.g., input[id="_016"]
                f'input[id="{checkbox_id}"]',   # e.g., input[id="016"]
                f'input[name="health-profession-{checkbox_id}"]',  # By name attribute
                f'.health-profession-filters input[id="_{checkbox_id}"]',
                f'.health-profession-filters input[id="{checkbox_id}"]',
            ]

            checkbox = None
            used_selector = None
            for selector in checkbox_selectors:
                try:
                    checkbox = self.browser.page.query_selector(selector)
                    if checkbox:
                        used_selector = selector
                        logger.debug(f"Found profession checkbox with selector: {selector}")
                        break
                except Exception:
                    continue

            if not checkbox:
                logger.debug(f"Profession checkbox not found: {profession} (ID: {checkbox_id})")
                return False

            # Check current state using JavaScript (more reliable for hidden inputs)
            is_checked = self.browser.page.evaluate(
                f'document.querySelector(\'{used_selector}\')?.checked || false'
            )

            # Only act if state needs to change
            if (select and not is_checked) or (not select and is_checked):
                # The actual <input> is often hidden; try clicking the label instead
                # Labels can be: <label for="001">, or the parent <li> element
                label_selectors = [
                    f'label[for="_{checkbox_id}"]',
                    f'label[for="{checkbox_id}"]',
                    f'.health-profession-filters label[for="_{checkbox_id}"]',
                    f'.health-profession-filters label[for="{checkbox_id}"]',
                ]

                clicked = False
                for label_selector in label_selectors:
                    try:
                        label = self.browser.page.query_selector(label_selector)
                        if label and label.is_visible():
                            label.click()
                            clicked = True
                            logger.debug(f"Clicked label for profession: {profession}")
                            break
                    except Exception:
                        continue

                # If label click didn't work, try JavaScript to toggle the checkbox
                if not clicked:
                    try:
                        self.browser.page.evaluate(f'''
                            const cb = document.querySelector('{used_selector}');
                            if (cb) {{
                                cb.checked = {str(select).lower()};
                                cb.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                cb.dispatchEvent(new Event('click', {{ bubbles: true }}));
                            }}
                        ''')
                        logger.debug(f"Used JavaScript to {'select' if select else 'deselect'} profession: {profession}")
                        clicked = True
                    except Exception as js_err:
                        logger.debug(f"JavaScript checkbox toggle failed: {js_err}")

                # As last resort, try clicking the parent <li> element
                if not clicked:
                    try:
                        # Find parent li element and click it
                        parent_li = self.browser.page.evaluate(f'''
                            const cb = document.querySelector('{used_selector}');
                            return cb ? cb.closest('li') : null;
                        ''')
                        if parent_li:
                            self.browser.page.evaluate(f'''
                                const cb = document.querySelector('{used_selector}');
                                if (cb) {{
                                    const li = cb.closest('li');
                                    if (li) li.click();
                                }}
                            ''')
                            logger.debug(f"Clicked parent li for profession: {profession}")
                            clicked = True
                    except Exception:
                        pass

                if not clicked:
                    logger.warning(f"Could not click checkbox for profession: {profession}")
                    return False

                ui_delay()  # Wait for filter to apply

            return True

        except Exception as e:
            logger.debug(f"Failed to select sidebar profession: {e}")
            return False

    def _select_sidebar_state(self, state_abbrev: str) -> bool:
        """
        Select a state from the sidebar location filter dropdown.

        Args:
            state_abbrev: State abbreviation (ACT, NSW, NT, QLD, SA, TAS, VIC, WA)
                         or "All States & Territories" to clear

        Returns:
            True if successful
        """
        try:
            # Expand the location section first
            self._expand_sidebar_section(self.SELECTORS['sidebar_location_section'])
            ui_delay()

            # Click the dropdown to open it
            dropdown_select = self.browser.page.query_selector(self.SELECTORS['sidebar_state_select'])
            if not dropdown_select:
                logger.debug("Sidebar state dropdown not found")
                return False

            dropdown_select.click()
            ui_delay()

            # Find and click the option
            options = self.browser.page.query_selector_all(self.SELECTORS['sidebar_state_options'])
            for option in options:
                text = option.text_content().strip()
                if text == state_abbrev or (state_abbrev == "All" and "All States" in text):
                    option.click()
                    logger.debug(f"Selected sidebar state: {state_abbrev}")
                    return True

            logger.debug(f"State option not found in sidebar: {state_abbrev}")
            return False

        except Exception as e:
            logger.debug(f"Failed to select sidebar state: {e}")
            return False

    def _input_sidebar_suburb(self, suburb: Optional[str]) -> bool:
        """
        Input or clear suburb in the sidebar location filter.

        Args:
            suburb: Suburb name to input, or None/empty to clear

        Returns:
            True if successful
        """
        try:
            # Expand the location section first
            self._expand_sidebar_section(self.SELECTORS['sidebar_location_section'])
            ui_delay()

            # Find the suburb input field
            suburb_input = self.browser.page.query_selector(self.SELECTORS['sidebar_suburb_input'])
            if not suburb_input:
                logger.debug("Sidebar suburb input not found")
                return False

            # Clear existing value first
            suburb_input.click()
            ui_delay()

            # Select all and delete (more reliable than fill(''))
            self.browser.page.keyboard.press('Meta+a')  # Select all (Cmd+A on Mac)
            ui_delay()
            self.browser.page.keyboard.press('Backspace')
            ui_delay()

            if suburb:
                # Input new suburb
                suburb_input.fill(suburb)
                ui_delay()

                # Press Enter to apply filter
                suburb_input.press('Enter')
                logger.debug(f"Input sidebar suburb: {suburb}")
            else:
                # Just clear - press Enter to apply empty filter
                suburb_input.press('Enter')
                logger.debug("Cleared sidebar suburb filter")

            return True

        except Exception as e:
            logger.debug(f"Failed to input sidebar suburb: {e}")
            return False

    def _clear_sidebar_filters(self) -> bool:
        """
        Clear all sidebar filters using the "Clear all filters" link.

        Returns:
            True if successful
        """
        try:
            clear_btn = self.browser.page.query_selector(self.SELECTORS['sidebar_clear_all'])
            if clear_btn:
                clear_btn.click()
                ui_delay()
                logger.debug("Cleared all sidebar filters")
                return True
            return False
        except Exception as e:
            logger.debug(f"Failed to clear sidebar filters: {e}")
            return False

    def _wait_for_results_update(self, timeout: int = 10000) -> bool:
        """
        Wait for search results to update after applying a filter.

        Args:
            timeout: Maximum wait time in milliseconds

        Returns:
            True if results updated
        """
        try:
            # Wait for loading indicator to appear and disappear
            self.browser.page.wait_for_selector(
                self.SELECTORS['loading'],
                state='attached',
                timeout=2000
            )
        except:
            pass  # Loading might be too fast to catch

        try:
            # Wait for loading to finish
            self.browser.page.wait_for_selector(
                self.SELECTORS['loading'],
                state='detached',
                timeout=timeout
            )
        except:
            pass

        # Wait for results table to be present
        try:
            self.browser.page.wait_for_selector(
                self.SELECTORS['results_table'],
                state='attached',
                timeout=timeout
            )
            return True
        except:
            return False

    def _wait_for_page_stable(self, timeout: int = 15000) -> bool:
        """
        Wait for page to be fully stable after a filter causes reload.

        This handles the case where clicking a filter causes a full page navigation.

        Args:
            timeout: Maximum wait time in milliseconds

        Returns:
            True if page is stable and ready
        """
        try:
            # Wait for page load state
            self.browser.page.wait_for_load_state('domcontentloaded', timeout=timeout)

            # Wait for network to be relatively idle
            try:
                self.browser.page.wait_for_load_state('networkidle', timeout=5000)
            except:
                pass  # Network might not go fully idle

            # Wait for results table OR no-results message
            self.browser.page.wait_for_selector(
                f'{self.SELECTORS["results_table"]}, {self.SELECTORS["no_results"]}, {self.SELECTORS["result_row"]}',
                state='attached',
                timeout=timeout
            )

            ui_delay()  # Brief pause for JS to finish
            return True

        except Exception as e:
            logger.debug(f"Page stabilization timeout: {e}")
            return False

    def _verify_sidebar_present(self) -> bool:
        """
        Verify that sidebar filters are present on the page.

        Returns:
            True if sidebar filters are available
        """
        try:
            # Check for profession filter section
            profession_section = self.browser.page.query_selector(
                self.SELECTORS['sidebar_profession_section']
            )
            if profession_section:
                return True

            # Also check for any profession checkbox
            checkbox = self.browser.page.query_selector(
                'input[name^="health-profession-"]'
            )
            return checkbox is not None

        except Exception:
            return False

    def _re_search_prefix(self, prefix: str) -> bool:
        """
        Re-perform search for a prefix after losing page state.

        Args:
            prefix: The prefix to search for

        Returns:
            True if search successful and results found
        """
        logger.debug(f"Re-searching prefix '{prefix}' to restore page state")

        if not self.browser.navigate(AHPRA_SEARCH_URL, wait_until='domcontentloaded'):
            return False

        random_delay()

        if not self._perform_search(prefix):
            return False

        random_delay()

        result_count = self._get_result_count()
        return result_count > 0

    def _apply_sidebar_filter_and_collect(
        self,
        prefix: str,
        profession: str,
        state: str,
        suburb: Optional[str] = None
    ) -> int:
        """
        Apply sidebar filters and collect results (optimized - no page navigation).

        This method assumes we're already on the search results page for the
        given prefix. It uses sidebar filters to refine by profession/state/suburb
        without navigating back to the home page.

        Handles page reloads gracefully - if the page reloads during filter
        application, waits for it to stabilize before continuing.

        Args:
            prefix: Current search prefix (for logging)
            profession: Profession to filter by
            state: State abbreviation to filter by
            suburb: Optional suburb to filter by

        Returns:
            Number of practitioners collected
        """
        state_abbrev = STATE_ABBREVIATIONS.get(state, state)

        try:
            # Verify sidebar is present before starting
            if not self._verify_sidebar_present():
                logger.debug("Sidebar not present, attempting to re-search")
                if not self._re_search_prefix(prefix):
                    logger.warning(f"Failed to restore page state for prefix '{prefix}'")
                    return 0

            # Apply profession filter
            if not self._select_sidebar_profession(profession, select=True):
                logger.warning(f"Failed to select profession filter: {profession}")
                return 0

            # Wait for page to stabilize (filter may cause reload)
            self._wait_for_page_stable()

            # ANTI-CAPTCHA: Add delay after profession filter to appear more human-like
            sidebar_filter_delay()

            # Verify we're still on a valid results page
            if not self._verify_sidebar_present():
                logger.debug("Page reloaded, sidebar lost - waiting for stabilization")
                self._wait_for_page_stable(timeout=20000)

            # Apply state filter
            if not self._select_sidebar_state(state_abbrev):
                logger.debug(f"State filter not applied: {state_abbrev} (may not be available)")
                # Continue anyway - profession filter is applied

            # Wait for page to stabilize again
            self._wait_for_page_stable()

            # ANTI-CAPTCHA: Add delay after state filter
            sidebar_filter_delay()

            # Apply suburb filter if specified
            if suburb:
                # Verify sidebar is still present after state filter
                if not self._verify_sidebar_present():
                    logger.debug("Sidebar lost after state filter, waiting for stabilization")
                    self._wait_for_page_stable(timeout=20000)

                if not self._input_sidebar_suburb(suburb):
                    logger.debug(f"Suburb filter not applied: {suburb} (may not be available)")
                    # Continue anyway - profession and state filters are applied
                else:
                    # Wait for page to stabilize after suburb filter
                    self._wait_for_page_stable()

                    # ANTI-CAPTCHA: Add delay after suburb filter
                    sidebar_filter_delay()

            # Get result count
            result_count = self._get_result_count()
            if result_count == 0:
                filter_desc = f"{profession} | {state_abbrev}"
                if suburb:
                    filter_desc += f" | {suburb}"
                filter_desc += f" | '{prefix}'"
                logger.debug(f"No results for {filter_desc}")
                # Try to clear filters for next iteration
                try:
                    self._select_sidebar_profession(profession, select=False)
                    self._select_sidebar_state("All")
                except Exception:
                    pass  # Page may have reloaded
                return 0

            # Collect all pages
            total_collected = 0
            page = 1

            while page <= PAGINATION_LIMIT:
                collected = self._collect_practitioners_from_page(prefix)
                total_collected += collected

                if not self._has_next_page() or collected == 0:
                    break

                if not self._go_to_next_page():
                    break

                page += 1
                ui_delay()

            filter_desc = f"{profession} | {state_abbrev}"
            if suburb:
                filter_desc += f" | {suburb}"
            filter_desc += f" | '{prefix}'"
            logger.debug(f"Sidebar filter collected: {total_collected} for {filter_desc}")

            # Try to clear filters for next iteration
            try:
                # Clear suburb filter first (if it was applied)
                if suburb:
                    self._input_sidebar_suburb(None)  # Clear suburb
                    self._wait_for_page_stable(timeout=5000)
                    sidebar_filter_delay()

                self._select_sidebar_profession(profession, select=False)
                self._wait_for_page_stable(timeout=5000)
                # ANTI-CAPTCHA: Delay after clearing filter
                sidebar_filter_delay()
            except Exception:
                pass  # Page may have reloaded, will be handled next iteration

            return total_collected

        except Exception as e:
            logger.error(f"Error in sidebar filter collection ({profession} | {state_abbrev}): {e}")
            # Try to recover page state
            try:
                self._wait_for_page_stable(timeout=10000)
            except Exception:
                pass
            return 0

    def _run_optimized_multi_dimensional_discovery(self) -> int:
        """
        Run OPTIMIZED multi-dimensional discovery using sidebar filters.

        This is significantly faster than the standard approach because:
        - Only navigates to home page once per PREFIX (not per combination)
        - Uses sidebar filters to change profession/state/suburb without page reload
        - Reduces full page navigations from (P×S×N) to just (N) where:
          P=professions (16), S=states (8), N=prefixes (26)

        Iteration order: PREFIX → PROFESSION → STATE → SUBURB (if include_suburbs=True)
        """
        # Get prefixes to search
        if self.test_prefix:
            prefixes = [self.test_prefix]
            logger.info(f"OPTIMIZED MODE: Using test prefix '{self.test_prefix}'")
        else:
            prefixes = list(ALPHABET)
            logger.info(f"OPTIMIZED MODE: Searching {len(prefixes)} prefixes (A-Z)")

        total_discovered_start = self.checkpoint.stats['total_discovered']
        professions = PROFESSIONS
        states = STATES

        # Calculate total combinations (with or without suburbs)
        if self.include_suburbs:
            # Count total suburbs across all states
            total_suburbs = sum(len(MAJOR_SUBURBS.get(state, [])) for state in states)
            # Each state has: base search (no suburb) + suburb-specific searches
            total_combinations = len(prefixes) * len(professions) * (len(states) + total_suburbs)
            logger.info(f"Total combinations: {total_combinations:,} ({len(prefixes)} prefixes × {len(professions)} professions × ({len(states)} states + {total_suburbs} suburbs))")
            logger.info("SUBURB MODE ENABLED: Will search by suburb for each state")
        else:
            total_combinations = len(prefixes) * len(professions) * len(states)
            logger.info(f"Total combinations: {total_combinations:,} ({len(prefixes)} prefixes × {len(professions)} professions × {len(states)} states)")
        logger.info("Using SIDEBAR FILTERS for optimized discovery (fewer page loads)")

        processed = 0

        for prefix_idx, prefix in enumerate(prefixes):
            logger.info(f"\n{'='*60}")
            logger.info(f"PREFIX [{prefix_idx + 1}/{len(prefixes)}]: '{prefix}'")
            logger.info(f"{'='*60}")

            # Navigate to home and perform initial search for this prefix
            if not self.browser.navigate(AHPRA_SEARCH_URL, wait_until='domcontentloaded'):
                logger.error(f"Failed to navigate to search page for prefix '{prefix}'")
                continue

            random_delay()

            # Perform initial search with just the prefix (no filters)
            if not self._perform_search(prefix):
                logger.warning(f"Initial search failed for prefix '{prefix}'")
                continue

            random_delay()

            # Check if we have results (sidebar filters only appear when there are results)
            initial_count = self._get_result_count()
            if initial_count == 0:
                logger.info(f"No results for prefix '{prefix}', skipping all combinations")
                continue

            logger.info(f"Initial results for '{prefix}': {initial_count:,} practitioners")

            # Track if we need to re-search this prefix
            needs_research = False

            # Now iterate through professions and states using sidebar filters
            for profession in professions:
                for state in states:
                    state_abbrev = STATE_ABBREVIATIONS.get(state, state)

                    # Build list of suburbs to search: [None] for base search, plus specific suburbs if enabled
                    suburbs_to_search = [None]  # Always do base search without suburb filter
                    if self.include_suburbs:
                        suburbs_to_search.extend(MAJOR_SUBURBS.get(state, []))

                    for suburb in suburbs_to_search:
                        combo_key = self.checkpoint.make_combination_key(profession, state, prefix, suburb)

                        # Skip if already completed
                        if self.checkpoint.is_combination_completed(combo_key):
                            processed += 1
                            continue

                        processed += 1

                        # Build filter description for logging
                        filter_desc = f"{profession} | {state_abbrev}"
                        if suburb:
                            filter_desc += f" | {suburb}"
                        filter_desc += f" | '{prefix}'"

                        logger.info(f"[{processed}/{total_combinations}] Sidebar filter: {filter_desc}")

                        try:
                            # If page state was lost, re-search before continuing
                            if needs_research or not self._verify_sidebar_present():
                                logger.info(f"Re-searching prefix '{prefix}' to restore page state")
                                if self._re_search_prefix(prefix):
                                    needs_research = False
                                else:
                                    logger.warning(f"Failed to re-search prefix '{prefix}'")
                                    # Mark as completed with 0 results to avoid infinite loop
                                    self.checkpoint.mark_combination_completed(combo_key)
                                    self.checkpoint.save()
                                    continue

                            self.checkpoint.set_current_combination(combo_key)

                            # Use sidebar filters to apply profession, state, and suburb
                            count = self._apply_sidebar_filter_and_collect(prefix, profession, state, suburb)

                            # Mark combination as completed
                            self.checkpoint.mark_combination_completed(combo_key)
                            self.checkpoint.save()

                            # Log progress periodically
                            if processed % 50 == 0:
                                current_discovered = self.checkpoint.stats['total_discovered']
                                new_so_far = current_discovered - total_discovered_start
                                logger.info(f"Progress: {processed}/{total_combinations} | New discoveries: {new_so_far:,}")

                        except Exception as e:
                            logger.error(f"Error processing combination '{combo_key}': {e}")
                            self.checkpoint.increment_errors()
                            needs_research = True  # Page state likely lost

                            # Track retry count
                            self._retry_counts[combo_key] = self._retry_counts.get(combo_key, 0) + 1

                            if self._retry_counts[combo_key] >= MAX_RETRIES:
                                logger.warning(f"Skipping combination '{combo_key}' after {MAX_RETRIES} failed attempts")
                                # Mark as completed to avoid retry loop
                                self.checkpoint.mark_combination_completed(combo_key)
                                self.checkpoint.save()

                # Try to clear profession filter after all states/suburbs for this profession
                try:
                    if self._verify_sidebar_present():
                        self._input_sidebar_suburb(None)  # Clear suburb filter
                        self._select_sidebar_profession(profession, select=False)
                        self._select_sidebar_state("All")  # Reset state to All
                        ui_delay()
                except Exception:
                    needs_research = True

            # Try to clear all filters before moving to next prefix
            try:
                self._clear_sidebar_filters()
            except Exception:
                pass  # Will re-navigate for next prefix anyway

        # Final save and cleanup
        self.checkpoint.save()
        self.checkpoint.close_raw_backup()

        new_discovered = self.checkpoint.stats['total_discovered'] - total_discovered_start
        logger.info(f"\nOPTIMIZED discovery complete. New practitioners found: {new_discovered:,}")

        return new_discovered
