#!/usr/bin/env python3
"""
Multi-dimensional test script to search for "shrestha" variations:
- Different name prefixes (SH, SHR, SHRE)
- Multiple searches to find all matching practitioners
- Combines all results and extracts data
"""

from loguru import logger
from collections import defaultdict
from config.settings import AHPRA_SEARCH_URL
from src.browser import BrowserManager
from src.api_client import AHPRAClient
from src.parser import PractitionerParser
from src.utils import random_delay

# Setup logging
logger.add("logs/test_shrestha_multidim.log", rotation="10 MB")


def search_shrestha_variations():
    """
    Search for 'shrestha' and related name prefixes for comprehensive results.
    Returns dict: {search_term: [reg_ids]}
    """
    logger.info("Starting multi-dimensional search for 'shrestha' variations")
    
    search_terms = [
        "shrestha",      # Full name
        "shresth",       # Partial (catches typos)
        "shretha",       # Alternative spelling
    ]
    
    results = defaultdict(list)
    total_found = 0
    
    with BrowserManager(headless=False) as browser:
        for search_term in search_terms:
            try:
                logger.info(f"Searching for: '{search_term}'")
                
                # Navigate to search page
                browser.navigate(AHPRA_SEARCH_URL, wait_until='domcontentloaded')
                random_delay(1, 2)
                
                # Fill in the search field
                search_input = browser.page.query_selector('#name-reg')
                if search_input:
                    search_input.click()
                    search_input.fill('')
                    random_delay(0.2, 0.4)
                    search_input.fill(search_term)
                    random_delay(0.3, 0.5)
                    
                    # Click search button
                    search_button = browser.page.query_selector('#predictiveSearchHomeBtn')
                    if search_button:
                        search_button.click()
                        random_delay(1, 2)
                        
                        # Wait for results or no-results message
                        try:
                            browser.page.wait_for_selector(
                                '.search-results-table-row, .no-results-message',
                                timeout=30000
                            )
                        except:
                            logger.warning(f"Timeout waiting for results: {search_term}")
                            continue
                        
                        # Extract registration IDs
                        result_rows = browser.page.query_selector_all(
                            '.search-results-table-row[data-practitioner-row-id]'
                        )
                        
                        if result_rows:
                            logger.info(f"Found {len(result_rows)} results for '{search_term}'")
                            for row in result_rows:
                                reg_id = row.get_attribute('data-practitioner-row-id')
                                if reg_id and reg_id not in results[search_term]:
                                    results[search_term].append(reg_id)
                                    total_found += 1
                        else:
                            logger.info(f"No results for '{search_term}'")
                
                random_delay(2, 3)  # Delay between searches
                
            except Exception as e:
                logger.error(f"Error searching '{search_term}': {e}")
                continue
    
    logger.info(f"Multi-dimensional search complete. Total found: {total_found}")
    return results


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
    print("\n" + "=" * 80)
    print("AHPRA Data Scraper - Multi-Dimensional Search for 'shrestha' Variations")
    print("=" * 80 + "\n")
    
    # Multi-dimensional search
    results = search_shrestha_variations()
    
    # Flatten results and track by search term
    all_reg_ids = set()
    search_summary = {}
    
    for search_term, reg_ids in results.items():
        unique_ids = list(set(reg_ids))
        search_summary[search_term] = len(unique_ids)
        all_reg_ids.update(unique_ids)
    
    if not all_reg_ids:
        print("❌ No practitioners found\n")
        return 1
    
    all_reg_ids = list(all_reg_ids)
    
    print(f"\n✅ Search Summary:")
    print("-" * 80)
    for search_term, count in sorted(search_summary.items()):
        print(f"  '{search_term:15s}': {count:3d} practitioners found")
    print(f"\n  Total unique practitioners: {len(all_reg_ids)}")
    
    print("\n" + "=" * 80)
    print("Extracting detailed data for each practitioner...")
    print("=" * 80 + "\n")
    
    # Extract data for each unique reg_id
    extracted_data = []
    for i, reg_id in enumerate(all_reg_ids, 1):
        print(f"\n[{i}/{len(all_reg_ids)}] Extracting: {reg_id}")
        print("-" * 80)
        
        data = extract_practitioner_data(reg_id)
        
        if data:
            extracted_data.append(data)
            for field, value in data.items():
                if value:
                    print(f"  {field:20s}: {value}")
        else:
            print("  ❌ Failed to extract data")
        
        random_delay(2, 3)  # Delay between extractions
    
    print(f"\n{'=' * 80}")
    print(f"Successfully extracted data for {len(extracted_data)}/{len(all_reg_ids)} practitioners")
    print("=" * 80 + "\n")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
