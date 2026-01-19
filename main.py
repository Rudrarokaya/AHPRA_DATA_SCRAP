#!/usr/bin/env python3
"""
AHPRA Practitioner Data Scraper

Main entry point for the scraper with CLI interface.

Usage:
    python main.py discover                              Adaptive mode (default)
    python main.py discover --comprehensive              Comprehensive (A-Z, AA-ZZ, AAA-ZZZ)
    python main.py discover --multi-dimensional          Multi-dimensional (profession × state × prefix)
    python main.py discover -m --include-suburbs         Multi-dimensional with suburbs
    python main.py discover --no-headless                Visible browser for debugging
    python main.py extract [--limit N]                   Extract practitioners via API
    python main.py status                                Show progress
    python main.py reset [--confirm]                     Reset all data
    python main.py test-id <reg_id>                      Test single extraction
"""

import argparse
import sys
from pathlib import Path

from loguru import logger

from config.settings import DATA_DIR, CHECKPOINT_DIR
from src.utils import setup_logging, format_duration
from src.browser import BrowserManager
from src.checkpoint import CheckpointManager
from src.discovery import DiscoveryEngine
from src.extractor import ExtractionEngine


def cmd_discover(args):
    """Run the discovery stage to find all practitioner URLs."""
    setup_logging("discovery")
    logger.info("=" * 60)
    logger.info("AHPRA Scraper - Discovery Stage")
    logger.info("=" * 60)

    checkpoint = CheckpointManager("ahpra")

    if args.resume:
        checkpoint.load()
        logger.info(f"Resuming from checkpoint: {checkpoint.stats['total_discovered']} already discovered")

    # Search mode settings
    comprehensive = args.comprehensive
    multi_dimensional = args.multi_dimensional
    include_suburbs = args.include_suburbs
    max_depth = args.depth

    test_prefix = args.test_prefix.upper() if args.test_prefix else None

    if multi_dimensional:
        logger.info("Search mode: MULTI-DIMENSIONAL (profession × state × prefix)")
        if test_prefix:
            # Test mode with single prefix
            base = 16 * 8 * 1  # 16 professions × 8 states × 1 prefix
            logger.info(f"  TEST MODE: Single prefix '{test_prefix}' only")
        else:
            # Calculate total combinations
            base = 16 * 8 * 26  # 16 professions × 8 states × 26 letters
        if include_suburbs:
            logger.info("  Including suburb-level searches for NSW, VIC, QLD")
        logger.info(f"  Base combinations: {base:,}")
    elif comprehensive:
        logger.info(f"Search mode: COMPREHENSIVE (all depths up to {max_depth})")
        # Calculate total searches
        total = sum(26 ** d for d in range(1, max_depth + 1))
        logger.info(f"Total prefixes to search: {total:,}")
        logger.info("  Depth 1 (A-Z): 26")
        if max_depth >= 2:
            logger.info("  Depth 2 (AA-ZZ): 676")
        if max_depth >= 3:
            logger.info("  Depth 3 (AAA-ZZZ): 17,576")
    else:
        logger.info("Search mode: ADAPTIVE (expands when results exceed threshold)")

    headless = args.headless
    logger.info(f"Browser mode: {'headless' if headless else 'visible'}")

    with BrowserManager(headless=headless) as browser:
        engine = DiscoveryEngine(
            browser,
            checkpoint,
            comprehensive=comprehensive,
            multi_dimensional=multi_dimensional,
            include_suburbs=include_suburbs,
            max_depth=max_depth,
            test_prefix=test_prefix
        )

        if not engine.initialize():
            logger.error("Failed to initialize discovery engine")
            return 1

        try:
            discovered = engine.run_discovery(resume=args.resume)
            logger.info(f"Discovery complete. New practitioners found: {discovered:,}")
            logger.info(f"Total discovered: {checkpoint.stats['total_discovered']:,}")

            # Show progress summary
            progress = engine.get_progress()
            if progress.get('mode') == 'multi_dimensional':
                logger.info(f"Completed combinations: {progress['completed_combinations']:,}")
            elif 'depth_progress' in progress:
                logger.info("Progress by depth:")
                for depth, stats in progress['depth_progress'].items():
                    logger.info(
                        f"  Depth {depth}: {stats['completed']}/{stats['total']} "
                        f"({stats['percentage']:.1f}%)"
                    )

        except KeyboardInterrupt:
            logger.warning("Discovery interrupted by user")
            checkpoint.save()
            logger.info("Checkpoint saved. Resume with: python main.py discover")
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            checkpoint.save()
            return 1

    return 0


def cmd_extract(args):
    """Run the extraction stage to get detailed practitioner data via API."""
    setup_logging("extraction")
    logger.info("=" * 60)
    logger.info("AHPRA Scraper - Extraction Stage (API-based)")
    logger.info("=" * 60)

    checkpoint = CheckpointManager("ahpra")
    checkpoint.load()

    pending = checkpoint.get_pending_reg_ids()
    if not pending:
        logger.warning("No pending reg_ids to extract. Run discovery first.")
        return 1

    logger.info(f"Pending extractions: {len(pending)}")

    if args.limit:
        logger.info(f"Limited to {args.limit} extractions")

    engine = ExtractionEngine(checkpoint)

    if not engine.initialize():
        logger.error("Failed to initialize extraction engine")
        return 1

    try:
        extracted = engine.run_extraction(resume=args.resume, limit=args.limit)
        logger.info(f"Extraction complete. Total extracted: {extracted}")

        progress = engine.get_progress()
        logger.info(f"Overall progress: {progress['completion_pct']:.1f}% complete")
        logger.info(f"Output file: {engine.output_file}")

    except KeyboardInterrupt:
        logger.warning("Extraction interrupted by user")
        checkpoint.save()
        logger.info("Checkpoint saved. Resume with: python main.py extract")
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        checkpoint.save()
        return 1
    finally:
        engine.close()

    return 0


def cmd_status(args):
    """Show current scraping progress."""
    setup_logging("status")

    checkpoint = CheckpointManager("ahpra")

    if not checkpoint.load():
        print("\nNo checkpoint found. Start with: python main.py discover\n")
        return 0

    summary = checkpoint.get_progress_summary()

    print("\n" + "=" * 50)
    print("AHPRA Scraper - Progress Status")
    print("=" * 50)

    # Discovery metadata
    if summary.get('discovery_started_at'):
        print(f"\n🕐 Discovery started: {summary['discovery_started_at']}")
    if summary.get('discovery_last_updated'):
        print(f"   Last updated: {summary['discovery_last_updated']}")

    print(f"\n📊 Discovery Stage:")
    print(f"   Practitioners found: {summary['total_discovered']:,}")

    # Check if multi-dimensional or prefix-based
    if summary.get('combinations_completed', 0) > 0:
        # Multi-dimensional mode
        print(f"   Combinations completed: {summary['combinations_completed']:,}")
        if summary.get('current_combination'):
            print(f"   Current: {summary['current_combination']}")
    else:
        # Prefix-based mode
        print(f"   Prefixes completed: {summary['prefixes_completed']}")

        # Calculate depth-level progress
        completed_prefixes = checkpoint.completed_prefixes
        depth_stats = {}
        for depth in range(1, 4):
            total = 26 ** depth
            done = sum(1 for p in completed_prefixes if len(p) == depth)
            depth_stats[depth] = {'total': total, 'done': done}

        # Show depth breakdown
        print(f"\n   Progress by depth:")
        for depth, stats in depth_stats.items():
            depth_names = {1: "A-Z", 2: "AA-ZZ", 3: "AAA-ZZZ"}
            pct = (stats['done'] / stats['total'] * 100) if stats['total'] > 0 else 0
            bar_filled = int(pct / 5)  # 20 char bar
            bar = "█" * bar_filled + "░" * (20 - bar_filled)
            print(f"     Depth {depth} ({depth_names[depth]}): [{bar}] {stats['done']}/{stats['total']:,} ({pct:.1f}%)")

        if summary['current_prefix']:
            print(f"\n   Current prefix: '{summary['current_prefix']}' (page {summary['current_page']})")

    print(f"\n📥 Extraction Stage:")
    print(f"   Extracted: {summary['total_extracted']:,}")
    print(f"   Pending: {summary['pending_extraction']:,}")

    if summary['total_discovered'] > 0:
        pct = (summary['total_extracted'] / summary['total_discovered']) * 100
        print(f"   Progress: {pct:.1f}%")

    print(f"\n⚠️  Errors: {summary['errors']}")

    # Show checkpoint file info
    checkpoint_file = CHECKPOINT_DIR / "ahpra_checkpoint.json"
    if checkpoint_file.exists():
        size = checkpoint_file.stat().st_size / 1024
        print(f"\n💾 Checkpoint: {checkpoint_file}")
        print(f"   Size: {size:.1f} KB")
        if checkpoint.stats.get('last_save_time'):
            print(f"   Last saved: {checkpoint.stats['last_save_time']}")

    # Show discovered_ids JSON
    discovery_dir = DATA_DIR / "discovery"
    discovered_json = discovery_dir / "discovered_ids.json"
    if discovered_json.exists():
        size = discovered_json.stat().st_size / 1024 / 1024
        print(f"\n📄 Discovery JSON: {discovered_json.name} ({size:.2f} MB)")

    # Show output files
    print(f"\n📁 Data directory: {DATA_DIR}")
    extracted_dir = DATA_DIR / "extracted"
    if extracted_dir.exists():
        csv_files = list(extracted_dir.glob("*.csv"))
        if csv_files:
            print(f"   CSV output files:")
            for f in csv_files:
                size = f.stat().st_size / 1024
                print(f"     - {f.name} ({size:.1f} KB)")

    # Show backup files
    backup_dir = DATA_DIR / "backup"
    if backup_dir.exists():
        backup_json = backup_dir / "extracted_backup.json"
        if backup_json.exists():
            size = backup_json.stat().st_size / 1024 / 1024
            print(f"\n   JSON backup: extracted_backup.json ({size:.2f} MB)")

    print("\n" + "=" * 50 + "\n")
    return 0


def cmd_reset(args):
    """Reset checkpoint data."""
    setup_logging("reset")

    if not args.confirm:
        print("\n⚠️  This will delete all progress data!")
        print("   Use --confirm to proceed.\n")
        return 1

    checkpoint = CheckpointManager("ahpra")

    # Delete checkpoint file
    checkpoint_file = CHECKPOINT_DIR / "ahpra_checkpoint.json"
    if checkpoint_file.exists():
        checkpoint_file.unlink()
        print(f"✓ Deleted checkpoint: {checkpoint_file}")

    # Delete reg_ids file
    discovery_dir = DATA_DIR / "discovery"
    if discovery_dir.exists():
        reg_ids_file = discovery_dir / "reg_ids.txt"
        if reg_ids_file.exists():
            reg_ids_file.unlink()
            print(f"✓ Deleted reg_ids: {reg_ids_file}")

        # Clean up any old JSON files
        for f in discovery_dir.glob("*.json"):
            f.unlink()
            print(f"✓ Deleted: {f}")

    print("\n✓ Reset complete. Start fresh with: python main.py discover\n")
    return 0


def cmd_test_id(args):
    """Test extraction on a single registration ID."""
    setup_logging("test")
    logger.info(f"Testing reg_id: {args.reg_id}")

    checkpoint = CheckpointManager("ahpra_test")
    engine = ExtractionEngine(checkpoint)

    try:
        data = engine.extract_single(args.reg_id)

        if data:
            print("\n" + "=" * 50)
            print("Extracted Data:")
            print("=" * 50)
            for key, value in data.items():
                if value:
                    print(f"  {key}: {value}")
            print("=" * 50 + "\n")
        else:
            print("\n❌ Failed to extract data for reg_id\n")
            return 1
    finally:
        engine.close()

    return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AHPRA Practitioner Data Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py discover                       Start/resume discovery (adaptive mode)
  python main.py discover --comprehensive       Comprehensive search (A-Z, AA-ZZ, AAA-ZZZ)
  python main.py discover -c --depth 2          Comprehensive up to depth 2 (A-Z, AA-ZZ)
  python main.py discover --multi-dimensional   Search by profession × state × prefix
  python main.py discover -m --include-suburbs  Multi-dimensional with suburb-level searches
  python main.py discover --no-headless         Run with visible browser
  python main.py extract --limit 100            Extract first 100 practitioners (via API)
  python main.py status                         Show progress
  python main.py test-id NMW0001234567          Test extraction for single reg_id
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Discover command
    discover_parser = subparsers.add_parser("discover", help="Run discovery stage")
    discover_parser.add_argument(
        "--no-resume", dest="resume", action="store_false", default=True,
        help="Start fresh instead of resuming"
    )
    discover_parser.add_argument(
        "--comprehensive", "-c", action="store_true", default=False,
        help="Use comprehensive search (all depths A-Z, AA-ZZ, AAA-ZZZ)"
    )
    discover_parser.add_argument(
        "--multi-dimensional", "-m", action="store_true", default=False,
        help="Use multi-dimensional search (profession × state × prefix)"
    )
    discover_parser.add_argument(
        "--include-suburbs", action="store_true", default=False,
        help="Include suburb-level searches (with --multi-dimensional)"
    )
    discover_parser.add_argument(
        "--test-prefix", type=str, default=None,
        help="Test with single prefix only (e.g., --test-prefix A)"
    )
    discover_parser.add_argument(
        "--depth", "-d", type=int, default=3, choices=[1, 2, 3, 4],
        help="Maximum search depth (1=A-Z, 2=AA-ZZ, 3=AAA-ZZZ, default: 3)"
    )
    discover_parser.add_argument(
        "--headless", dest="headless", action="store_true", default=True,
        help="Run browser in headless mode (default)"
    )
    discover_parser.add_argument(
        "--no-headless", dest="headless", action="store_false",
        help="Run browser with visible window"
    )

    # Extract command
    extract_parser = subparsers.add_parser("extract", help="Run extraction stage (API-based)")
    extract_parser.add_argument(
        "--no-resume", dest="resume", action="store_false", default=True,
        help="Start fresh instead of resuming"
    )
    extract_parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of practitioners to extract"
    )

    # Status command
    subparsers.add_parser("status", help="Show current progress")

    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Reset all progress")
    reset_parser.add_argument(
        "--confirm", action="store_true",
        help="Confirm reset operation"
    )

    # Test ID command
    test_parser = subparsers.add_parser("test-id", help="Test extraction on single registration ID")
    test_parser.add_argument("reg_id", help="Registration ID to test (e.g., NMW0001234567)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Dispatch to command handler
    commands = {
        "discover": cmd_discover,
        "extract": cmd_extract,
        "status": cmd_status,
        "reset": cmd_reset,
        "test-id": cmd_test_id,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
