#!/usr/bin/env python3
"""
Phase 2: Extraction pipeline for discovered IDs.

Extracts detailed practitioner data from AHPRA API in batches.
Supports resumable extraction with checkpoints.

Usage:
    python phase2_extract.py [--batch-size N] [--limit N] [--fresh] [--retry-failed]
"""

import json
import argparse
import sys
from pathlib import Path
from loguru import logger

from config.settings import DATA_DIR
from src.utils import setup_logging, format_duration
from src.checkpoint import CheckpointManager
from src.extractor import ExtractionEngine
import time


def load_discovered_ids(limit: int = None) -> list:
    """Load discovered reg IDs from JSON file"""
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
        description="Extract practitioner data from discovered IDs"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit to first N IDs (for testing)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for progress display (default: 100)"
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Start fresh, ignoring checkpoint and backup"
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry previously failed IDs"
    )

    args = parser.parse_args()
    
    setup_logging("phase2_extraction")
    logger.info("=" * 70)
    logger.info("AHPRA Phase 2: Extraction Pipeline")
    logger.info("=" * 70)
    
    # Load ALL discovered IDs (without limit - limit is applied later)
    all_reg_ids = load_discovered_ids(limit=None)
    if not all_reg_ids:
        logger.error("No IDs to extract")
        return 1

    logger.info(f"Total discovered IDs: {len(all_reg_ids):,}")
    if args.limit:
        logger.info(f"Will process up to {args.limit} IDs")

    # Initialize extraction engine with persistent checkpoint (not daily)
    checkpoint_name = "phase2_extraction"
    checkpoint = CheckpointManager(checkpoint_name)

    # Always resume by default unless --fresh is specified
    if not args.fresh:
        checkpoint.load()
        logger.info(f"Already extracted: {len(checkpoint.extracted_reg_ids)}")
    else:
        logger.info("Starting fresh (ignoring previous checkpoint)")

    # Initialize checkpoint with ALL discovered IDs (never limit scraped_reg_ids)
    checkpoint.scraped_reg_ids = set(all_reg_ids)

    engine = ExtractionEngine(checkpoint)

    if not engine.initialize():
        logger.error("Failed to initialize extraction engine")
        return 1

    # Sync backup reg_ids with checkpoint to recover from crashes
    recovered = 0
    for reg_id in engine._backup_reg_ids:
        if reg_id not in checkpoint.extracted_reg_ids:
            checkpoint.extracted_reg_ids.add(reg_id)
            recovered += 1
    if recovered > 0:
        logger.info(f"Recovered {recovered} IDs from backup to checkpoint")
        checkpoint.save()
    
    start_time = time.time()
    
    try:
        # Handle --retry-failed option
        if args.retry_failed:
            if hasattr(checkpoint, 'failed_reg_ids') and checkpoint.failed_reg_ids:
                pending = list(checkpoint.failed_reg_ids)
                checkpoint.failed_reg_ids.clear()  # Reset for retry
                logger.info(f"Retrying {len(pending)} previously failed IDs")
            else:
                logger.warning("No failed IDs to retry")
                return 0
        else:
            # Get pending IDs (those not yet extracted)
            pending = checkpoint.get_pending_reg_ids()
            # Apply limit if specified
            if args.limit and len(pending) > args.limit:
                pending = pending[:args.limit]
                logger.info(f"Limited to {args.limit} IDs")

        if not pending:
            logger.warning("No pending IDs to extract")
            return 0

        logger.info(f"Pending extractions: {len(pending):,}")
        logger.info(f"CSV output: {engine.output_file}")
        logger.info(f"JSON backup: {engine.backup_file}")
        logger.info("=" * 70)

        extracted_count = 0
        skipped_count = 0
        failed_ids = []
        consecutive_failures = 0
        total_failures_in_window = 0  # Track failures within a time window

        # Multi-layer throttling strategy (stays below WAF threshold)
        # Layer 1: Base delay in api_client.py (15-25s = ~3 req/min, well below 20 req/min threshold)
        # Layer 2: 60-second cooldown after 3 failures (resets short-term counters)
        # Layer 3: 5-minute cooldown after 3 consecutive failures (resets sliding windows)
        SHORT_COOLDOWN_THRESHOLD = 3   # Failures before 60s pause
        SHORT_COOLDOWN_DURATION = 60   # 1 minute - resets short-term WAF window
        LONG_COOLDOWN_THRESHOLD = 3    # Consecutive failures before 5-min pause
        LONG_COOLDOWN_DURATION = 300   # 5 minutes - resets long-term sliding windows

        last_progress_time = start_time

        for idx, reg_id in enumerate(pending, 1):
            try:
                # Skip if already in backup (deduplication)
                if reg_id in engine._backup_reg_ids:
                    logger.debug(f"Skipping {reg_id} - already in backup")
                    skipped_count += 1
                    continue

                # Show progress status for EVERY record
                elapsed = time.time() - start_time

                logger.info(
                    f"[{idx}/{len(pending)}] Extracting {reg_id}... "
                    f"({extracted_count} ok, {len(failed_ids)} failed, {format_duration(elapsed)})"
                )

                # Extract single practitioner
                result = engine.extract_single(reg_id)

                if result:
                    # Save to backup and CSV
                    engine._save_to_json_backup(result)
                    engine._write_record(result)
                    checkpoint.mark_extracted(reg_id)
                    extracted_count += 1
                    consecutive_failures = 0  # Reset on success
                    total_failures_in_window = 0  # Reset failure window on success

                    # Get practitioner name for confirmation
                    name = result.get('name', 'Unknown')
                    logger.info(f"    -> Extracted: {name}")

                    # Show detailed progress every batch_size or every 5 minutes
                    current_time = time.time()
                    if extracted_count % args.batch_size == 0 or (current_time - last_progress_time) > 300:
                        last_progress_time = current_time
                        rate = extracted_count / elapsed if elapsed > 0 else 0
                        remaining = len(pending) - idx
                        eta = remaining / rate if rate > 0 else 0

                        logger.info(
                            f"--- Progress: {extracted_count}/{len(pending)} extracted, "
                            f"{rate:.2f} records/sec, "
                            f"~{format_duration(eta)} remaining ---"
                        )
                else:
                    failed_ids.append(reg_id)
                    consecutive_failures += 1
                    total_failures_in_window += 1
                    # Track failed IDs in checkpoint
                    if hasattr(checkpoint, 'failed_reg_ids'):
                        checkpoint.failed_reg_ids.add(reg_id)
                    logger.warning(f"    -> Failed to extract {reg_id}")

                    # Layer 2: Short cooldown after N failures (resets short-term WAF counters)
                    if total_failures_in_window >= SHORT_COOLDOWN_THRESHOLD:
                        logger.warning(
                            f"Detected {total_failures_in_window} failures in window - "
                            f"applying {SHORT_COOLDOWN_DURATION}s cooldown to reset short-term counters..."
                        )
                        checkpoint.save()
                        time.sleep(SHORT_COOLDOWN_DURATION)
                        total_failures_in_window = 0
                        logger.info("Short cooldown complete. Resuming...")

                    # Layer 3: Long cooldown after consecutive failures (resets sliding windows)
                    if consecutive_failures >= LONG_COOLDOWN_THRESHOLD:
                        logger.warning(
                            f"Detected {consecutive_failures} consecutive failures - "
                            f"possible rate limiting. Applying {LONG_COOLDOWN_DURATION}s cooldown to reset WAF windows..."
                        )
                        checkpoint.save()
                        # Reset the API session to get fresh cookies
                        engine.api_client.session.close()
                        engine.api_client._cookies_initialized = False
                        engine.api_client._setup_session()
                        # 5-minute pause to let WAF sliding windows reset
                        time.sleep(LONG_COOLDOWN_DURATION)
                        consecutive_failures = 0
                        logger.info("Long cooldown complete. Session reset. Resuming extraction...")

            except KeyboardInterrupt:
                logger.warning("Extraction interrupted by user")
                checkpoint.save()
                break
            except Exception as e:
                logger.debug(f"Error extracting {reg_id}: {e}")
                failed_ids.append(reg_id)
                if hasattr(checkpoint, 'failed_reg_ids'):
                    checkpoint.failed_reg_ids.add(reg_id)
        
        # Final summary
        elapsed = time.time() - start_time
        logger.info("=" * 70)
        logger.info("EXTRACTION SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Successfully extracted: {extracted_count}")
        logger.info(f"Skipped (already in backup): {skipped_count}")
        logger.info(f"Failed: {len(failed_ids)}")
        actual_processed = extracted_count + len(failed_ids)
        if actual_processed > 0:
            logger.info(f"Success rate: {extracted_count / actual_processed * 100:.1f}%")
        logger.info(f"Time elapsed: {format_duration(elapsed)}")
        if elapsed > 0:
            logger.info(f"Average rate: {extracted_count / elapsed:.1f} records/sec")
        logger.info(f"CSV output: {engine.output_file}")
        logger.info(f"JSON backup: {engine.backup_file}")

        if failed_ids and len(failed_ids) <= 10:
            logger.warning(f"Failed IDs: {', '.join(failed_ids)}")
        elif failed_ids:
            logger.warning(f"Failed IDs: {len(failed_ids)} total (use --retry-failed to retry)")
        
        # Save checkpoint
        checkpoint.save()
        
        return 0 if len(failed_ids) == 0 else 1
    
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        checkpoint.save()
        return 1
    finally:
        engine.close()


if __name__ == "__main__":
    sys.exit(main())
