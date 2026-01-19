#!/usr/bin/env python3
"""
Merge test discovered IDs into the main discovered_ids.json file.

This script finds all test_*_ids_*.json files in the discovery directory
and merges their IDs into the main discovered_ids.json file.

Usage:
    python merge_test_ids.py           # Preview what will be merged
    python merge_test_ids.py --apply   # Actually merge the files
    python merge_test_ids.py --delete  # Merge and delete test files after
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from config.settings import DISCOVERY_DIR, DISCOVERED_IDS_FILE


def find_test_files() -> list[Path]:
    """Find all test discovered IDs files."""
    patterns = [
        "test_*_ids_*.json",
        "test_discovered_ids_*.json",
        "test_optimized_ids_*.json",
    ]

    test_files = []
    for pattern in patterns:
        test_files.extend(DISCOVERY_DIR.glob(pattern))

    # Remove duplicates and sort
    test_files = sorted(set(test_files))
    return test_files


def load_ids_from_file(file_path: Path) -> set[str]:
    """Load reg_ids from a JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return set(data.get('reg_ids', []))
    except Exception as e:
        print(f"  ERROR loading {file_path.name}: {e}")
        return set()


def load_main_ids() -> tuple[set[str], dict]:
    """Load IDs from main discovered_ids.json file."""
    if not DISCOVERED_IDS_FILE.exists():
        return set(), {
            'started_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'total_count': 0,
            'reg_ids': []
        }

    try:
        with open(DISCOVERED_IDS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return set(data.get('reg_ids', [])), data
    except Exception as e:
        print(f"ERROR loading main file: {e}")
        return set(), {}


def save_main_ids(ids: set[str], metadata: dict) -> bool:
    """Save IDs to main discovered_ids.json file."""
    metadata['last_updated'] = datetime.now().isoformat()
    metadata['total_count'] = len(ids)
    metadata['reg_ids'] = sorted(list(ids))

    # Atomic write
    temp_file = DISCOVERED_IDS_FILE.with_suffix('.tmp')
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        temp_file.replace(DISCOVERED_IDS_FILE)
        return True
    except Exception as e:
        print(f"ERROR saving main file: {e}")
        if temp_file.exists():
            temp_file.unlink()
        return False


def main():
    parser = argparse.ArgumentParser(description="Merge test IDs into main discovered_ids.json")
    parser.add_argument('--apply', action='store_true', help='Actually perform the merge')
    parser.add_argument('--delete', action='store_true', help='Delete test files after merge')
    args = parser.parse_args()

    print("=" * 60)
    print("MERGE TEST IDs INTO MAIN FILE")
    print("=" * 60)

    # Find test files
    test_files = find_test_files()

    if not test_files:
        print("\nNo test files found to merge.")
        print(f"Looking in: {DISCOVERY_DIR}")
        return

    print(f"\nFound {len(test_files)} test file(s):")
    for f in test_files:
        print(f"  - {f.name}")

    # Load main file
    main_ids, main_metadata = load_main_ids()
    print(f"\nMain file: {DISCOVERED_IDS_FILE.name}")
    print(f"  Current IDs: {len(main_ids):,}")

    # Collect all test IDs
    all_test_ids = set()
    for test_file in test_files:
        test_ids = load_ids_from_file(test_file)
        print(f"\n  {test_file.name}:")
        print(f"    Total IDs: {len(test_ids):,}")

        new_ids = test_ids - main_ids - all_test_ids
        print(f"    New (unique): {len(new_ids):,}")

        all_test_ids.update(test_ids)

    # Calculate what would be added
    new_ids = all_test_ids - main_ids

    print("\n" + "=" * 60)
    print("MERGE SUMMARY")
    print("=" * 60)
    print(f"Main file current:  {len(main_ids):,} IDs")
    print(f"From test files:    {len(all_test_ids):,} IDs")
    print(f"New (to be added):  {len(new_ids):,} IDs")
    print(f"After merge:        {len(main_ids) + len(new_ids):,} IDs")

    if not args.apply:
        print("\n[DRY RUN] No changes made.")
        print("Run with --apply to merge, or --apply --delete to merge and remove test files.")
        return

    # Perform merge
    print("\nMerging...")
    merged_ids = main_ids | all_test_ids

    if save_main_ids(merged_ids, main_metadata):
        print(f"SUCCESS: Merged {len(new_ids):,} new IDs into {DISCOVERED_IDS_FILE.name}")
        print(f"Total IDs now: {len(merged_ids):,}")

        # Delete test files if requested
        if args.delete:
            print("\nDeleting test files...")
            for test_file in test_files:
                try:
                    test_file.unlink()
                    print(f"  Deleted: {test_file.name}")
                except Exception as e:
                    print(f"  ERROR deleting {test_file.name}: {e}")

            # Also delete associated checkpoint files
            from config.settings import CHECKPOINT_DIR
            for test_file in test_files:
                # Extract checkpoint name from test file name
                stem = test_file.stem  # e.g., "test_discovered_ids_A_20260116_215748"
                checkpoint_pattern = stem.replace("_ids_", "_") + "_checkpoint.json"
                checkpoint_files = list(CHECKPOINT_DIR.glob(f"*{stem.split('_')[-2]}_{stem.split('_')[-1]}*"))
                for cp_file in checkpoint_files:
                    try:
                        cp_file.unlink()
                        print(f"  Deleted checkpoint: {cp_file.name}")
                    except Exception:
                        pass
    else:
        print("FAILED: Could not save merged file.")


if __name__ == "__main__":
    main()
