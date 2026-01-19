#!/usr/bin/env python3
"""
Test script to search for "shrestha" practitioners and extract their data.
"""

from loguru import logger
from config.settings import AHPRA_SEARCH_URL
from src.browser import BrowserManager
from src.api_client import AHPRAClient
from src.parser import PractitionerParser

# Setup logging
logger.add("logs/test_shrestha.log", rotation="10 MB")

def search_shrestha():
    """Search for practitioners named 'shrestha' and collect their reg_ids."""
    logger.info("Starting search for 'shrestha'")
    
    reg_ids = []
    
    with BrowserManager(headless=False) as browser:
        # Navigate to search page
        logger.info("Navigating to AHPRA search page...")
        browser.navigate(AHPRA_SEARCH_URL)
        
        # Fill in the search field
        logger.info("Searching for 'shrestha'...")
        search_input = browser.page.query_selector('#name-reg')
        if search_input:
            search_input.click()
            search_input.fill('')
            search_input.fill('shrestha')
            
            # Click search button
            search_button = browser.page.query_selector('#predictiveSearchHomeBtn')
            if search_button:
                search_button.click()
                
                # Wait for results
                browser.page.wait_for_selector('.search-results-table-row', timeout=30000)
                
                # Extract registration IDs
                result_rows = browser.page.query_selector_all('.search-results-table-row[data-practitioner-row-id]')
                logger.info(f"Found {len(result_rows)} results for 'shrestha'")
                
                for row in result_rows:
                    reg_id = row.get_attribute('data-practitioner-row-id')
                    if reg_id:
                        reg_ids.append(reg_id)
                        logger.info(f"Found reg_id: {reg_id}")
    
    return reg_ids

def extract_practitioner_data(reg_id):
    """Extract detailed data for a single practitioner via API POST."""
    logger.info(f"Extracting data for reg_id: {reg_id}")
    
    client = AHPRAClient()
    parser = PractitionerParser()
    
    try:
        # Fetch practitioner data via API POST
        html_response = client.fetch_practitioner(reg_id)
        
        if html_response:
            # Parse the HTML response
            data = parser.parse(html_response)
            return data
        else:
            logger.error(f"Failed to fetch data for {reg_id}")
            return None
    finally:
        client.close()

def main():
    """Main test function."""
    print("\n" + "=" * 70)
    print("AHPRA Data Scraper - Test Search for 'shrestha'")
    print("=" * 70 + "\n")
    
    # Search for shrestha
    reg_ids = search_shrestha()
    
    if not reg_ids:
        print("❌ No practitioners found with name 'shrestha'\n")
        return 1
    
    print(f"\n✅ Found {len(reg_ids)} practitioner(s) named 'shrestha':\n")
    
    # Extract data for each practitioner
    for i, reg_id in enumerate(reg_ids, 1):
        print(f"\n{'=' * 70}")
        print(f"Practitioner {i}/{len(reg_ids)}: {reg_id}")
        print("=" * 70)
        
        data = extract_practitioner_data(reg_id)
        
        if data:
            for field, value in data.items():
                if value:
                    print(f"  {field:20s}: {value}")
        else:
            print("  ❌ Failed to extract data")
    
    print(f"\n{'=' * 70}\n")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
