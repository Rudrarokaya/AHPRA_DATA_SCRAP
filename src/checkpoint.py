"""
Checkpoint management for resumable scraping.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Any, Optional, List
from loguru import logger

from config.settings import (
    CHECKPOINT_DIR, CHECKPOINT_INTERVAL, AUTO_SAVE_INTERVAL,
    DISCOVERY_DIR, DISCOVERED_IDS_FILE
)


class CheckpointManager:
    """
    Manages checkpoints for resumable scraping operations.

    Tracks:
    - Completed prefixes (for discovery stage)
    - Scraped registration IDs (for deduplication)
    - Current position in the scraping process
    - Statistics and metadata
    """

    def __init__(self, checkpoint_name: str = "scraper", discovered_ids_file: Optional[Path] = None):
        """
        Initialize checkpoint manager.

        Args:
            checkpoint_name: Name for the checkpoint file
            discovered_ids_file: Optional custom path for discovered IDs file.
                                 If None, uses the global DISCOVERED_IDS_FILE.
                                 Useful for isolated test runs.
        """
        self.checkpoint_name = checkpoint_name
        self.checkpoint_file = CHECKPOINT_DIR / f"{checkpoint_name}_checkpoint.json"
        self.reg_ids_file = DISCOVERY_DIR / "reg_ids.txt"  # Legacy flat file (for migration)
        # Use custom path if provided (for test isolation), otherwise use global file
        self.discovered_ids_file = discovered_ids_file if discovered_ids_file else DISCOVERED_IDS_FILE

        # RAW BACKUP: Append-only file for immediate ID backup (failsafe)
        # This file gets each ID appended immediately when found - never loses data
        self.raw_ids_backup_file = self.discovered_ids_file.with_suffix('.raw.txt')
        self._raw_backup_handle = None

        # Checkpoint data
        self.completed_prefixes: Set[str] = set()
        self.completed_combinations: Set[str] = set()  # For multi-dimensional search
        self.scraped_reg_ids: Set[str] = set()  # In-memory set for dedup during discovery
        self.extracted_reg_ids: Set[str] = set()
        self.failed_reg_ids: Set[str] = set()  # Track IDs that failed extraction
        self.current_prefix: Optional[str] = None
        self.current_page: int = 0
        self.current_combination: Optional[str] = None  # For multi-dimensional search

        # Discovery metadata (stored in discovered_ids.json)
        self.discovery_started_at: Optional[str] = None
        self.discovery_last_updated: Optional[str] = None

        # Statistics
        self.stats = {
            "total_discovered": 0,
            "total_extracted": 0,
            "errors": 0,
            "start_time": None,
            "last_save_time": None,
        }

        # Auto-save tracking
        self._last_auto_save = time.time()

        # Ensure directories exist
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)

    def load(self) -> bool:
        """
        Load checkpoint from file and reg_ids from JSON (or migrate from flat file).

        Returns:
            True if checkpoint loaded successfully, False otherwise
        """
        # Try to load from new JSON format first
        if self.discovered_ids_file.exists():
            try:
                self._load_discovered_ids_json()
                logger.info(f"Loaded {len(self.scraped_reg_ids)} reg_ids from {self.discovered_ids_file}")
            except Exception as e:
                logger.error(f"Failed to load discovered_ids.json: {e}")
        # Fall back to legacy flat file and migrate
        elif self.reg_ids_file.exists():
            try:
                self._migrate_from_txt()
                logger.info(f"Migrated {len(self.scraped_reg_ids)} reg_ids from {self.reg_ids_file} to JSON format")
            except Exception as e:
                logger.error(f"Failed to migrate reg_ids file: {e}")

        # AUTO-RECOVER: Check raw backup for any IDs missed due to crash
        self.recover_from_raw_backup()

        # Load checkpoint JSON
        if not self.checkpoint_file.exists():
            logger.info(f"No checkpoint file found at {self.checkpoint_file}")
            # Update stats with reg_ids count
            self.stats['total_discovered'] = len(self.scraped_reg_ids)
            return len(self.scraped_reg_ids) > 0

        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.completed_prefixes = set(data.get('completed_prefixes', []))
            self.completed_combinations = set(data.get('completed_combinations', []))
            self.extracted_reg_ids = set(data.get('extracted_reg_ids', []))
            self.failed_reg_ids = set(data.get('failed_reg_ids', []))
            self.current_prefix = data.get('current_prefix')
            self.current_page = data.get('current_page', 0)
            self.current_combination = data.get('current_combination')
            self.stats = data.get('stats', self.stats)

            # Update total_discovered from actual count
            self.stats['total_discovered'] = len(self.scraped_reg_ids)

            logger.info(
                f"Checkpoint loaded: {len(self.completed_prefixes)} prefixes, "
                f"{len(self.completed_combinations)} combinations, "
                f"{len(self.scraped_reg_ids)} reg_ids discovered, "
                f"{len(self.extracted_reg_ids)} extracted"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False

    def _load_discovered_ids_json(self) -> None:
        """Load discovered reg_ids from JSON file."""
        with open(self.discovered_ids_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.scraped_reg_ids = set(data.get('reg_ids', []))
        self.discovery_started_at = data.get('started_at')
        self.discovery_last_updated = data.get('last_updated')

    def _migrate_from_txt(self) -> None:
        """Migrate legacy reg_ids.txt to new JSON format."""
        # Load from flat file
        with open(self.reg_ids_file, 'r', encoding='utf-8') as f:
            self.scraped_reg_ids = set(line.strip() for line in f if line.strip())

        # Set initial timestamps
        self.discovery_started_at = datetime.now().isoformat()
        self.discovery_last_updated = datetime.now().isoformat()

        # Save to new JSON format
        self._save_discovered_ids_json()

        logger.info(f"Migration complete: {len(self.scraped_reg_ids)} reg_ids migrated to JSON format")

    def save(self) -> bool:
        """
        Save checkpoint to file and discovered_ids to JSON.

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Update save time and stats
            self.stats['last_save_time'] = datetime.now().isoformat()
            self.stats['total_discovered'] = len(self.scraped_reg_ids)

            data = {
                'completed_prefixes': list(self.completed_prefixes),
                'completed_combinations': list(self.completed_combinations),
                'extracted_reg_ids': list(self.extracted_reg_ids),
                'failed_reg_ids': list(self.failed_reg_ids),
                'current_prefix': self.current_prefix,
                'current_page': self.current_page,
                'current_combination': self.current_combination,
                'stats': self.stats,
            }

            # Write to temp file first, then rename (atomic)
            temp_file = self.checkpoint_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

            temp_file.replace(self.checkpoint_file)

            # Also save discovered_ids JSON
            self._save_discovered_ids_json()

            logger.debug(f"Checkpoint saved to {self.checkpoint_file}")
            self._last_auto_save = time.time()
            return True

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False

    def _save_discovered_ids_json(self) -> None:
        """Save discovered reg_ids to JSON file with metadata."""
        # Update last_updated timestamp
        self.discovery_last_updated = datetime.now().isoformat()

        # Set started_at if this is a new discovery
        if not self.discovery_started_at:
            self.discovery_started_at = datetime.now().isoformat()

        data = {
            'started_at': self.discovery_started_at,
            'last_updated': self.discovery_last_updated,
            'total_count': len(self.scraped_reg_ids),
            'reg_ids': list(self.scraped_reg_ids),
        }

        # Write to temp file first, then rename (atomic)
        temp_file = self.discovered_ids_file.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        temp_file.replace(self.discovered_ids_file)

    def auto_save_if_needed(self) -> bool:
        """
        Auto-save checkpoint if enough time has passed.

        Returns:
            True if saved, False otherwise
        """
        if time.time() - self._last_auto_save >= AUTO_SAVE_INTERVAL:
            return self.save()
        return False

    def should_save(self, count: int) -> bool:
        """
        Check if we should save based on item count.

        Args:
            count: Current item count

        Returns:
            True if should save
        """
        return count > 0 and count % CHECKPOINT_INTERVAL == 0

    def is_prefix_completed(self, prefix: str) -> bool:
        """
        Check if a prefix has been completed.

        Args:
            prefix: Search prefix

        Returns:
            True if completed
        """
        return prefix in self.completed_prefixes

    def mark_prefix_completed(self, prefix: str) -> None:
        """
        Mark a prefix as completed.

        Args:
            prefix: Search prefix
        """
        self.completed_prefixes.add(prefix)
        self.current_prefix = None
        self.current_page = 0
        logger.debug(f"Marked prefix '{prefix}' as completed")

    def set_current_position(self, prefix: str, page: int) -> None:
        """
        Set current scraping position.

        Args:
            prefix: Current prefix
            page: Current page number
        """
        self.current_prefix = prefix
        self.current_page = page

    def is_reg_id_scraped(self, reg_id: str) -> bool:
        """
        Check if a registration ID has been scraped.

        Args:
            reg_id: Registration ID

        Returns:
            True if already scraped
        """
        return reg_id in self.scraped_reg_ids

    def save_reg_id(self, reg_id: str) -> bool:
        """
        Save a discovered reg_id to the in-memory set AND raw backup file.

        The raw backup file is an append-only failsafe that immediately
        persists each ID to disk - ensuring zero data loss even on crash.

        Args:
            reg_id: Registration ID

        Returns:
            True if new (not duplicate), False if already exists
        """
        if reg_id in self.scraped_reg_ids:
            logger.debug(f"Duplicate reg_id skipped: {reg_id}")
            return False

        self.scraped_reg_ids.add(reg_id)
        self.stats['total_discovered'] += 1

        # IMMEDIATELY append to raw backup file (failsafe)
        self._append_to_raw_backup(reg_id)

        return True

    def _append_to_raw_backup(self, reg_id: str) -> None:
        """
        Append a single reg_id to the raw backup file immediately.

        This is an append-only operation that ensures data is never lost.
        """
        try:
            # Open file handle if not already open
            if self._raw_backup_handle is None:
                self._raw_backup_handle = open(self.raw_ids_backup_file, 'a', encoding='utf-8')

            self._raw_backup_handle.write(reg_id + '\n')
            self._raw_backup_handle.flush()  # Flush immediately
        except Exception as e:
            logger.error(f"Failed to write to raw backup: {e}")

    def close_raw_backup(self) -> None:
        """Close the raw backup file handle."""
        if self._raw_backup_handle:
            try:
                self._raw_backup_handle.flush()
                self._raw_backup_handle.close()
            except Exception:
                pass
            self._raw_backup_handle = None

    def recover_from_raw_backup(self) -> int:
        """
        Recover reg_ids from raw backup file that may not be in main JSON.

        This is useful if the process crashed before checkpoint.save() was called.

        Returns:
            Number of IDs recovered
        """
        if not self.raw_ids_backup_file.exists():
            return 0

        recovered = 0
        try:
            with open(self.raw_ids_backup_file, 'r', encoding='utf-8') as f:
                for line in f:
                    reg_id = line.strip()
                    if reg_id and reg_id not in self.scraped_reg_ids:
                        self.scraped_reg_ids.add(reg_id)
                        recovered += 1

            if recovered > 0:
                logger.info(f"Recovered {recovered} IDs from raw backup file")
                # Save to main JSON immediately
                self.save()

        except Exception as e:
            logger.error(f"Failed to recover from raw backup: {e}")

        return recovered

    def load_all_reg_ids(self) -> Set[str]:
        """
        Load all reg_ids from JSON file (or legacy flat file).

        Returns:
            Set of all discovered reg_ids
        """
        # Try new JSON format first
        if self.discovered_ids_file.exists():
            try:
                with open(self.discovered_ids_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return set(data.get('reg_ids', []))
            except Exception as e:
                logger.error(f"Failed to load discovered_ids.json: {e}")

        # Fall back to legacy flat file
        if self.reg_ids_file.exists():
            try:
                with open(self.reg_ids_file, 'r', encoding='utf-8') as f:
                    return set(line.strip() for line in f if line.strip())
            except Exception as e:
                logger.error(f"Failed to load reg_ids: {e}")

        return set()

    def is_reg_id_extracted(self, reg_id: str) -> bool:
        """
        Check if a registration ID has been fully extracted.

        Args:
            reg_id: Registration ID

        Returns:
            True if already extracted
        """
        return reg_id in self.extracted_reg_ids

    def mark_extracted(self, reg_id: str) -> None:
        """
        Mark a registration ID as fully extracted.

        Args:
            reg_id: Registration ID
        """
        self.extracted_reg_ids.add(reg_id)
        self.stats['total_extracted'] += 1

    def increment_errors(self) -> None:
        """Increment error count."""
        self.stats['errors'] += 1

    def start_session(self) -> None:
        """Mark the start of a scraping session."""
        if not self.stats['start_time']:
            self.stats['start_time'] = datetime.now().isoformat()

    def get_pending_reg_ids(self) -> List[str]:
        """
        Get reg_ids that have been discovered but not yet extracted.

        Returns:
            List of pending reg_ids
        """
        return [
            reg_id for reg_id in self.scraped_reg_ids
            if reg_id not in self.extracted_reg_ids
        ]

    def get_progress_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current progress.

        Returns:
            Progress summary dictionary
        """
        pending = len(self.get_pending_reg_ids())
        return {
            'prefixes_completed': len(self.completed_prefixes),
            'combinations_completed': len(self.completed_combinations),
            'total_discovered': len(self.scraped_reg_ids),
            'total_extracted': len(self.extracted_reg_ids),
            'pending_extraction': pending,
            'errors': self.stats['errors'],
            'current_prefix': self.current_prefix,
            'current_page': self.current_page,
            'current_combination': self.current_combination,
            'discovery_started_at': self.discovery_started_at,
            'discovery_last_updated': self.discovery_last_updated,
        }

    def reset(self) -> None:
        """Reset all checkpoint data and delete discovery files."""
        self.completed_prefixes.clear()
        self.completed_combinations.clear()
        self.scraped_reg_ids.clear()
        self.extracted_reg_ids.clear()
        self.current_prefix = None
        self.current_page = 0
        self.current_combination = None
        self.discovery_started_at = None
        self.discovery_last_updated = None
        self.stats = {
            "total_discovered": 0,
            "total_extracted": 0,
            "errors": 0,
            "start_time": None,
            "last_save_time": None,
        }

        # Delete discovered_ids JSON file
        if self.discovered_ids_file.exists():
            try:
                self.discovered_ids_file.unlink()
                logger.info(f"Deleted {self.discovered_ids_file}")
            except Exception as e:
                logger.error(f"Failed to delete discovered_ids file: {e}")

        # Delete legacy reg_ids file if exists
        if self.reg_ids_file.exists():
            try:
                self.reg_ids_file.unlink()
                logger.info(f"Deleted {self.reg_ids_file}")
            except Exception as e:
                logger.error(f"Failed to delete reg_ids file: {e}")

        logger.info("Checkpoint data reset")

    # Multi-dimensional search tracking methods

    def make_combination_key(
        self,
        profession: str,
        state: str,
        prefix: str,
        suburb: Optional[str] = None
    ) -> str:
        """
        Create a unique key for a search combination.

        Args:
            profession: Profession name
            state: State name
            prefix: Name prefix
            suburb: Optional suburb name

        Returns:
            Combination key string
        """
        if suburb:
            return f"{profession}|{state}|{suburb}|{prefix}"
        return f"{profession}|{state}|{prefix}"

    def is_combination_completed(self, combination_key: str) -> bool:
        """
        Check if a search combination has been completed.

        Args:
            combination_key: Combination key string

        Returns:
            True if completed
        """
        return combination_key in self.completed_combinations

    def mark_combination_completed(self, combination_key: str) -> None:
        """
        Mark a search combination as completed.

        Args:
            combination_key: Combination key string
        """
        self.completed_combinations.add(combination_key)
        self.current_combination = None
        logger.debug(f"Marked combination '{combination_key}' as completed")

    def set_current_combination(self, combination_key: str) -> None:
        """
        Set current search combination position.

        Args:
            combination_key: Combination key string
        """
        self.current_combination = combination_key

    def export_reg_ids(self, output_file: Path) -> bool:
        """
        Export discovered reg_ids to a file.

        Args:
            output_file: Output file path

        Returns:
            True if successful
        """
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for reg_id in sorted(self.scraped_reg_ids):
                    f.write(f"{reg_id}\n")
            logger.info(f"Exported {len(self.scraped_reg_ids)} reg_ids to {output_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to export reg_ids: {e}")
            return False
