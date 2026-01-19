"""
Search strategies for AHPRA practitioner discovery.

Implements:
1. Recursive Prefix Search - Systematically searches A-Z, drilling deeper when needed
2. Comprehensive Prefix Search - Searches all depths (A-Z, AA-ZZ, AAA-ZZZ) systematically
3. Filter Combination Search - Uses profession + state combinations for validation
"""

from typing import Generator, List, Tuple, Optional
from loguru import logger

from config.professions import ALPHABET, PROFESSIONS, STATES, HIGH_VOLUME_PREFIXES, MAJOR_SUBURBS
from config.settings import MAX_RESULTS_PER_PAGE, MAX_PREFIX_DEPTH


class PrefixGenerator:
    """
    Generates search prefixes for prefix search algorithms.

    Supports generating prefixes at multiple depths:
    - Depth 1: A, B, C, ..., Z (26 prefixes)
    - Depth 2: AA, AB, ..., ZZ (676 prefixes)
    - Depth 3: AAA, AAB, ..., ZZZ (17,576 prefixes)
    """

    def __init__(self, max_depth: int = None):
        """
        Initialize prefix generator.

        Args:
            max_depth: Maximum prefix depth (default from settings)
        """
        self.max_depth = max_depth or MAX_PREFIX_DEPTH
        self.alphabet = ALPHABET

    def generate_all_prefixes(self, up_to_depth: int = None) -> Generator[str, None, None]:
        """
        Generate ALL prefixes from depth 1 up to specified depth.

        Args:
            up_to_depth: Maximum depth to generate (default: self.max_depth)

        Yields:
            Prefix strings in order: A-Z, then AA-ZZ, then AAA-ZZZ, etc.
        """
        max_d = up_to_depth or self.max_depth
        for depth in range(1, max_d + 1):
            yield from self._generate_at_depth(depth)

    def generate_prefixes_at_depth(self, depth: int) -> Generator[str, None, None]:
        """
        Generate all prefixes at a specific depth only.

        Args:
            depth: The depth level (1=A-Z, 2=AA-ZZ, 3=AAA-ZZZ)

        Yields:
            Prefix strings at that depth
        """
        yield from self._generate_at_depth(depth)

    def _generate_at_depth(self, depth: int, current: str = "") -> Generator[str, None, None]:
        """
        Generate all prefixes at a specific depth.

        Args:
            depth: Target depth
            current: Current prefix being built

        Yields:
            Prefix strings
        """
        if len(current) == depth:
            yield current
            return

        for char in self.alphabet:
            yield from self._generate_at_depth(depth, current + char)

    def get_children(self, prefix: str) -> List[str]:
        """
        Get child prefixes for a given prefix.

        Args:
            prefix: Parent prefix

        Returns:
            List of child prefixes (e.g., 'A' -> ['AA', 'AB', ..., 'AZ'])
        """
        if len(prefix) >= self.max_depth:
            return []
        return [prefix + char for char in self.alphabet]

    def should_recurse(self, prefix: str, result_count: int) -> bool:
        """
        Determine if we should recurse deeper for a prefix (adaptive mode).

        Args:
            prefix: Current prefix
            result_count: Number of results found

        Returns:
            True if should recurse deeper
        """
        # Don't recurse if at max depth
        if len(prefix) >= self.max_depth:
            return False

        # Recurse if results exceed page limit
        if result_count >= MAX_RESULTS_PER_PAGE:
            return True

        # Always recurse for known high-volume prefixes
        if prefix in HIGH_VOLUME_PREFIXES:
            return True

        return False

    def count_prefixes_at_depth(self, depth: int) -> int:
        """
        Calculate number of prefixes at a given depth.

        Args:
            depth: The depth level

        Returns:
            Number of prefixes (26^depth)
        """
        return len(self.alphabet) ** depth

    def get_total_prefixes(self, up_to_depth: int = None) -> int:
        """
        Get total number of prefixes up to a given depth.

        Args:
            up_to_depth: Maximum depth

        Returns:
            Total prefix count
        """
        max_d = up_to_depth or self.max_depth
        total = 0
        for d in range(1, max_d + 1):
            total += self.count_prefixes_at_depth(d)
        return total


class RecursivePrefixSearch:
    """
    Implements adaptive recursive prefix search strategy.

    This strategy:
    1. Starts with single letters (A-Z)
    2. If results exceed threshold, recurses deeper (AA, AB, ...)
    3. Continues until all results are captured

    Best for: Quick searches when most prefixes have few results
    """

    def __init__(self, max_depth: int = None, max_results_threshold: int = None):
        """
        Initialize recursive prefix search.

        Args:
            max_depth: Maximum prefix depth
            max_results_threshold: Results count triggering recursion
        """
        self.prefix_gen = PrefixGenerator(max_depth)
        self.max_results = max_results_threshold or MAX_RESULTS_PER_PAGE

    def get_search_plan(self, completed_prefixes: set = None) -> List[str]:
        """
        Get the initial search plan (single letters not yet completed).

        Args:
            completed_prefixes: Set of already completed prefixes

        Returns:
            List of prefixes to search
        """
        completed = completed_prefixes or set()

        # Start with single letters
        plan = []
        for char in ALPHABET:
            if char not in completed:
                plan.append(char)

        logger.info(f"Search plan: {len(plan)} top-level prefixes remaining")
        return plan

    def expand_prefix(self, prefix: str, result_count: int, completed_prefixes: set = None) -> List[str]:
        """
        Expand a prefix into child prefixes if needed.

        Args:
            prefix: Current prefix that needs expansion
            result_count: Number of results found for this prefix
            completed_prefixes: Set of already completed prefixes

        Returns:
            List of child prefixes to search, or empty if no expansion needed
        """
        completed = completed_prefixes or set()

        if not self.prefix_gen.should_recurse(prefix, result_count):
            return []

        children = self.prefix_gen.get_children(prefix)
        # Filter out completed prefixes
        remaining = [p for p in children if p not in completed]

        logger.info(f"Expanding '{prefix}' ({result_count} results) -> {len(remaining)} children")
        return remaining


class ComprehensivePrefixSearch:
    """
    Implements comprehensive prefix search strategy.

    This strategy systematically searches ALL prefix combinations
    at each depth level to ensure complete coverage:

    Phase 1: A, B, C, ..., Z (26 searches)
    Phase 2: AA, AB, ..., ZZ (676 searches)
    Phase 3: AAA, AAB, ..., ZZZ (17,576 searches)

    Best for: Complete data extraction where no results should be missed
    """

    def __init__(self, max_depth: int = None):
        """
        Initialize comprehensive prefix search.

        Args:
            max_depth: Maximum depth to search (default: 3 for AAA-ZZZ)
        """
        self.prefix_gen = PrefixGenerator(max_depth or 3)
        self.max_depth = self.prefix_gen.max_depth

    def get_search_plan(self, completed_prefixes: set = None, start_depth: int = 1) -> List[str]:
        """
        Get comprehensive search plan covering all depths.

        Args:
            completed_prefixes: Set of already completed prefixes
            start_depth: Starting depth level (1, 2, or 3)

        Returns:
            List of all prefixes to search, ordered by depth
        """
        completed = completed_prefixes or set()
        plan = []

        for depth in range(start_depth, self.max_depth + 1):
            depth_prefixes = list(self.prefix_gen.generate_prefixes_at_depth(depth))
            remaining = [p for p in depth_prefixes if p not in completed]
            plan.extend(remaining)

            total_at_depth = len(depth_prefixes)
            completed_at_depth = total_at_depth - len(remaining)
            logger.info(
                f"Depth {depth}: {len(remaining)}/{total_at_depth} prefixes remaining "
                f"({completed_at_depth} completed)"
            )

        logger.info(f"Comprehensive search plan: {len(plan)} total prefixes")
        return plan

    def get_prefixes_at_depth(self, depth: int, completed_prefixes: set = None) -> List[str]:
        """
        Get prefixes for a specific depth level only.

        Args:
            depth: Depth level (1=A-Z, 2=AA-ZZ, 3=AAA-ZZZ)
            completed_prefixes: Set of already completed prefixes

        Returns:
            List of prefixes at that depth
        """
        completed = completed_prefixes or set()
        prefixes = list(self.prefix_gen.generate_prefixes_at_depth(depth))
        remaining = [p for p in prefixes if p not in completed]

        logger.info(f"Depth {depth}: {len(remaining)}/{len(prefixes)} prefixes to search")
        return remaining

    def get_progress_by_depth(self, completed_prefixes: set = None) -> dict:
        """
        Get completion progress broken down by depth.

        Args:
            completed_prefixes: Set of completed prefixes

        Returns:
            Dictionary with progress stats per depth
        """
        completed = completed_prefixes or set()
        progress = {}

        for depth in range(1, self.max_depth + 1):
            total = self.prefix_gen.count_prefixes_at_depth(depth)
            done = sum(1 for p in completed if len(p) == depth)
            progress[depth] = {
                'total': total,
                'completed': done,
                'remaining': total - done,
                'percentage': (done / total * 100) if total > 0 else 0
            }

        return progress

    def estimate_total_searches(self) -> dict:
        """
        Estimate total searches needed for comprehensive coverage.

        Returns:
            Dictionary with counts per depth and total
        """
        estimates = {}
        total = 0

        for depth in range(1, self.max_depth + 1):
            count = self.prefix_gen.count_prefixes_at_depth(depth)
            estimates[f'depth_{depth}'] = count
            total += count

        estimates['total'] = total
        return estimates


class FilterCombinationSearch:
    """
    Implements filter combination search strategy.

    Uses profession × state combinations to:
    1. Validate completeness of prefix search
    2. Catch any edge cases missed by name search
    """

    def __init__(self):
        """Initialize filter combination search."""
        self.professions = PROFESSIONS
        self.states = STATES

    def get_all_combinations(self) -> List[Tuple[str, str]]:
        """
        Get all profession × state combinations.

        Returns:
            List of (profession, state) tuples
        """
        combinations = []
        for profession in self.professions:
            for state in self.states:
                combinations.append((profession, state))

        logger.info(f"Total filter combinations: {len(combinations)}")
        return combinations

    def get_combinations_for_profession(self, profession: str) -> List[Tuple[str, str]]:
        """
        Get all state combinations for a specific profession.

        Args:
            profession: Health profession

        Returns:
            List of (profession, state) tuples
        """
        return [(profession, state) for state in self.states]

    def get_combinations_for_state(self, state: str) -> List[Tuple[str, str]]:
        """
        Get all profession combinations for a specific state.

        Args:
            state: Australian state/territory

        Returns:
            List of (profession, state) tuples
        """
        return [(profession, state) for profession in self.professions]


class MultiDimensionalSearch:
    """
    Implements multi-dimensional search strategy.

    Searches through combinations of:
    - Professions (16 AHPRA professions)
    - States (8 Australian states/territories)
    - Suburbs (major suburbs per state, optional)
    - Name prefixes (A-Z)

    This increases discovery coverage by filtering searches to specific
    profession/state/suburb combinations, capturing practitioners that
    might be missed with prefix-only search.
    """

    def __init__(
        self,
        include_suburbs: bool = False,
        max_prefix_depth: int = 1,
        high_volume_states: Optional[List[str]] = None,
        test_prefix: Optional[str] = None
    ):
        """
        Initialize multi-dimensional search.

        Args:
            include_suburbs: Whether to include suburb-level searches
            max_prefix_depth: Maximum prefix depth (1=A-Z, 2=AA-ZZ)
            high_volume_states: States to include suburb searches for
                               (default: NSW, VIC, QLD)
            test_prefix: Optional single prefix for testing (e.g., 'A')
        """
        self.professions = PROFESSIONS
        self.states = STATES
        self.suburbs = MAJOR_SUBURBS
        self.include_suburbs = include_suburbs
        self.max_prefix_depth = max_prefix_depth
        self.test_prefix = test_prefix
        self.high_volume_states = high_volume_states or [
            "New South Wales",
            "Victoria",
            "Queensland"
        ]
        self.prefix_gen = PrefixGenerator(max_prefix_depth)

    def get_all_combinations(
        self,
        completed_combinations: set = None
    ) -> List[Tuple[str, str, Optional[str], str]]:
        """
        Get all search combinations (profession, state, suburb, prefix).

        Args:
            completed_combinations: Set of already completed combination keys

        Returns:
            List of (profession, state, suburb, prefix) tuples
        """
        completed = completed_combinations or set()
        combinations = []

        # Use test_prefix if provided, otherwise generate all prefixes
        if self.test_prefix:
            prefixes = [self.test_prefix]
            logger.info(f"TEST MODE: Using single prefix '{self.test_prefix}'")
        else:
            prefixes = list(self.prefix_gen.generate_prefixes_at_depth(1))

        for profession in self.professions:
            for state in self.states:
                # Generate prefix combinations for this profession/state
                for prefix in prefixes:
                    combo_key = f"{profession}|{state}|{prefix}"
                    if combo_key not in completed:
                        combinations.append((profession, state, None, prefix))

                # If including suburbs for high-volume states
                if self.include_suburbs and state in self.high_volume_states:
                    suburbs_for_state = self.suburbs.get(state, [])
                    for suburb in suburbs_for_state:
                        for prefix in prefixes:
                            combo_key = f"{profession}|{state}|{suburb}|{prefix}"
                            if combo_key not in completed:
                                combinations.append((profession, state, suburb, prefix))

        total_count = len(combinations)
        logger.info(f"Multi-dimensional search plan: {total_count:,} combinations")
        return combinations

    def get_combinations_for_profession(
        self,
        profession: str,
        completed_combinations: set = None
    ) -> List[Tuple[str, str, Optional[str], str]]:
        """
        Get all combinations for a specific profession.

        Args:
            profession: The profession to search
            completed_combinations: Set of already completed combination keys

        Returns:
            List of (profession, state, suburb, prefix) tuples
        """
        completed = completed_combinations or set()
        combinations = []

        # Use test_prefix if provided, otherwise generate all prefixes
        if self.test_prefix:
            prefixes = [self.test_prefix]
        else:
            prefixes = list(self.prefix_gen.generate_prefixes_at_depth(1))

        for state in self.states:
            for prefix in prefixes:
                combo_key = f"{profession}|{state}|{prefix}"
                if combo_key not in completed:
                    combinations.append((profession, state, None, prefix))

            if self.include_suburbs and state in self.high_volume_states:
                suburbs_for_state = self.suburbs.get(state, [])
                for suburb in suburbs_for_state:
                    for prefix in prefixes:
                        combo_key = f"{profession}|{state}|{suburb}|{prefix}"
                        if combo_key not in completed:
                            combinations.append((profession, state, suburb, prefix))

        return combinations

    def get_combinations_for_state(
        self,
        state: str,
        completed_combinations: set = None
    ) -> List[Tuple[str, str, Optional[str], str]]:
        """
        Get all combinations for a specific state.

        Args:
            state: The state to search
            completed_combinations: Set of already completed combination keys

        Returns:
            List of (profession, state, suburb, prefix) tuples
        """
        completed = completed_combinations or set()
        combinations = []

        # Use test_prefix if provided, otherwise generate all prefixes
        if self.test_prefix:
            prefixes = [self.test_prefix]
        else:
            prefixes = list(self.prefix_gen.generate_prefixes_at_depth(1))

        for profession in self.professions:
            for prefix in prefixes:
                combo_key = f"{profession}|{state}|{prefix}"
                if combo_key not in completed:
                    combinations.append((profession, state, None, prefix))

            if self.include_suburbs and state in self.high_volume_states:
                suburbs_for_state = self.suburbs.get(state, [])
                for suburb in suburbs_for_state:
                    for prefix in prefixes:
                        combo_key = f"{profession}|{state}|{suburb}|{prefix}"
                        if combo_key not in completed:
                            combinations.append((profession, state, suburb, prefix))

        return combinations

    def estimate_total_combinations(self) -> dict:
        """
        Estimate total search combinations.

        Returns:
            Dictionary with counts breakdown
        """
        num_professions = len(self.professions)
        num_states = len(self.states)

        # Account for test_prefix mode (single prefix vs A-Z)
        if self.test_prefix:
            num_prefixes = 1
        else:
            num_prefixes = 26  # A-Z at depth 1

        # Base combinations: profession × state × prefix
        base_count = num_professions * num_states * num_prefixes

        # Suburb combinations for high-volume states
        suburb_count = 0
        if self.include_suburbs:
            for state in self.high_volume_states:
                num_suburbs = len(self.suburbs.get(state, []))
                suburb_count += num_professions * num_suburbs * num_prefixes

        return {
            'professions': num_professions,
            'states': num_states,
            'prefixes': num_prefixes,
            'test_prefix': self.test_prefix,
            'base_combinations': base_count,
            'suburb_combinations': suburb_count,
            'total': base_count + suburb_count,
        }

    def get_progress_summary(self, completed_combinations: set = None) -> dict:
        """
        Get progress summary for multi-dimensional search.

        Args:
            completed_combinations: Set of completed combination keys

        Returns:
            Progress summary dictionary
        """
        completed = completed_combinations or set()
        estimates = self.estimate_total_combinations()
        total = estimates['total']
        done = len(completed)

        return {
            'total_combinations': total,
            'completed': done,
            'remaining': total - done,
            'percentage': (done / total * 100) if total > 0 else 0,
            'by_profession': self._get_progress_by_profession(completed),
        }

    def _get_progress_by_profession(self, completed: set) -> dict:
        """Get progress breakdown by profession."""
        progress = {}
        for profession in self.professions:
            # Count combinations that start with this profession
            done = sum(1 for c in completed if c.startswith(f"{profession}|"))
            progress[profession] = done
        return progress


class SearchOrchestrator:
    """
    Orchestrates different search strategies.

    Supports three modes:
    - Adaptive: Only recurses deeper when results exceed threshold
    - Comprehensive: Searches ALL depths systematically (A-Z, AA-ZZ, AAA-ZZZ)
    - Multi-dimensional: Searches by profession × state × suburb × prefix
    """

    def __init__(
        self,
        comprehensive: bool = False,
        multi_dimensional: bool = False,
        include_suburbs: bool = False,
        max_depth: int = 3,
        test_prefix: Optional[str] = None
    ):
        """
        Initialize search orchestrator.

        Args:
            comprehensive: Use comprehensive mode (all depths) vs adaptive mode
            multi_dimensional: Use multi-dimensional mode (profession × state × prefix)
            include_suburbs: Include suburb-level searches (multi-dimensional only)
            max_depth: Maximum search depth (1-4)
            test_prefix: Optional single prefix for testing (e.g., 'A')
        """
        self.comprehensive = comprehensive
        self.multi_dimensional = multi_dimensional
        self.include_suburbs = include_suburbs
        self.max_depth = max_depth
        self.test_prefix = test_prefix

        if multi_dimensional:
            self.multi_search = MultiDimensionalSearch(
                include_suburbs=include_suburbs,
                max_prefix_depth=1,  # A-Z only for multi-dimensional
                test_prefix=test_prefix
            )
            logger.info("Using MULTI-DIMENSIONAL search mode (profession × state × prefix)")
            estimates = self.multi_search.estimate_total_combinations()
            logger.info(f"Total combinations planned: {estimates['total']:,}")
            if include_suburbs:
                logger.info(f"  - Base combinations: {estimates['base_combinations']:,}")
                logger.info(f"  - Suburb combinations: {estimates['suburb_combinations']:,}")
            self.prefix_search = None
        elif comprehensive:
            self.prefix_search = ComprehensivePrefixSearch(max_depth)
            self.multi_search = None
            logger.info(f"Using COMPREHENSIVE search mode (depth 1-{max_depth})")
            estimates = self.prefix_search.estimate_total_searches()
            logger.info(f"Total searches planned: {estimates['total']:,}")
        else:
            self.prefix_search = RecursivePrefixSearch(max_depth)
            self.multi_search = None
            logger.info("Using ADAPTIVE search mode (expands on demand)")

        self.filter_search = FilterCombinationSearch()

    def get_discovery_queue(self, completed_prefixes: set = None) -> List[str]:
        """
        Get the queue of prefixes to search for discovery.

        Args:
            completed_prefixes: Already completed prefixes

        Returns:
            List of prefixes to search
        """
        if self.multi_dimensional:
            # Multi-dimensional mode doesn't use prefix queue
            return []
        return self.prefix_search.get_search_plan(completed_prefixes)

    def get_multi_dimensional_queue(
        self,
        completed_combinations: set = None
    ) -> List[Tuple[str, str, Optional[str], str]]:
        """
        Get the queue of combinations for multi-dimensional discovery.

        Args:
            completed_combinations: Already completed combination keys

        Returns:
            List of (profession, state, suburb, prefix) tuples
        """
        if not self.multi_dimensional:
            return []
        return self.multi_search.get_all_combinations(completed_combinations)

    def handle_search_result(
        self,
        prefix: str,
        result_count: int,
        completed_prefixes: set = None
    ) -> Optional[List[str]]:
        """
        Handle a search result and determine next steps.

        In comprehensive mode: Never expands (all prefixes pre-planned)
        In adaptive mode: Expands when results exceed threshold

        Args:
            prefix: The prefix that was searched
            result_count: Number of results found
            completed_prefixes: Already completed prefixes

        Returns:
            List of new prefixes to add to queue, or None if prefix is complete
        """
        # In comprehensive mode, don't expand - everything is pre-planned
        if self.comprehensive:
            return None

        # In adaptive mode, expand if needed
        children = self.prefix_search.expand_prefix(prefix, result_count, completed_prefixes)

        if children:
            return children
        return None

    def get_progress_by_depth(self, completed_prefixes: set = None) -> dict:
        """
        Get progress breakdown by depth level.

        Args:
            completed_prefixes: Set of completed prefixes

        Returns:
            Progress dictionary by depth
        """
        if self.comprehensive:
            return self.prefix_search.get_progress_by_depth(completed_prefixes)

        # For adaptive mode, calculate from completed prefixes
        completed = completed_prefixes or set()
        progress = {}
        for depth in range(1, self.max_depth + 1):
            total = 26 ** depth
            done = sum(1 for p in completed if len(p) == depth)
            progress[depth] = {
                'total': total,
                'completed': done,
                'remaining': total - done,
                'percentage': (done / total * 100) if total > 0 else 0
            }
        return progress

    def get_validation_combinations(self) -> List[Tuple[str, str]]:
        """
        Get profession × state combinations for validation.

        Returns:
            List of (profession, state) tuples
        """
        return self.filter_search.get_all_combinations()
