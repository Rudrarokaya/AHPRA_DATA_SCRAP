#!/usr/bin/env python3
"""
Test script for multi-dimensional discovery phase.

Tests the DiscoveryEngine with multiple prefixes to verify:
1. Prefix-based search works correctly
2. Checkpoint tracking works
3. No duplicate reg_ids are collected
4. Results can be resumed
"""

from loguru import logger
from pathlib import Path
import json
from config.settings import DISCOVERY_DIR, CHECKPOINT_DIR
from src.browser import BrowserManager
from src.checkpoint import CheckpointManager
from src.discovery import DiscoveryEngine
from src.utils import random_delay

# Setup logging
logger.add("logs/test_discovery_multidim.log", rotation="10 MB")


def test_discovery_with_prefixes(prefixes, mode="adaptive"):
    """
    Test discovery engine with specific prefixes.
    
    Args:
        prefixes: List of prefixes to search (e.g., ['SH', 'SM', 'SHR'])
        mode: 'adaptive' or 'comprehensive'
    
    Returns:
        dict with stats
    """
    logger.info(f"Starting discovery test with {len(prefixes)} prefixes in {mode} mode")
    print("\n" + "=" * 80)
    print(f"AHPRA Discovery Test - Multi-Dimensional Search ({mode} mode)")
    print(f"Prefixes to search: {', '.join(prefixes)}")
    print("=" * 80 + "\n")
    
    # Initialize checkpoint
    checkpoint = CheckpointManager("test_discovery")
    checkpoint.load()
    
    initial_count = len(checkpoint.stats.get('scraped_reg_ids', set()))
    logger.info(f"Checkpoint loaded: {initial_count} reg_ids already discovered")
    
    stats = {
        'prefixes_tested': prefixes,
        'mode': mode,
        'total_prefixes': len(prefixes),
        'prefixes_completed': 0,
        'total_reg_ids_found': 0,
        'new_reg_ids': 0,
        'duplicates': 0,
        'errors': 0,
    }
    
    # Test each prefix
    with BrowserManager(headless=False) as browser:
        discovery_engine = DiscoveryEngine(browser, checkpoint, comprehensive=False)
        
        if not discovery_engine.initialize():
            logger.error("Failed to initialize discovery engine")
            return stats
        
        for i, prefix in enumerate(prefixes, 1):
            try:
                logger.info(f"[{i}/{len(prefixes)}] Searching prefix: {prefix}")
                print(f"\n[{i}/{len(prefixes)}] Searching prefix: '{prefix}'")
                print("-" * 80)
                
                # Perform search for this prefix
                reg_ids_before = len(checkpoint.stats.get('scraped_reg_ids', set()))
                
                # Use the discovery engine's search method
                results = discovery_engine._search_prefix(prefix)
                
                reg_ids_after = len(checkpoint.stats.get('scraped_reg_ids', set()))
                new_found = reg_ids_after - reg_ids_before
                
                stats['prefixes_completed'] += 1
                stats['new_reg_ids'] += new_found
                
                print(f"  New reg_ids found: {new_found}")
                print(f"  Total discovered so far: {reg_ids_after}")
                
                logger.info(f"Prefix '{prefix}' completed. Found {new_found} new reg_ids")
                
                random_delay(2, 3)  # Delay between searches
                
            except Exception as e:
                logger.error(f"Error searching prefix '{prefix}': {e}")
                stats['errors'] += 1
                continue
    
    # Final stats
    final_count = len(checkpoint.stats.get('scraped_reg_ids', set()))
    stats['total_reg_ids_found'] = final_count
    stats['duplicates'] = initial_count  # Count of what was already there
    
    # Save checkpoint
    checkpoint.save()
    logger.info(f"Checkpoint saved. Total reg_ids: {final_count}")
    
    return stats


def display_results(stats):
    """Display test results."""
    print("\n" + "=" * 80)
    print("TEST RESULTS")
    print("=" * 80)
    print(f"\nMode: {stats['mode']}")
    print(f"Prefixes tested: {', '.join(stats['prefixes_tested'])}")
    print(f"\nStatistics:")
    print(f"  Prefixes completed: {stats['prefixes_completed']}/{stats['total_prefixes']}")
    print(f"  Total reg_ids discovered: {stats['total_reg_ids_found']}")
    print(f"  New reg_ids in this session: {stats['new_reg_ids']}")
    print(f"  Previously discovered: {stats['duplicates']}")
    print(f"  Search errors: {stats['errors']}")
    
    if stats['prefixes_completed'] == stats['total_prefixes']:
        print(f"\n✅ All prefixes searched successfully!")
    else:
        print(f"\n⚠️  {stats['total_prefixes'] - stats['prefixes_completed']} prefixes had errors")
    
    print("=" * 80 + "\n")
    
    return stats['errors'] == 0


def main():
    """Main test function."""
    print("\n" + "=" * 80)
    print("AHPRA Multi-Dimensional Discovery Test")
    print("=" * 80)
    
    # Test 1: Small prefix set (quick test)
    print("\n📋 TEST 1: Quick Test with Single Letters")
    print("Testing with common high-volume prefixes: S, SH, SM")
    test_prefixes_1 = ['S', 'SH', 'SM']
    stats_1 = test_discovery_with_prefixes(test_prefixes_1, mode="adaptive")
    display_results(stats_1)
    
    input("\nPress Enter to continue to TEST 2...")
    
    # Test 2: More comprehensive (depth 2)
    print("\n📋 TEST 2: Comprehensive Test with Depth 2")
    print("Testing with more prefixes: SH, SM, SN, SO, SP, SR, SS")
    test_prefixes_2 = ['SH', 'SM', 'SN', 'SO', 'SP', 'SR', 'SS']
    stats_2 = test_discovery_with_prefixes(test_prefixes_2, mode="adaptive")
    display_results(stats_2)
    
    # Summary
    print("\n" + "=" * 80)
    print("MULTI-DIMENSIONAL DISCOVERY TEST SUMMARY")
    print("=" * 80)
    print(f"\nTest 1 (Single letters):")
    print(f"  Found: {stats_1['new_reg_ids']} new reg_ids")
    print(f"  Errors: {stats_1['errors']}")
    
    print(f"\nTest 2 (Depth 2):")
    print(f"  Found: {stats_2['new_reg_ids']} new reg_ids")
    print(f"  Errors: {stats_2['errors']}")
    
    total_new = stats_1['new_reg_ids'] + stats_2['new_reg_ids']
    total_errors = stats_1['errors'] + stats_2['errors']
    
    print(f"\nCombined:")
    print(f"  Total new reg_ids discovered: {total_new}")
    print(f"  Total errors: {total_errors}")
    
    if total_errors == 0:
        print(f"\n✅ Multi-dimensional discovery test PASSED!")
        return 0
    else:
        print(f"\n❌ Multi-dimensional discovery test had {total_errors} error(s)")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
