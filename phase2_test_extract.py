#!/usr/bin/env python3
"""
Phase 2: Test extraction using first 10 discovered IDs.

Extracts detailed practitioner data from AHPRA API for the first 10 IDs
found in the discovery phase.
"""

import json
import sys
from pathlib import Path
from loguru import logger

from config.settings import DATA_DIR
from src.utils import setup_logging
from src.checkpoint import CheckpointManager
from src.extractor import ExtractionEngine
from src.api_client import AHPRAClient


def load_first_n_ids(n: int = 10) -> list:
    """Load first N reg IDs from discovered_ids.json"""
    discovered_file = DATA_DIR / "discovery" / "discovered_ids.json"
    
    if not discovered_file.exists():
        logger.error(f"Discovered IDs file not found: {discovered_file}")
        return []
    
    try:
        with open(discovered_file, 'r') as f:
            data = json.load(f)
        
        ids = data.get("reg_ids", [])[:n]
        logger.info(f"Loaded {len(ids)} IDs from discovered_ids.json")
        return ids
    
    except Exception as e:
        logger.error(f"Failed to load discovered IDs: {e}")
        return []


def main():
    setup_logging("phase2_extract")
    logger.info("=" * 60)
    logger.info("AHPRA Phase 2: Test Extraction (First 10 IDs)")
    logger.info("=" * 60)
    
    # Load first 10 IDs
    reg_ids = load_first_n_ids(n=10)
    
    if not reg_ids:
        logger.error("No IDs to extract")
        return 1
    
    logger.info(f"Starting extraction for {len(reg_ids)} practitioners")
    for i, rid in enumerate(reg_ids, 1):
        logger.info(f"  {i}. {rid}")
    
    # Initialize extraction engine
    checkpoint = CheckpointManager("phase2_test")
    engine = ExtractionEngine(checkpoint)
    
    if not engine.initialize():
        logger.error("Failed to initialize extraction engine")
        return 1
    
    try:
        # Extract each ID
        extracted_count = 0
        failed_ids = []
        
        for idx, reg_id in enumerate(reg_ids, 1):
            logger.info(f"\n[{idx}/{len(reg_ids)}] Extracting: {reg_id}")
            
            try:
                result = engine.extract_single(reg_id)
                
                if result:
                    extracted_count += 1
                    logger.success(f"✓ Extracted: {reg_id} - {result.get('name', 'Unknown')}")
                    # Save to CSV and backup
                    engine._save_to_json_backup(result)
                    engine._write_record(result)
                else:
                    logger.warning(f"✗ Failed to extract {reg_id}: No data returned")
                    failed_ids.append(reg_id)
            
            except Exception as e:
                logger.error(f"Error extracting {reg_id}: {e}")
                failed_ids.append(reg_id)
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("EXTRACTION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total processed: {len(reg_ids)}")
        logger.info(f"Successfully extracted: {extracted_count}")
        logger.info(f"Failed: {len(failed_ids)}")
        
        if failed_ids:
            logger.warning("Failed IDs:")
            for rid in failed_ids:
                logger.warning(f"  - {rid}")
        
        logger.info(f"Output file: {engine.output_file}")
        
        return 0 if len(failed_ids) == 0 else 1
    
    except KeyboardInterrupt:
        logger.warning("Extraction interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return 1
    finally:
        engine.close()


if __name__ == "__main__":
    sys.exit(main())
