#!/usr/bin/env python3
"""
Debug script to explore sidebar filters on AHPRA search results page.

This script:
1. Performs a search to get to the results page
2. Explores the sidebar filter elements
3. Reports all available filter options and their selectors
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.browser import BrowserManager
from config.settings import AHPRA_SEARCH_URL


def explore_sidebar_filters():
    """Explore and document sidebar filters on the results page."""

    print("=" * 70)
    print("AHPRA Sidebar Filter Explorer")
    print("=" * 70)

    with BrowserManager(headless=False) as browser:
        # Navigate to search page
        print("\n1. Navigating to AHPRA search page...")
        browser.navigate(AHPRA_SEARCH_URL, wait_until='domcontentloaded')
        time.sleep(2)

        # Perform a simple search to get to results page
        print("\n2. Performing search with prefix 'A'...")

        # Fill search input
        search_input = browser.page.query_selector('#name-reg')
        if search_input:
            search_input.fill('A')
            time.sleep(0.5)

        # Click search button
        search_btn = browser.page.query_selector('#predictiveSearchHomeBtn')
        if search_btn:
            search_btn.click()
            time.sleep(3)  # Wait for results

        print("\n3. Exploring sidebar filters on results page...")
        print("-" * 70)

        # Look for common sidebar/filter patterns
        filter_selectors = [
            # Common sidebar filter patterns
            '.sidebar', '.side-bar', '.filter-sidebar', '.filters',
            '.facet', '.facets', '.faceted-search',
            '.search-filters', '.filter-panel', '.filter-section',
            '.refinement', '.refinements',

            # Dropdown patterns
            'select[name*="profession"]', 'select[name*="state"]',
            'select[name*="location"]', 'select[name*="sex"]',
            'select[name*="language"]',

            # AHPRA-specific patterns (guesses)
            '.profession-filter', '.state-filter', '.location-filter',
            '#profession-filter', '#state-filter', '#location-filter',
            '.filter-dropdown', '.filter-select',

            # Left panel patterns
            '.left-panel', '.left-sidebar', '.search-refine',
            '.search-options', '.advanced-filters',

            # Accordion patterns (filters often in accordions)
            '.accordion', '.collapsible', '.expandable',

            # List-based filters
            'ul.filter-list', '.filter-options', '.checkbox-filter',
        ]

        print("\nSearching for filter elements...")
        found_elements = []

        for selector in filter_selectors:
            try:
                elements = browser.page.query_selector_all(selector)
                if elements:
                    found_elements.append((selector, len(elements)))
                    print(f"  ✓ Found {len(elements)} element(s): {selector}")
            except Exception:
                pass

        if not found_elements:
            print("  No common filter selectors found.")

        # Get all select elements on the page
        print("\n4. All SELECT elements on the page:")
        print("-" * 70)
        selects = browser.page.query_selector_all('select')
        for i, select in enumerate(selects):
            try:
                select_id = select.get_attribute('id') or 'no-id'
                select_name = select.get_attribute('name') or 'no-name'
                select_class = select.get_attribute('class') or 'no-class'

                # Get options
                options = select.query_selector_all('option')
                option_texts = [opt.text_content()[:30] for opt in options[:5]]

                print(f"\n  SELECT #{i + 1}:")
                print(f"    ID: {select_id}")
                print(f"    Name: {select_name}")
                print(f"    Class: {select_class[:50]}...")
                print(f"    Options ({len(options)} total): {option_texts}")
            except Exception as e:
                print(f"  Error reading select: {e}")

        # Look for any elements with "filter" in their class or id
        print("\n5. Elements containing 'filter' in class/id:")
        print("-" * 70)

        # Use JavaScript to find all elements with filter in class or id
        filter_elements = browser.page.evaluate("""
            () => {
                const results = [];
                const all = document.querySelectorAll('*');
                for (const el of all) {
                    const id = el.id || '';
                    const cls = el.className || '';
                    if (typeof cls === 'string' && (
                        id.toLowerCase().includes('filter') ||
                        cls.toLowerCase().includes('filter') ||
                        id.toLowerCase().includes('facet') ||
                        cls.toLowerCase().includes('facet') ||
                        id.toLowerCase().includes('refine') ||
                        cls.toLowerCase().includes('refine')
                    )) {
                        results.push({
                            tag: el.tagName,
                            id: id,
                            class: cls.substring(0, 100),
                            text: el.textContent.substring(0, 50).trim()
                        });
                    }
                }
                return results.slice(0, 20);  // Limit to first 20
            }
        """)

        if filter_elements:
            for elem in filter_elements:
                print(f"  <{elem['tag']}> id='{elem['id']}' class='{elem['class']}'")
                if elem['text']:
                    print(f"    Text: {elem['text'][:50]}...")
        else:
            print("  No elements with 'filter' in class/id found.")

        # Look for the left sidebar content specifically
        print("\n6. Looking for sidebar/left panel structure:")
        print("-" * 70)

        sidebar_html = browser.page.evaluate("""
            () => {
                // Look for common left sidebar patterns
                const patterns = [
                    '.col-md-3', '.col-lg-3', '.col-sm-4',  // Bootstrap columns
                    'aside', '.aside',
                    '[class*="sidebar"]', '[class*="side-bar"]',
                    '[class*="left"]', '[class*="panel"]',
                    '.search-filters', '.filters-container'
                ];

                for (const pattern of patterns) {
                    const el = document.querySelector(pattern);
                    if (el && el.innerHTML.length > 100) {
                        return {
                            selector: pattern,
                            html: el.outerHTML.substring(0, 2000),
                            text: el.textContent.substring(0, 500)
                        };
                    }
                }
                return null;
            }
        """)

        if sidebar_html:
            print(f"  Found sidebar with selector: {sidebar_html['selector']}")
            print(f"  Text content preview:\n{sidebar_html['text'][:300]}...")
        else:
            print("  No obvious sidebar structure found.")

        # Get all elements that look like they might be dropdowns or filters
        print("\n7. Looking for dropdown/accordion patterns:")
        print("-" * 70)

        dropdowns = browser.page.evaluate("""
            () => {
                const results = [];

                // Look for elements that might be dropdowns
                const candidates = document.querySelectorAll(`
                    [class*="dropdown"],
                    [class*="select"],
                    [class*="combo"],
                    [class*="accordion"],
                    [role="listbox"],
                    [role="combobox"],
                    details,
                    summary
                `);

                for (const el of candidates) {
                    results.push({
                        tag: el.tagName,
                        id: el.id,
                        class: (el.className || '').substring(0, 80),
                        role: el.getAttribute('role'),
                        text: el.textContent.substring(0, 50).trim()
                    });
                }

                return results.slice(0, 15);
            }
        """)

        if dropdowns:
            for d in dropdowns:
                print(f"  <{d['tag']}> id='{d['id']}' role='{d['role']}'")
                print(f"    class: {d['class']}")
                print(f"    text: {d['text'][:40]}...")
        else:
            print("  No dropdown/accordion patterns found.")

        # Check the page structure more broadly
        print("\n8. Page structure overview (main sections):")
        print("-" * 70)

        sections = browser.page.evaluate("""
            () => {
                const results = [];
                const mainSections = document.querySelectorAll('main, section, article, div.container, div.row');

                for (const section of mainSections) {
                    if (section.children.length > 0) {
                        results.push({
                            tag: section.tagName,
                            id: section.id,
                            class: (section.className || '').substring(0, 60),
                            childCount: section.children.length,
                            hasSelect: section.querySelector('select') !== null,
                            hasInput: section.querySelector('input') !== null
                        });
                    }
                }

                return results.slice(0, 15);
            }
        """)

        for s in sections:
            has_filters = "✓" if (s['hasSelect'] or s['hasInput']) else " "
            print(f"  [{has_filters}] <{s['tag']}> id='{s['id']}' class='{s['class'][:40]}' children={s['childCount']}")

        print("\n" + "=" * 70)
        print("Exploration complete. Check the browser window to visually inspect")
        print("the sidebar filters you mentioned.")
        print("=" * 70)

        # Keep browser open for manual inspection
        input("\nPress Enter to close the browser...")


if __name__ == "__main__":
    explore_sidebar_filters()
