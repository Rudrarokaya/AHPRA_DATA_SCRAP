"""
Stage 2: Extractor module for AHPRA scraper.

Uses AHPRA API to fetch practitioner details by registration ID.
Saves extracted data as both JSON backup and CSV output.
"""

import csv
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger

from config.settings import (
    EXTRACTED_DIR,
    BACKUP_DIR,
    EXTRACTED_BACKUP_FILE,
    DATA_FIELDS,
    MAX_RETRIES,
    RETRY_DELAY,
    CHECKPOINT_INTERVAL,
    PROGRESS_DISPLAY_INTERVAL,
)
from src.api_client import AHPRAClient
from src.checkpoint import CheckpointManager
from src.parser import PractitionerParser
from src.utils import get_date_string, format_duration


class ExtractionEngine:
    """
    Extracts detailed practitioner information via AHPRA API.
    Saves data as both JSON backup and CSV output.
    """

    def __init__(self, checkpoint: CheckpointManager, api_client: AHPRAClient = None):
        """
        Initialize extraction engine.

        Args:
            checkpoint: Checkpoint manager instance
            api_client: Optional API client (creates one if not provided)
        """
        self.checkpoint = checkpoint
        self.api_client = api_client or AHPRAClient()
        self.parser = PractitionerParser()
        self._owns_client = api_client is None

        # Output files
        self.output_file: Optional[Path] = None
        self._csv_writer = None
        self._output_handle = None

        # JSON backup (using JSONL format for incremental writes)
        self.backup_file = EXTRACTED_BACKUP_FILE
        self.backup_metadata_file = EXTRACTED_BACKUP_FILE.with_suffix('.meta.json')
        self._backup_handle = None  # File handle for JSONL
        self._backup_reg_ids: set = set()  # Track what's already in backup
        self._backup_count: int = 0  # Track count without loading all data

        # Progress tracking
        self._extraction_start_time: Optional[float] = None
        self._last_progress_time: float = 0

        # CSV deduplication
        self._csv_reg_ids: set = set()

    def initialize(self) -> bool:
        """
        Initialize the extraction engine.

        Returns:
            True if successful
        """
        logger.info("Initializing extraction engine")

        # Ensure output directories exist
        EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

        # Create CSV output file
        date_str = get_date_string()
        self.output_file = EXTRACTED_DIR / f"practitioners_{date_str}.csv"

        # Check if we're resuming (file exists)
        file_exists = self.output_file.exists()

        # Scan existing CSV for reg_ids (deduplication)
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

        # Write header if new file
        if not file_exists:
            self._csv_writer.writeheader()

        logger.info(f"CSV output: {self.output_file}")

        # Initialize JSON backup
        self._initialize_json_backup()
        logger.info(f"JSON backup: {self.backup_file}")

        return True

    def _initialize_json_backup(self) -> None:
        """
        Initialize JSON backup using JSONL format for memory efficiency.

        Uses two files:
        - .jsonl file: One JSON object per line (practitioners)
        - .meta.json file: Metadata (started_at, last_updated, total_count)

        This approach avoids loading all data into memory.
        """
        # Load metadata if exists
        if self.backup_metadata_file.exists():
            try:
                with open(self.backup_metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                self._backup_count = metadata.get('total_extracted', 0)
            except Exception as e:
                logger.warning(f"Failed to load backup metadata: {e}")
                self._backup_count = 0

        # Scan existing JSONL file for reg_ids (deduplication)
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

        # Open JSONL file for appending
        self._backup_handle = open(self.backup_file, 'a', encoding='utf-8')

        # Write initial metadata if new
        if not self.backup_metadata_file.exists():
            self._save_backup_metadata(is_initial=True)

    def close(self) -> None:
        """Close output file handles and API client."""
        if self._output_handle:
            self._output_handle.flush()
            self._output_handle.close()
            self._output_handle = None
            self._csv_writer = None

        if self._backup_handle:
            self._backup_handle.flush()
            self._backup_handle.close()
            self._backup_handle = None
            # Save final metadata
            self._save_backup_metadata()

        if self._owns_client and self.api_client:
            self.api_client.close()

    def run_extraction(self, resume: bool = True, limit: int = None) -> int:
        """
        Run the extraction process.

        Args:
            resume: Whether to resume from checkpoint
            limit: Optional limit on number of practitioners to extract

        Returns:
            Number of practitioners extracted
        """
        logger.info("Starting extraction process")

        # Load checkpoint
        if resume:
            self.checkpoint.load()

        # Get pending reg_ids
        pending = self.checkpoint.get_pending_reg_ids()
        total_pending = len(pending)

        if total_pending == 0:
            logger.warning("No pending reg_ids to extract. Run discovery first.")
            return 0

        logger.info(f"Pending extractions: {total_pending:,}")

        # Apply limit if specified
        if limit:
            pending = pending[:limit]
            logger.info(f"Limited to {limit} extractions")

        extracted_count = 0
        self._extraction_start_time = time.time()

        for i, reg_id in enumerate(pending):
            # Skip if already extracted (checkpoint deduplication)
            if self.checkpoint.is_reg_id_extracted(reg_id):
                continue

            # Skip if already in JSON backup (secondary deduplication)
            if reg_id in self._backup_reg_ids:
                logger.debug(f"Skipping {reg_id} - already in backup")
                continue

            try:
                # Extract practitioner data via API
                data = self._extract_practitioner(reg_id)

                if data:
                    # Save to JSON backup FIRST (before CSV)
                    self._save_to_json_backup(data)

                    # Write to CSV
                    self._write_record(data)

                    # Mark as extracted in checkpoint
                    self.checkpoint.mark_extracted(reg_id)
                    extracted_count += 1

                    # Display progress every PROGRESS_DISPLAY_INTERVAL (50)
                    if extracted_count % PROGRESS_DISPLAY_INTERVAL == 0:
                        self._display_progress(extracted_count, len(pending))

                else:
                    logger.warning(f"No data extracted for {reg_id}")
                    self.checkpoint.increment_errors()

            except Exception as e:
                logger.error(f"Error extracting {reg_id}: {e}")
                self.checkpoint.increment_errors()
                # Flush files on error to prevent data loss
                if self._output_handle:
                    self._output_handle.flush()
                if self._backup_handle:
                    self._backup_handle.flush()

            # Auto-save checkpoint
            self.checkpoint.auto_save_if_needed()

            # Periodic checkpoint save every CHECKPOINT_INTERVAL (50)
            if self.checkpoint.should_save(extracted_count):
                self.checkpoint.save()
                self._save_json_backup()  # Also save JSON backup
                self._output_handle.flush()

        # Final save
        self.checkpoint.save()
        self._save_json_backup()
        self._output_handle.flush()

        logger.info(f"Extraction complete. Total extracted: {extracted_count:,}")
        return extracted_count

    def _display_progress(self, extracted: int, total: int) -> None:
        """Display progress with rate and ETA."""
        elapsed = time.time() - self._extraction_start_time
        rate = extracted / elapsed * 60 if elapsed > 0 else 0  # per minute
        remaining = total - extracted

        if rate > 0:
            eta_seconds = remaining / rate * 60
            eta_str = format_duration(eta_seconds)
        else:
            eta_str = "calculating..."

        # Get file sizes
        csv_size = self.output_file.stat().st_size / 1024 / 1024 if self.output_file.exists() else 0
        json_size = self.backup_file.stat().st_size / 1024 / 1024 if self.backup_file.exists() else 0

        logger.info(
            f"[{extracted:,}/{total:,}] "
            f"Rate: {rate:.1f}/min | "
            f"ETA: {eta_str} | "
            f"CSV: {csv_size:.1f}MB | "
            f"JSON: {json_size:.1f}MB"
        )

    def _save_to_json_backup(self, data: Dict) -> None:
        """
        Write a practitioner record to JSON backup file incrementally.

        Uses JSONL format (one JSON object per line) for memory efficiency.

        Args:
            data: Practitioner data dictionary
        """
        # Add extracted_at timestamp
        backup_entry = data.copy()
        backup_entry['extracted_at'] = datetime.now().isoformat()

        # Write as single JSON line (JSONL format)
        try:
            self._backup_handle.write(json.dumps(backup_entry, ensure_ascii=False) + '\n')
            # IMMEDIATELY flush to prevent data loss
            self._backup_handle.flush()
            self._backup_count += 1

            # Track in dedup set
            if data.get('reg_id'):
                self._backup_reg_ids.add(data['reg_id'])
        except Exception as e:
            logger.error(f"Failed to write to JSON backup: {e}")

    def _save_json_backup(self) -> None:
        """Flush JSONL backup and save metadata."""
        try:
            # Flush the JSONL file
            if self._backup_handle:
                self._backup_handle.flush()

            # Save metadata
            self._save_backup_metadata()
        except Exception as e:
            logger.error(f"Failed to save JSON backup: {e}")

    def _save_backup_metadata(self, is_initial: bool = False) -> None:
        """
        Save backup metadata to separate file.

        Args:
            is_initial: True if this is the initial metadata creation
        """
        try:
            metadata = {
                'total_extracted': self._backup_count,
                'last_updated': datetime.now().isoformat(),
            }

            if is_initial:
                metadata['started_at'] = datetime.now().isoformat()
            elif self.backup_metadata_file.exists():
                # Preserve original started_at
                try:
                    with open(self.backup_metadata_file, 'r', encoding='utf-8') as f:
                        old_meta = json.load(f)
                    metadata['started_at'] = old_meta.get('started_at', metadata['last_updated'])
                except Exception:
                    metadata['started_at'] = metadata['last_updated']
            else:
                metadata['started_at'] = metadata['last_updated']

            # Atomic write
            temp_file = self.backup_metadata_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            temp_file.replace(self.backup_metadata_file)
        except Exception as e:
            logger.error(f"Failed to save backup metadata: {e}")

    def _extract_practitioner(self, reg_id: str) -> Optional[Dict]:
        """
        Extract data for a single practitioner via API.

        Args:
            reg_id: Registration ID

        Returns:
            Extracted data dictionary or None
        """
        # Fetch HTML via API
        html = self.api_client.fetch_practitioner(reg_id)

        if not html:
            logger.warning(f"Failed to fetch data for {reg_id} - no HTML returned")
            return None

        # Debug: Check for rate limiting or CAPTCHA indicators
        html_lower = html.lower()
        blocking_detected = False
        blocking_type = None

        if 'captcha' in html_lower or 'recaptcha' in html_lower:
            logger.error(f"CAPTCHA detected for {reg_id}! Server is rate limiting.")
            blocking_detected = True
            blocking_type = "captcha"
        elif 'too many requests' in html_lower or 'rate limit' in html_lower:
            logger.error(f"Rate limit page detected for {reg_id}!")
            blocking_detected = True
            blocking_type = "ratelimit"
        elif 'access denied' in html_lower or 'blocked' in html_lower:
            logger.error(f"Access denied page detected for {reg_id}!")
            blocking_detected = True
            blocking_type = "blocked"

        if blocking_detected:
            # Save the blocking page for analysis
            try:
                debug_file = Path(f"debug_{blocking_type}_{reg_id}.html")
                debug_file.write_text(html, encoding='utf-8')
                logger.info(f"Saved blocking page to {debug_file}")
            except Exception as e:
                logger.debug(f"Failed to save debug HTML: {e}")
            return None

        try:
            # Parse the HTML response
            data = self.parser.parse(html)

            # Ensure reg_id is set
            if not data.get('reg_id'):
                data['reg_id'] = reg_id

            # Validate we got some data - accept if we have reg_id + any other field
            # This is less strict than requiring name OR profession
            valid_fields = sum(1 for v in data.values() if v is not None)
            if valid_fields >= 2:  # At least reg_id + one other field
                return data

            # Debug: Log what we got back when parsing fails
            logger.warning(f"Incomplete data for {reg_id}: only {valid_fields} valid fields")
            logger.debug(f"HTML length: {len(html)} chars, first 500 chars: {html[:500]}")

        except Exception as e:
            logger.warning(f"Parse error for {reg_id}: {e}")

        return None

    def _write_record(self, data: Dict) -> None:
        """
        Write a record to the CSV file.

        Args:
            data: Practitioner data dictionary
        """
        try:
            # Check for duplicates in CSV
            reg_id = data.get('reg_id')
            if reg_id and reg_id in self._csv_reg_ids:
                logger.debug(f"Skipping CSV write - {reg_id} already exists")
                return

            self._csv_writer.writerow(data)
            # IMMEDIATELY flush to prevent data loss
            self._output_handle.flush()

            # Track in dedup set
            if reg_id:
                self._csv_reg_ids.add(reg_id)
        except Exception as e:
            logger.error(f"Failed to write record: {e}")

    def extract_single(self, reg_id: str) -> Optional[Dict]:
        """
        Extract data for a single reg_id (useful for testing).

        Args:
            reg_id: Registration ID

        Returns:
            Extracted data dictionary
        """
        return self._extract_practitioner(reg_id)

    def get_progress(self) -> Dict:
        """
        Get current extraction progress.

        Returns:
            Progress dictionary
        """
        pending = len(self.checkpoint.get_pending_reg_ids())
        extracted = len(self.checkpoint.extracted_reg_ids)

        return {
            'total_discovered': len(self.checkpoint.scraped_reg_ids),
            'total_extracted': extracted,
            'pending': pending,
            'errors': self.checkpoint.stats['errors'],
            'completion_pct': (extracted / (extracted + pending) * 100) if (extracted + pending) > 0 else 0,
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
