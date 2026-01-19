#!/usr/bin/env python3
"""
Phase 2: Extraction pipeline for discovered IDs.

Extracts detailed practitioner data from AHPRA API in batches.
Supports resumable extraction with checkpoints.

Usage:
    python phase2_extract.py [--batch-size N] [--limit N] [--resume]
"""

import json
import argparse
import sys
from pathlib import Path
from loguru import logger

from config.settings import DATA_DIR
from src.utils import setup_logging, format_duration, get_date_string
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
        "--resume",
        action="store_true",
        help="Resume from checkpoint"
    )
    
    args = parser.parse_args()
    
    setup_logging("phase2_extraction")
    logger.info("=" * 70)
    logger.info("AHPRA Phase 2: Extraction Pipeline")
    logger.info("=" * 70)
    
    # Load discovered IDs
    all_reg_ids = load_discovered_ids(limit=args.limit)
    if not all_reg_ids:
        logger.error("No IDs to extract")
        return 1
    
    logger.info(f"Total IDs to process: {len(all_reg_ids):,}")
    
    # Initialize extraction engine
    checkpoint_name = f"phase2_extraction_{get_date_string()}"
    checkpoint = CheckpointManager(checkpoint_name)
    
    # Initialize or resume from checkpoint
    if args.resume and checkpoint.load():
        logger.info(f"Resuming from checkpoint")
        extracted = len(checkpoint.extracted_reg_ids)
        logger.info(f"Already extracted: {extracted}")
    else:
        # New extraction - initialize checkpoint with all IDs
        checkpoint.scraped_reg_ids = set(all_reg_ids)
    
    engine = ExtractionEngine(checkpoint)
    
    if not engine.initialize():
        logger.error("Failed to initialize extraction engine")
        return 1
    
    start_time = time.time()
    
    try:
        # Get pending IDs (those not yet extracted)
        pending = checkpoint.get_pending_reg_ids()
        if not pending:
            logger.warning("No pending IDs to extract")
            return 0
        
        logger.info(f"Pending extractions: {len(pending):,}")
        logger.info(f"CSV output: {engine.output_file}")
        logger.info(f"JSON backup: {engine.backup_file}")
        logger.info("=" * 70)
        
        extracted_count = 0
        failed_ids = []
        
        for idx, reg_id in enumerate(pending, 1):
            try:
                # Extract single practitioner
                result = engine.extract_single(reg_id)
                
                if result:
                    # Save to backup and CSV
                    engine._save_to_json_backup(result)
                    engine._write_record(result)
                    checkpoint.mark_extracted(reg_id)
                    extracted_count += 1
                    
                    # Display progress
                    if extracted_count % args.batch_size == 0:
                        elapsed = time.time() - start_time
                        rate = extracted_count / elapsed
                        remaining = len(pending) - extracted_count
                        eta = remaining / rate if rate > 0 else 0
                        
                        logger.info(
                            f"[{extracted_count}/{len(pending)}] "
                            f"{elapsed:.0f}s elapsed, "
                            f"{rate:.1f} records/sec, "
                            f"~{format_duration(eta)} remaining"
                        )
                else:
                    failed_ids.append(reg_id)
                    logger.debug(f"Failed to extract: {reg_id}")
            
            except KeyboardInterrupt:
                logger.warning("Extraction interrupted by user")
                checkpoint.save()
                break
            except Exception as e:
                logger.debug(f"Error extracting {reg_id}: {e}")
                failed_ids.append(reg_id)
        
        # Final summary
        elapsed = time.time() - start_time
        logger.info("=" * 70)
        logger.info("EXTRACTION SUMMARY")
        logger.info("=" * 70)
        logger.info(f"Successfully extracted: {extracted_count}")
        logger.info(f"Failed: {len(failed_ids)}")
        logger.info(f"Success rate: {extracted_count / len(pending) * 100:.1f}%")
        logger.info(f"Time elapsed: {format_duration(elapsed)}")
        logger.info(f"Average rate: {extracted_count / elapsed:.1f} records/sec")
        logger.info(f"CSV output: {engine.output_file}")
        logger.info(f"JSON backup: {engine.backup_file}")
        
        if failed_ids and len(failed_ids) <= 10:
            logger.warning(f"Failed IDs: {', '.join(failed_ids)}")
        
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
