#!/usr/bin/env python3
"""
Debug script to verify dropdown selection is working correctly.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from src.browser import BrowserManager
from src.utils import setup_logging, ui_delay, random_delay
from config.settings import AHPRA_SEARCH_URL

# Configure logging to show debug messages
logger.remove()
logger.add(sys.stderr, level="DEBUG")

def debug_dropdown_selection():
    """Debug the dropdown selection to see if filters are being applied."""

    print("\n" + "=" * 70)
    print("DEBUG: Testing AHPRA Dropdown Selection")
    print("=" * 70)

    with BrowserManager(headless=False) as browser:  # Visible browser for debugging
        # Navigate to search page
        print("\n1. Navigating to AHPRA search page...")
        browser.navigate(AHPRA_SEARCH_URL, wait_until='domcontentloaded')
        random_delay(2, 3)

        page = browser.page

        # Step 1: Check what dropdown elements exist
        print("\n2. Looking for dropdown elements...")

        # Check profession dropdown
        profession_dropdown = page.query_selector('#health-profession-dropdown')
        if profession_dropdown:
            print(f"   ✓ Profession dropdown found: {profession_dropdown.get_attribute('class')}")
            # Get current value
            current_text = profession_dropdown.text_content()
            print(f"   Current value: '{current_text}'")
        else:
            print("   ✗ Profession dropdown NOT found with #health-profession-dropdown")
            # Try to find any dropdown-like elements
            all_dropdowns = page.query_selector_all('[class*="dropdown"], select, [role="listbox"]')
            print(f"   Found {len(all_dropdowns)} dropdown-like elements")
            for i, dd in enumerate(all_dropdowns[:5]):
                print(f"     {i+1}. {dd.get_attribute('id')} - {dd.get_attribute('class')}")

        # Check state dropdown
        state_dropdown = page.query_selector('#state-dropdown')
        if state_dropdown:
            print(f"   ✓ State dropdown found: {state_dropdown.get_attribute('class')}")
            current_text = state_dropdown.text_content()
            print(f"   Current value: '{current_text}'")
        else:
            print("   ✗ State dropdown NOT found with #state-dropdown")

        # Step 2: Try clicking the profession dropdown
        print("\n3. Attempting to click profession dropdown...")
        if profession_dropdown:
            profession_dropdown.click()
            ui_delay(1, 2)

            # Look for dropdown options
            print("   Looking for dropdown options...")
            options = page.query_selector_all('li, .dropdown-item, [role="option"], .dropdown-menu li')
            print(f"   Found {len(options)} potential options")

            visible_options = []
            for opt in options:
                if opt.is_visible():
                    text = opt.text_content().strip()
                    if text and len(text) < 100:  # Filter out noise
                        visible_options.append(text)

            print(f"   Visible options ({len(visible_options)}):")
            for i, opt in enumerate(visible_options[:10]):
                print(f"     {i+1}. {opt}")

            # Try to select "Medical Practitioner"
            print("\n4. Attempting to select 'Medical Practitioner'...")

            # Method 1: Look for exact text match
            med_option = page.query_selector('text="Medical Practitioner"')
            if med_option and med_option.is_visible():
                print("   Found via text selector, clicking...")
                med_option.click()
                ui_delay()
            else:
                print("   Not found via text selector, trying alternatives...")

                # Method 2: Search through all options
                for opt in options:
                    if opt.is_visible():
                        text = opt.text_content() or ''
                        if 'Medical Practitioner' in text:
                            print(f"   Found: '{text}', clicking...")
                            opt.click()
                            ui_delay()
                            break
                else:
                    print("   ✗ Could not find 'Medical Practitioner' option")

            # Check if selection was applied
            ui_delay(1, 2)
            new_text = profession_dropdown.text_content()
            print(f"   Dropdown value after selection: '{new_text}'")

        # Step 3: Try the state dropdown
        print("\n5. Attempting to click state dropdown...")
        state_dropdown = page.query_selector('#state-dropdown')
        if state_dropdown:
            state_dropdown.click()
            ui_delay(1, 2)

            options = page.query_selector_all('li, .dropdown-item, [role="option"]')
            visible_options = [opt.text_content().strip() for opt in options if opt.is_visible() and opt.text_content()]
            print(f"   Visible state options: {visible_options[:10]}")

            # Try to select "VIC" (abbreviation)
            print("\n6. Attempting to select 'VIC' (abbreviation)...")
            vic_option = page.query_selector('text="VIC"')
            if vic_option and vic_option.is_visible():
                print("   Found 'VIC' via text selector, clicking...")
                vic_option.click()
                ui_delay()
            else:
                for opt in options:
                    if opt.is_visible() and opt.text_content() and opt.text_content().strip() == 'VIC':
                        print(f"   Found: '{opt.text_content()}', clicking...")
                        opt.click()
                        ui_delay()
                        break

            ui_delay(1, 2)
            new_text = state_dropdown.text_content()
            print(f"   State dropdown value after selection: '{new_text}'")

        # Step 4: Fill search and submit
        print("\n7. Filling search term 'A' and submitting...")
        search_input = page.query_selector('#name-reg')
        if search_input:
            search_input.fill('A')
            ui_delay()

            search_button = page.query_selector('#predictiveSearchHomeBtn')
            if search_button:
                search_button.click()
                print("   Search submitted, waiting for results...")
                random_delay(3, 5)

                # Check results
                result_rows = page.query_selector_all('.search-results-table-row[data-practitioner-row-id]')
                print(f"\n8. Results found: {len(result_rows)}")

                # Show first few results to verify they match filters
                if result_rows:
                    print("\n   First 5 results:")
                    for i, row in enumerate(result_rows[:5]):
                        name_el = row.query_selector('a')
                        name = name_el.text_content() if name_el else 'N/A'

                        # Try to get profession from the row
                        prof_el = row.query_selector('.search-results-table-col:nth-child(2) .text p')
                        prof = prof_el.text_content() if prof_el else 'N/A'

                        # Try to get location
                        loc_el = row.query_selector('.search-results-table-col:last-child .text p')
                        loc = loc_el.text_content() if loc_el else 'N/A'

                        print(f"     {i+1}. {name} | {prof} | {loc}")

        print("\n" + "=" * 70)
        print("Debug complete. Check if filters were applied correctly.")
        print("=" * 70)

        # Keep browser open for manual inspection
        input("\nPress Enter to close browser...")


if __name__ == "__main__":
    debug_dropdown_selection()
