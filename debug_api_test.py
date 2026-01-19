#!/usr/bin/env python3
"""
Debug script to test API connectivity and extraction.
"""

import json
from src.api_client import AHPRAClient
from src.parser import PractitionerParser
from loguru import logger

# Test first 3 IDs with detailed debugging
test_ids = [
    "OCC0002418114",
    "OPT0001581253", 
    "OST0002740494"
]

def main():
    logger.remove()
    logger.add(lambda msg: print(msg, end=''))
    logger.add(
        "logs/debug_api_test_{time:YYYY-MM-DD_HH-mm-ss}.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    )
    
    logger.info("Testing AHPRA API Client")
    logger.info("=" * 60)
    
    # Test connection
    client = AHPRAClient()
    logger.info(f"Testing connection to AHPRA...")
    if client.test_connection():
        logger.success("✓ Connection successful")
    else:
        logger.error("✗ Connection failed")
        return 1
    
    parser = PractitionerParser()
    
    for reg_id in test_ids:
        logger.info(f"\nFetching data for: {reg_id}")
        html = client.fetch_practitioner(reg_id)
        
        if html:
            logger.info(f"✓ Got HTML response ({len(html)} bytes)")
            
            # Show first 500 chars
            logger.debug(f"HTML preview:\n{html[:500]}")
            
            # Try to parse
            try:
                data = parser.parse(html)
                logger.info(f"✓ Parsed data: {json.dumps(data, indent=2)}")
            except Exception as e:
                logger.error(f"✗ Parse error: {e}")
        else:
            logger.error(f"✗ Failed to fetch HTML")
    
    client.close()
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
