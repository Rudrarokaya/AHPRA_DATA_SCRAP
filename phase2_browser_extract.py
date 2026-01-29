#!/usr/bin/env python3
"""
Phase 2: Browser-based extraction pipeline.

Uses Playwright browser instead of HTTP API to avoid CAPTCHA.
This is slower but more reliable for large-scale extraction.

Usage:
    python phase2_browser_extract.py [--no-headless] [--limit N]
"""

import json
import argparse
import sys
import csv
import time
import random
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict
from loguru import logger

from config.settings import (
    DATA_DIR, EXTRACTED_DIR, BACKUP_DIR,
    EXTRACTED_BACKUP_FILE, DATA_FIELDS,
)
from src.utils import setup_logging, format_duration, get_date_string
from src.checkpoint import CheckpointManager
from src.browser import BrowserManager
from src.parser import PractitionerParser


# Browser extraction delays - longer than HTTP to ensure WAF passes
# At 15-25s delays = ~3 req/min, well below 20 req/min WAF threshold
MIN_DELAY = 15  # Minimum seconds between extractions
MAX_DELAY = 25  # Maximum seconds between extractions


class BrowserExtractionEngine:
    """Browser-based extraction using Playwright."""
    
    AHPRA_SEARCH_URL = "https://www.ahpra.gov.au/Registration/Registers-of-Practitioners.aspx"
    
    def __init__(self, browser: BrowserManager, checkpoint: CheckpointManager):
        self.browser = browser
        self.checkpoint = checkpoint
        self.parser = PractitionerParser()
        
        # Output files
        self.output_file: Optional[Path] = None
        self._csv_writer = None
        self._output_handle = None
        
        # JSON backup
        self.backup_file = EXTRACTED_BACKUP_FILE
        self.backup_metadata_file = EXTRACTED_BACKUP_FILE.with_suffix('.meta.json')
        self._backup_handle = None
        self._backup_reg_ids: set = set()
        self._backup_count: int = 0
        
        # CSV deduplication
        self._csv_reg_ids: set = set()
    
    def initialize(self) -> bool:
        """Initialize the extraction engine."""
        logger.info("Initializing browser extraction engine")
        
        # Ensure output directories exist
        EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        
        # Create CSV output file
        date_str = get_date_string()
        self.output_file = EXTRACTED_DIR / f"practitioners_{date_str}.csv"
        
        file_exists = self.output_file.exists()
        
        # Scan existing CSV for reg_ids
        if file_exists:
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if row.get('reg_id'):
                            self._csv_reg_ids.add(row['reg_id'])
                if self._csv_reg_ids:
                    logger.info(f"Loaded {len(self._csv_reg_ids)} reg_ids from existing CSV")
            except Exception as e:
                logger.warning(f"Failed to scan existing CSV: {e}")
        
        # Open file for appending
        self._output_handle = open(self.output_file, 'a', newline='', encoding='utf-8')
        self._csv_writer = csv.DictWriter(self._output_handle, fieldnames=DATA_FIELDS)
        
        if not file_exists:
            self._csv_writer.writeheader()
        
        logger.info(f"CSV output: {self.output_file}")
        
        # Initialize JSON backup
        self._initialize_json_backup()
        logger.info(f"JSON backup: {self.backup_file}")
        
        return True
    
    def _initialize_json_backup(self) -> None:
        """Initialize JSONL backup file."""
        if self.backup_metadata_file.exists():
            try:
                with open(self.backup_metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                self._backup_count = metadata.get('total_extracted', 0)
            except Exception as e:
                logger.warning(f"Failed to load backup metadata: {e}")
                self._backup_count = 0
        
        if self.backup_file.exists():
            try:
                with open(self.backup_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                record = json.loads(line)
                                if 'reg_id' in record:
                                    self._backup_reg_ids.add(record['reg_id'])
                            except json.JSONDecodeError:
                                continue
                self._backup_count = len(self._backup_reg_ids)
                logger.info(f"Loaded {len(self._backup_reg_ids)} reg_ids from existing backup")
            except Exception as e:
                logger.warning(f"Failed to scan backup file: {e}")
        
        self._backup_handle = open(self.backup_file, 'a', encoding='utf-8')
        
        if not self.backup_metadata_file.exists():
            self._save_backup_metadata(is_initial=True)
    
    def _save_backup_metadata(self, is_initial: bool = False) -> None:
        """Save backup metadata."""
        try:
            metadata = {
                'total_extracted': self._backup_count,
                'last_updated': datetime.now().isoformat(),
            }
            
            if is_initial:
                metadata['started_at'] = datetime.now().isoformat()
            elif self.backup_metadata_file.exists():
                try:
                    with open(self.backup_metadata_file, 'r', encoding='utf-8') as f:
                        old_meta = json.load(f)
                    metadata['started_at'] = old_meta.get('started_at', metadata['last_updated'])
                except Exception:
                    metadata['started_at'] = metadata['last_updated']
            else:
                metadata['started_at'] = metadata['last_updated']
            
            with open(self.backup_metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save backup metadata: {e}")
    
    def _save_to_json_backup(self, data: Dict) -> None:
        """Write a record to JSON backup."""
        backup_entry = data.copy()
        backup_entry['extracted_at'] = datetime.now().isoformat()
        
        try:
            self._backup_handle.write(json.dumps(backup_entry, ensure_ascii=False) + '\n')
            self._backup_handle.flush()
            self._backup_count += 1
            
            if data.get('reg_id'):
                self._backup_reg_ids.add(data['reg_id'])
        except Exception as e:
            logger.error(f"Failed to write to JSON backup: {e}")
    
    def _write_record(self, data: Dict) -> None:
        """Write a record to CSV."""
        try:
            reg_id = data.get('reg_id')
            if reg_id and reg_id in self._csv_reg_ids:
                return
            
            self._csv_writer.writerow(data)
            self._output_handle.flush()
            
            if reg_id:
                self._csv_reg_ids.add(reg_id)
        except Exception as e:
            logger.error(f"Failed to write to CSV: {e}")
    
    def _dismiss_modals(self, page):
        """Dismiss any open modals that might block interactions."""
        try:
            # Try clicking any visible close buttons
            close_selectors = [
                '.modal-close',
                '.close-button',
                'button[aria-label="Close"]',
                '.modal .close',
                '[data-dismiss="modal"]',
            ]
            for selector in close_selectors:
                close_btn = page.locator(selector)
                if close_btn.count() > 0 and close_btn.first.is_visible():
                    close_btn.first.click(force=True)
                    time.sleep(0.3)
                    return True

            # Try pressing Escape
            page.keyboard.press('Escape')
            time.sleep(0.3)
            return True
        except Exception:
            return False

    def extract_single(self, reg_id: str) -> Optional[Dict]:
        """
        Extract data for a single practitioner using NATURAL browser interaction.

        AHPRA page structure (discovered via debugging):
        1. Search returns results in a modal popup (not a table)
        2. Results are in: .modal-body div[data-practitioner-id="XXX"]
        3. Clickable name is: a.practitioner-name-link

        Flow:
        1. Press Escape to dismiss any overlay
        2. Fill search input and click search button
        3. Wait for modal results to appear
        4. Click on a.practitioner-name-link to load full details
        5. Extract data from the detail page
        6. Navigate back for next iteration
        """
        try:
            page = self.browser.page

            # Step 0: CRITICAL - Press Escape to dismiss overlays/modals
            page.keyboard.press('Escape')
            time.sleep(0.5)

            # Step 1: Make sure we're on the search page
            current_url = page.url
            if 'Registers-of-Practitioners' not in current_url:
                logger.debug("Navigating to search page...")
                self.browser.navigate(self.AHPRA_SEARCH_URL)
                page.wait_for_load_state('load', timeout=60000)
                time.sleep(3)
                page.keyboard.press('Escape')
                time.sleep(0.5)

            # Step 2: TYPE (not fill) the search input - triggers typeahead properly
            search_input = page.locator('#name-reg')
            search_input.click()
            time.sleep(0.3)
            # Use type() to trigger the typeahead, not fill()
            search_input.type(reg_id, delay=50)  # 50ms between keystrokes
            time.sleep(1)

            # Step 3: Click search button (force=True to bypass any overlays)
            page.locator('#predictiveSearchHomeBtn').click(force=True)

            # Wait for results modal to appear (8 seconds for AJAX)
            logger.debug("Waiting for search results...")
            time.sleep(8)

            # Step 4: Click the practitioner name link using JavaScript
            # The link is in a modal and may not be "visible" to Playwright,
            # so we use JS to click it directly
            click_result = page.evaluate(f'''() => {{
                // Try to find the specific practitioner's link
                let link = document.querySelector('div[data-practitioner-id="{reg_id}"] a.practitioner-name-link');

                // Fallback to any practitioner link
                if (!link) {{
                    link = document.querySelector('a.practitioner-name-link');
                }}

                if (link) {{
                    link.click();
                    return {{ success: true, name: link.innerText }};
                }}
                return {{ success: false }};
            }}''')

            if not click_result['success']:
                logger.warning(f"No practitioner-name-link found for {reg_id}")
                page.screenshot(path=f"debug_no_link_{reg_id}.png")
                return None

            logger.debug(f"Clicked on: {click_result.get('name', 'unknown')}")

            # Wait for detail page to load
            time.sleep(5)  # Give time for the detail view to render

            # Step 6: Get the HTML content
            html = page.content()

            if not html:
                logger.warning(f"Failed to get HTML for {reg_id}")
                return None

            # Check for CAPTCHA
            if 'captcha' in html.lower() or 'recaptcha' in html.lower():
                logger.error(f"CAPTCHA detected for {reg_id}!")
                Path(f"debug_captcha_{reg_id}.html").write_text(html)
                return None

            # Step 7: Parse the HTML
            data = self.parser.parse(html)

            if not data.get('reg_id'):
                data['reg_id'] = reg_id

            # Step 8: Go back to search page for next iteration
            page.go_back()
            page.wait_for_load_state('load', timeout=30000)
            time.sleep(1)
            page.keyboard.press('Escape')  # Dismiss any modal
            time.sleep(0.5)

            # Validate
            valid_fields = sum(1 for v in data.values() if v is not None)
            if valid_fields >= 2:
                return data

            logger.warning(f"Incomplete data for {reg_id}: only {valid_fields} valid fields")
            return None

        except Exception as e:
            logger.error(f"Error extracting {reg_id}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            # Try to recover
            try:
                self.browser.navigate(self.AHPRA_SEARCH_URL)
                time.sleep(2)
                page.keyboard.press('Escape')
            except Exception:
                pass
            return None
    
    def close(self) -> None:
        """Close file handles."""
        if self._output_handle:
            self._output_handle.flush()
            self._output_handle.close()
            self._output_handle = None
        
        if self._backup_handle:
            self._backup_handle.flush()
            self._backup_handle.close()
            self._backup_handle = None
            self._save_backup_metadata()


def load_discovered_ids(limit: int = None) -> list:
    """Load discovered reg IDs from JSON file."""
    discovered_file = DATA_DIR / "discovery" / "discovered_ids.json"
    
    if not discovered_file.exists():
        logger.error(f"Discovered IDs file not found: {discovered_file}")
        return []
    
    try:
        with open(discovered_file, 'r') as f:
            data = json.load(f)
        
        ids = data.get("reg_ids", [])
        if limit:
            ids = ids[:limit]
        
        logger.info(f"Loaded {len(ids)} IDs from discovered_ids.json")
        return ids
    
    except Exception as e:
        logger.error(f"Failed to load discovered IDs: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(
        description="Browser-based extraction of practitioner data"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible mode (not headless)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit to first N IDs (for testing)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Progress display interval (default: 8)"
    )
    
    args = parser.parse_args()
    
    setup_logging("phase2_browser_extraction")
    logger.info("=" * 70)
    logger.info("AHPRA Phase 2: Browser-based Extraction")
    logger.info("=" * 70)
    
    # Load discovered IDs
    all_reg_ids = load_discovered_ids(limit=args.limit)
    if not all_reg_ids:
        logger.error("No IDs to extract")
        return 1
    
    logger.info(f"Total IDs to process: {len(all_reg_ids):,}")
    
    # Initialize checkpoint
    checkpoint_name = f"phase2_browser_{get_date_string()}"
    checkpoint = CheckpointManager(checkpoint_name)
    checkpoint.scraped_reg_ids = set(all_reg_ids)
    
    headless = not args.no_headless
    logger.info(f"Browser mode: {'headless' if headless else 'visible'}")

    # Multi-layer throttling (reactive, not proactive)
    # Layer 1: Base delay (15-25s) in extraction loop = ~3 req/min
    # Layer 2: Short cooldown after failures (60s) - resets WAF short-term window
    # Layer 3: Long cooldown after consecutive failures (300s) - resets WAF sliding window
    SHORT_COOLDOWN_DURATION = 60   # 1 minute
    LONG_COOLDOWN_DURATION = 300   # 5 minutes
    FAILURES_FOR_SHORT_COOLDOWN = 3
    FAILURES_FOR_LONG_COOLDOWN = 3

    try:
        with BrowserManager(headless=headless) as browser:
            engine = BrowserExtractionEngine(browser, checkpoint)
            
            if not engine.initialize():
                logger.error("Failed to initialize extraction engine")
                return 1
            
            # Get pending IDs
            pending = [rid for rid in all_reg_ids if rid not in engine._backup_reg_ids]
            
            if not pending:
                logger.warning("No pending IDs to extract")
                return 0
            
            logger.info(f"Pending extractions: {len(pending):,}")
            logger.info(f"Already extracted: {len(engine._backup_reg_ids):,}")
            logger.info("=" * 70)
            
            start_time = time.time()
            extracted_count = 0
            failed_ids = []
            consecutive_failures = 0
            total_failures_in_window = 0

            for idx, reg_id in enumerate(pending, 1):
                try:
                    elapsed = time.time() - start_time
                    logger.info(
                        f"[{idx}/{len(pending)}] Extracting {reg_id}... "
                        f"({extracted_count} ok, {len(failed_ids)} failed)"
                    )

                    # Random delay between requests (Layer 1: base throttling)
                    delay = random.uniform(MIN_DELAY, MAX_DELAY)
                    logger.debug(f"Waiting {delay:.1f}s before extraction...")
                    time.sleep(delay)

                    result = engine.extract_single(reg_id)

                    if result:
                        engine._save_to_json_backup(result)
                        engine._write_record(result)
                        checkpoint.mark_extracted(reg_id)
                        extracted_count += 1
                        consecutive_failures = 0
                        total_failures_in_window = 0  # Reset on success

                        name = result.get('name', 'Unknown')
                        logger.info(f"    -> Extracted: {name}")

                        if extracted_count % args.batch_size == 0:
                            rate = extracted_count / elapsed if elapsed > 0 else 0
                            remaining = len(pending) - idx
                            eta = remaining / rate if rate > 0 else 0
                            logger.info(
                                f"--- Progress: {extracted_count}/{len(pending)}, "
                                f"~{format_duration(eta)} remaining ---"
                            )
                    else:
                        failed_ids.append(reg_id)
                        consecutive_failures += 1
                        total_failures_in_window += 1
                        logger.warning(f"    -> Failed to extract {reg_id}")

                        # Layer 2: Short cooldown after N failures in window
                        if total_failures_in_window >= FAILURES_FOR_SHORT_COOLDOWN:
                            logger.warning(
                                f"Detected {total_failures_in_window} failures - "
                                f"applying {SHORT_COOLDOWN_DURATION}s cooldown..."
                            )
                            checkpoint.save()
                            time.sleep(SHORT_COOLDOWN_DURATION)
                            total_failures_in_window = 0
                            logger.info("Short cooldown complete. Resuming...")

                        # Layer 3: Long cooldown after consecutive failures
                        if consecutive_failures >= FAILURES_FOR_LONG_COOLDOWN:
                            logger.warning(
                                f"Detected {consecutive_failures} consecutive failures - "
                                f"applying {LONG_COOLDOWN_DURATION}s cooldown to reset WAF..."
                            )
                            checkpoint.save()
                            # Refresh the page to get a fresh session state
                            browser.navigate(engine.AHPRA_SEARCH_URL)
                            time.sleep(LONG_COOLDOWN_DURATION)
                            consecutive_failures = 0
                            logger.info("Long cooldown complete. Resuming...")

                except KeyboardInterrupt:
                    logger.warning("Interrupted by user")
                    checkpoint.save()
                    break
                except Exception as e:
                    logger.error(f"Error: {e}")
                    failed_ids.append(reg_id)
            
            # Summary
            elapsed = time.time() - start_time
            logger.info("=" * 70)
            logger.info("EXTRACTION SUMMARY")
            logger.info("=" * 70)
            logger.info(f"Successfully extracted: {extracted_count}")
            logger.info(f"Failed: {len(failed_ids)}")
            logger.info(f"Time elapsed: {format_duration(elapsed)}")
            
            engine.close()
            checkpoint.save()
            
            return 0 if len(failed_ids) == 0 else 1
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
