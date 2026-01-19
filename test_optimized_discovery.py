#!/usr/bin/env python3
"""
Test script for OPTIMIZED discovery using sidebar filters.

This tests the new optimized approach that uses sidebar filters on the
results page instead of navigating back to home for each combination.

Usage:
    # Quick test with one profession, one state, one prefix
    python test_optimized_discovery.py --prefix A --quick

    # Test with one prefix (all professions, all states)
    python test_optimized_discovery.py --prefix A

    # Full test (all prefixes A-Z)
    python test_optimized_discovery.py --full

    # Visible browser for debugging
    python test_optimized_discovery.py --prefix A --no-headless
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import CHECKPOINT_DIR, DISCOVERY_DIR
from src.browser import BrowserManager
from src.checkpoint import CheckpointManager
from src.discovery import DiscoveryEngine


def main():
    parser = argparse.ArgumentParser(description="Test optimized sidebar filter discovery")
    parser.add_argument('--prefix', type=str, default='A', help='Test prefix (default: A)')
    parser.add_argument('--quick', action='store_true', help='Quick test (limited combinations)')
    parser.add_argument('--full', action='store_true', help='Full test (all prefixes A-Z)')
    parser.add_argument('--no-headless', action='store_true', help='Show browser window')
    parser.add_argument('--no-optimized', action='store_true', help='Use standard mode (for comparison)')

    args = parser.parse_args()

    print("=" * 70)
    print("OPTIMIZED DISCOVERY TEST (Sidebar Filters)")
    print("=" * 70)

    # Determine test mode
    if args.full:
        test_prefix = None
        mode_desc = "FULL (all prefixes A-Z)"
    else:
        test_prefix = args.prefix.upper()
        mode_desc = f"Single prefix '{test_prefix}'"

    use_optimized = not args.no_optimized

    print(f"Mode: {mode_desc}")
    print(f"Optimized (sidebar filters): {'YES' if use_optimized else 'NO'}")
    print(f"Headless: {'YES' if not args.no_headless else 'NO (visible browser)'}")

    # Create isolated checkpoint for this test
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    checkpoint_name = f"test_optimized_{test_prefix or 'full'}_{timestamp}"
    test_discovered_ids_file = DISCOVERY_DIR / f"test_optimized_ids_{test_prefix or 'full'}_{timestamp}.json"

    print(f"\nCheckpoint: {checkpoint_name}")
    print(f"Discovered IDs will be saved to: {test_discovered_ids_file.name}")

    # Confirm
    response = input("\nProceed with test? (y/n): ")
    if response.lower() != 'y':
        print("Test cancelled.")
        return

    checkpoint = CheckpointManager(checkpoint_name, discovered_ids_file=test_discovered_ids_file)

    start_time = datetime.now()

    try:
        with BrowserManager(headless=not args.no_headless) as browser:
            engine = DiscoveryEngine(
                browser,
                checkpoint,
                multi_dimensional=True,
                include_suburbs=False,
                test_prefix=test_prefix,
                use_optimized=use_optimized
            )

            if not engine.initialize():
                print("ERROR: Failed to initialize discovery engine")
                return

            print("\n" + "=" * 70)
            print("STARTING OPTIMIZED DISCOVERY")
            print("=" * 70 + "\n")

            # Run discovery
            discovered = engine.run_discovery(resume=False)

            end_time = datetime.now()
            duration = end_time - start_time

            print("\n" + "=" * 70)
            print("TEST COMPLETE")
            print("=" * 70)
            print(f"Duration: {duration}")
            print(f"Total discovered: {discovered:,}")
            print(f"Unique IDs: {len(checkpoint.scraped_reg_ids):,}")
            print(f"Errors: {checkpoint.stats['errors']}")
            print(f"Discovered IDs saved to: {test_discovered_ids_file}")
            print("=" * 70)

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        checkpoint.save()
        print(f"Progress saved. Discovered so far: {len(checkpoint.scraped_reg_ids):,}")

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
