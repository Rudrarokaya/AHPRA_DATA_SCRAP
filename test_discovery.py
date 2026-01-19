#!/usr/bin/env python3
"""
End-to-end test script for multi-dimensional discovery.

The multi-dimensional discovery iterates in this order:
  1. For each PROFESSION (16 total):
     2. For each STATE (8 total):
        3. For each PREFIX (A-Z, 26 total):
           → Search and collect practitioner IDs

This means we complete ALL states for one profession before moving to the next.

Usage:
    # Test with single prefix 'A' (quick test - 128 combinations)
    python test_discovery.py --prefix A

    # Test with all prefixes A-Z for one profession (208 combinations)
    python test_discovery.py --all-prefixes --profession "Medical Practitioner"

    # Test with name 'Angel' across all professions
    python test_discovery.py --prefix Angel

    # Test specific profession + state with all prefixes
    python test_discovery.py --all-prefixes --profession "Nurse" --state "Victoria"

    # Test with prefix and include suburbs
    python test_discovery.py --prefix A --include-suburbs

    # Run in visible browser mode for debugging
    python test_discovery.py --prefix A --no-headless

    # Set maximum combinations to test
    python test_discovery.py --prefix Angel --max-combinations 10
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from config.settings import DATA_DIR, CHECKPOINT_DIR, DISCOVERY_DIR
from config.professions import PROFESSIONS, STATES, MAJOR_SUBURBS, ALPHABET
from src.browser import BrowserManager
from src.checkpoint import CheckpointManager
from src.discovery import DiscoveryEngine
from src.search import MultiDimensionalSearch
from src.utils import setup_logging


class TestDiscovery:
    """
    Test harness for multi-dimensional discovery.

    Allows testing with various parameters to validate discovery functionality
    and measure discovery rates.
    """

    def __init__(
        self,
        prefix: Optional[str] = None,
        all_prefixes: bool = False,
        profession: Optional[str] = None,
        state: Optional[str] = None,
        include_suburbs: bool = False,
        max_combinations: Optional[int] = None,
        headless: bool = True,
        use_fresh_checkpoint: bool = True
    ):
        """
        Initialize test discovery.

        Args:
            prefix: Name prefix to search (e.g., 'A', 'Angel', 'Smith')
            all_prefixes: If True, iterate through all prefixes A-Z
            profession: Optional specific profession to test
            state: Optional specific state to test
            include_suburbs: Include suburb-level searches
            max_combinations: Maximum number of combinations to test
            headless: Run browser in headless mode
            use_fresh_checkpoint: Start fresh (ignore existing checkpoint)
        """
        self.all_prefixes = all_prefixes
        if all_prefixes:
            self.prefixes = list(ALPHABET)  # A-Z
            self.prefix = "A-Z"  # For display
        else:
            self.prefix = prefix.upper() if prefix and len(prefix) == 1 else prefix
            self.prefixes = [self.prefix] if self.prefix else []
        self.profession = profession
        self.state = state
        self.include_suburbs = include_suburbs
        self.max_combinations = max_combinations
        self.headless = headless
        self.use_fresh_checkpoint = use_fresh_checkpoint

        # Test results tracking
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.combinations_tested = 0
        self.total_discovered = 0
        self.results_by_combination: List[dict] = []
        self.test_discovered_ids_file: Optional[Path] = None  # Track isolated test file

    def get_test_combinations(self) -> List[Tuple[str, str, Optional[str], str]]:
        """
        Get combinations to test based on filters.

        Iteration order: Profession → State → Prefix
        This completes all states for one profession before moving to the next.

        Returns:
            List of (profession, state, suburb, prefix) tuples
        """
        combinations = []

        # Determine professions to test
        if self.profession:
            if self.profession not in PROFESSIONS:
                logger.error(f"Invalid profession: {self.profession}")
                logger.info(f"Valid professions: {', '.join(PROFESSIONS)}")
                return []
            professions = [self.profession]
        else:
            professions = PROFESSIONS

        # Determine states to test
        if self.state:
            if self.state not in STATES:
                logger.error(f"Invalid state: {self.state}")
                logger.info(f"Valid states: {', '.join(STATES)}")
                return []
            states = [self.state]
        else:
            states = STATES

        # Build combinations in order: Profession → State → Prefix
        for prof in professions:
            for st in states:
                for prefix in self.prefixes:
                    combinations.append((prof, st, None, prefix))

                    # Add suburb combinations if requested
                    if self.include_suburbs:
                        suburbs = MAJOR_SUBURBS.get(st, [])
                        for suburb in suburbs:
                            combinations.append((prof, st, suburb, prefix))

        # Limit combinations if specified
        if self.max_combinations and len(combinations) > self.max_combinations:
            logger.info(f"Limiting to {self.max_combinations} combinations (out of {len(combinations)})")
            combinations = combinations[:self.max_combinations]

        return combinations

    def print_test_plan(self, combinations: List[Tuple]) -> None:
        """Print the test plan before execution."""
        print("\n" + "=" * 70)
        print("MULTI-DIMENSIONAL DISCOVERY TEST")
        print("=" * 70)

        # Show iteration order
        print("\n🔄 Iteration Order:")
        print("   1. For each PROFESSION →")
        print("      2. For each STATE →")
        print("         3. For each PREFIX → Search & collect IDs")

        print(f"\n📋 Test Parameters:")
        if self.all_prefixes:
            print(f"   Prefixes: A-Z (all 26 letters)")
        else:
            print(f"   Prefix/Name: '{self.prefix}'")
        print(f"   Profession filter: {self.profession or 'All (16 professions)'}")
        print(f"   State filter: {self.state or 'All (8 states)'}")
        print(f"   Include suburbs: {self.include_suburbs}")
        print(f"   Browser mode: {'Headless' if self.headless else 'Visible'}")
        print(f"\n📊 Combinations to test: {len(combinations)}")

        if len(combinations) <= 20:
            print("\n   Combinations:")
            for i, (prof, state, suburb, prefix) in enumerate(combinations, 1):
                suburb_str = f" | {suburb}" if suburb else ""
                print(f"   {i:3}. {prof} | {state}{suburb_str} | '{prefix}'")
        else:
            print(f"\n   First 5 combinations:")
            for i, (prof, state, suburb, prefix) in enumerate(combinations[:5], 1):
                suburb_str = f" | {suburb}" if suburb else ""
                print(f"   {i:3}. {prof} | {state}{suburb_str} | '{prefix}'")
            print(f"   ... and {len(combinations) - 5} more")

        # Estimate time
        avg_time_per_combo = 60  # ~60 seconds per combination (including delays)
        estimated_minutes = (len(combinations) * avg_time_per_combo) / 60
        estimated_hours = estimated_minutes / 60

        print(f"\n⏱️  Estimated time: ", end="")
        if estimated_hours >= 1:
            print(f"{estimated_hours:.1f} hours ({estimated_minutes:.0f} minutes)")
        else:
            print(f"{estimated_minutes:.0f} minutes")

        print("=" * 70 + "\n")

    def run_test(self) -> dict:
        """
        Run the discovery test.

        Returns:
            Test results dictionary
        """
        setup_logging("test_discovery")

        # Get test combinations
        combinations = self.get_test_combinations()
        if not combinations:
            return {'error': 'No valid combinations to test'}

        self.print_test_plan(combinations)

        # Confirm before running
        if len(combinations) > 10:
            response = input(f"This will test {len(combinations)} combinations. Continue? [y/N]: ")
            if response.lower() != 'y':
                print("Test cancelled.")
                return {'cancelled': True}

        self.start_time = datetime.now()

        # Create test checkpoint with ISOLATED discovered_ids file
        test_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        test_checkpoint_name = f"test_{self.prefix}_{test_timestamp}"

        # Create isolated discovered_ids file for this test run
        self.test_discovered_ids_file = DISCOVERY_DIR / f"test_discovered_ids_{self.prefix}_{test_timestamp}.json"
        checkpoint = CheckpointManager(test_checkpoint_name, discovered_ids_file=self.test_discovered_ids_file)

        if self.use_fresh_checkpoint:
            # Ensure we start fresh
            checkpoint_file = CHECKPOINT_DIR / f"{test_checkpoint_name}_checkpoint.json"
            if checkpoint_file.exists():
                checkpoint_file.unlink()
            # Also remove the isolated discovered_ids file if exists
            if self.test_discovered_ids_file.exists():
                self.test_discovered_ids_file.unlink()

        print(f"📁 Test discovered IDs will be saved to: {self.test_discovered_ids_file.name}")

        try:
            with BrowserManager(headless=self.headless) as browser:
                # Create discovery engine with test prefix
                # use_optimized=False for manual testing to see each combination
                # Set to True for faster real discovery
                engine = DiscoveryEngine(
                    browser,
                    checkpoint,
                    multi_dimensional=True,
                    include_suburbs=self.include_suburbs,
                    test_prefix=self.prefix,
                    use_optimized=False  # Manual test mode - we track each combination ourselves
                )

                if not engine.initialize():
                    return {'error': 'Failed to initialize discovery engine'}

                print("\n🚀 Starting discovery test...\n")

                # Run discovery for each combination manually to track results
                total_discovered = 0

                for i, (profession, state, suburb, prefix) in enumerate(combinations, 1):
                    combo_str = f"{profession} | {state}"
                    if suburb:
                        combo_str += f" | {suburb}"
                    combo_str += f" | '{prefix}'"

                    print(f"[{i}/{len(combinations)}] Testing: {combo_str}")

                    try:
                        # Get unique count before search
                        unique_before = len(checkpoint.scraped_reg_ids)

                        # Perform search for this combination
                        count = engine._search_combination(prefix, profession, state, suburb)

                        # Get unique count after search (true new discoveries)
                        unique_after = len(checkpoint.scraped_reg_ids)
                        new_unique = unique_after - unique_before

                        self.results_by_combination.append({
                            'profession': profession,
                            'state': state,
                            'suburb': suburb,
                            'prefix': prefix,
                            'count': count,  # Raw count from search
                            'new_unique': new_unique,  # Truly new unique IDs
                            'success': True
                        })

                        total_discovered = unique_after  # Use checkpoint's unique count
                        self.combinations_tested += 1

                        print(f"         → Found: {count} (New unique: {new_unique}, Total unique: {total_discovered})")

                        # Save checkpoint
                        combo_key = checkpoint.make_combination_key(profession, state, prefix, suburb)
                        checkpoint.mark_combination_completed(combo_key)
                        checkpoint.save()

                    except KeyboardInterrupt:
                        print("\n\n⚠️  Test interrupted by user")
                        break
                    except Exception as e:
                        logger.error(f"Error testing combination: {e}")
                        self.results_by_combination.append({
                            'profession': profession,
                            'state': state,
                            'suburb': suburb,
                            'prefix': prefix,
                            'count': 0,
                            'success': False,
                            'error': str(e)
                        })

                self.total_discovered = total_discovered

        except Exception as e:
            logger.error(f"Test failed: {e}")
            return {'error': str(e)}

        self.end_time = datetime.now()

        # Generate and print results
        return self.generate_results()

    def generate_results(self) -> dict:
        """Generate test results summary."""
        duration = (self.end_time - self.start_time).total_seconds()

        results = {
            'prefix': self.prefix,
            'profession_filter': self.profession,
            'state_filter': self.state,
            'include_suburbs': self.include_suburbs,
            'combinations_tested': self.combinations_tested,
            'total_discovered': self.total_discovered,
            'duration_seconds': duration,
            'duration_formatted': self._format_duration(duration),
            'avg_per_combination': self.total_discovered / max(1, self.combinations_tested),
            'rate_per_minute': (self.total_discovered / duration) * 60 if duration > 0 else 0,
            'results_by_combination': self.results_by_combination,
            'top_combinations': self._get_top_combinations(10),
            'by_profession': self._aggregate_by_profession(),
            'by_state': self._aggregate_by_state(),
        }

        self._print_results(results)

        return results

    def _format_duration(self, seconds: float) -> str:
        """Format duration as human-readable string."""
        if seconds < 60:
            return f"{seconds:.0f} seconds"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f} minutes"
        else:
            hours = seconds / 3600
            return f"{hours:.1f} hours"

    def _get_top_combinations(self, n: int) -> List[dict]:
        """Get top N combinations by discovery count."""
        sorted_results = sorted(
            [r for r in self.results_by_combination if r['success']],
            key=lambda x: x['count'],
            reverse=True
        )
        return sorted_results[:n]

    def _aggregate_by_profession(self) -> dict:
        """Aggregate results by profession."""
        by_prof = {}
        for r in self.results_by_combination:
            if r['success']:
                prof = r['profession']
                if prof not in by_prof:
                    by_prof[prof] = {'count': 0, 'combinations': 0}
                by_prof[prof]['count'] += r['count']
                by_prof[prof]['combinations'] += 1
        return dict(sorted(by_prof.items(), key=lambda x: x[1]['count'], reverse=True))

    def _aggregate_by_state(self) -> dict:
        """Aggregate results by state."""
        by_state = {}
        for r in self.results_by_combination:
            if r['success']:
                state = r['state']
                if state not in by_state:
                    by_state[state] = {'count': 0, 'combinations': 0}
                by_state[state]['count'] += r['count']
                by_state[state]['combinations'] += 1
        return dict(sorted(by_state.items(), key=lambda x: x[1]['count'], reverse=True))

    def _print_results(self, results: dict) -> None:
        """Print formatted test results."""
        print("\n" + "=" * 70)
        print("TEST RESULTS")
        print("=" * 70)

        print(f"\n📊 Summary:")
        print(f"   Prefix/Name tested: '{results['prefix']}'")
        print(f"   Combinations tested: {results['combinations_tested']}")
        print(f"   Total practitioners discovered: {results['total_discovered']:,}")
        print(f"   Duration: {results['duration_formatted']}")
        print(f"   Average per combination: {results['avg_per_combination']:.1f}")
        print(f"   Discovery rate: {results['rate_per_minute']:.1f} practitioners/minute")

        # Top combinations
        if results['top_combinations']:
            print(f"\n🏆 Top {len(results['top_combinations'])} Combinations:")
            for i, combo in enumerate(results['top_combinations'], 1):
                suburb_str = f" | {combo['suburb']}" if combo['suburb'] else ""
                print(f"   {i}. {combo['profession']} | {combo['state']}{suburb_str}: {combo['count']:,}")

        # By profession
        if results['by_profession']:
            print(f"\n📋 By Profession:")
            for prof, data in list(results['by_profession'].items())[:5]:
                print(f"   {prof}: {data['count']:,} ({data['combinations']} combinations)")
            if len(results['by_profession']) > 5:
                print(f"   ... and {len(results['by_profession']) - 5} more professions")

        # By state
        if results['by_state']:
            print(f"\n🗺️  By State:")
            for state, data in results['by_state'].items():
                print(f"   {state}: {data['count']:,} ({data['combinations']} combinations)")

        print("\n" + "=" * 70)

        # Save results to file
        results_file = DATA_DIR / f"test_results_{self.prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(results_file, 'w') as f:
            f.write(f"Test Results for prefix '{self.prefix}'\n")
            f.write(f"Run at: {datetime.now().isoformat()}\n")
            f.write(f"Duration: {results['duration_formatted']}\n")
            f.write(f"Combinations tested: {results['combinations_tested']}\n")
            f.write(f"Total discovered: {results['total_discovered']}\n")
            f.write(f"\nDetailed results:\n")
            for r in self.results_by_combination:
                suburb_str = f" | {r['suburb']}" if r['suburb'] else ""
                status = "✓" if r['success'] else "✗"
                f.write(f"{status} {r['profession']} | {r['state']}{suburb_str}: {r['count']}\n")

        print(f"\n📁 Results saved to: {results_file}")
        if self.test_discovered_ids_file and self.test_discovered_ids_file.exists():
            print(f"📁 Discovered IDs saved to: {self.test_discovered_ids_file}")


def main():
    """Main entry point for test script."""
    parser = argparse.ArgumentParser(
        description="End-to-end test for multi-dimensional discovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_discovery.py --prefix A
  python test_discovery.py --prefix Angel
  python test_discovery.py --prefix Angel --profession "Medical Practitioner"
  python test_discovery.py --prefix Angel --state "New South Wales"
  python test_discovery.py --prefix A --max-combinations 10
  python test_discovery.py --prefix Angel --no-headless
        """
    )

    parser.add_argument(
        "--prefix", "-p", type=str, default=None,
        help="Name prefix to search (e.g., 'A', 'Angel', 'Smith')"
    )
    parser.add_argument(
        "--all-prefixes", "-a", action="store_true", default=False,
        help="Iterate through all prefixes A-Z (instead of single prefix)"
    )
    parser.add_argument(
        "--profession", type=str, default=None,
        help="Filter to specific profession (e.g., 'Medical Practitioner')"
    )
    parser.add_argument(
        "--state", type=str, default=None,
        help="Filter to specific state (e.g., 'New South Wales')"
    )
    parser.add_argument(
        "--include-suburbs", action="store_true", default=False,
        help="Include suburb-level searches"
    )
    parser.add_argument(
        "--max-combinations", "-m", type=int, default=None,
        help="Maximum number of combinations to test"
    )
    parser.add_argument(
        "--no-headless", action="store_true", default=False,
        help="Run browser in visible mode (for debugging)"
    )
    parser.add_argument(
        "--list-professions", action="store_true",
        help="List all available professions and exit"
    )
    parser.add_argument(
        "--list-states", action="store_true",
        help="List all available states and exit"
    )

    args = parser.parse_args()

    # Handle list options
    if args.list_professions:
        print("\nAvailable professions:")
        for i, prof in enumerate(PROFESSIONS, 1):
            print(f"  {i:2}. {prof}")
        return 0

    if args.list_states:
        print("\nAvailable states:")
        for i, state in enumerate(STATES, 1):
            print(f"  {i}. {state}")
        return 0

    # Check prefix or all_prefixes is provided for actual test
    if not args.prefix and not args.all_prefixes:
        parser.error("Either --prefix or --all-prefixes is required for running tests")

    if args.prefix and args.all_prefixes:
        parser.error("Cannot use both --prefix and --all-prefixes together")

    # Run test
    test = TestDiscovery(
        prefix=args.prefix,
        all_prefixes=args.all_prefixes,
        profession=args.profession,
        state=args.state,
        include_suburbs=args.include_suburbs,
        max_combinations=args.max_combinations,
        headless=not args.no_headless,
    )

    results = test.run_test()

    if 'error' in results:
        print(f"\n❌ Test failed: {results['error']}")
        return 1
    elif results.get('cancelled'):
        return 0
    else:
        print(f"\n✅ Test completed successfully!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
