# AHPRA Data Scraper - Claude Context File

This file contains context for AI assistants working on this project.

---

## Build & Test Commands

### Installation
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browser (required for discovery)
playwright install chromium
```

### Running the Scraper

```bash
# Discovery Stage (find practitioners)
python main.py discover                    # Adaptive mode (default)
python main.py discover --comprehensive    # Comprehensive (all prefixes A-ZZZ)
python main.py discover -c --depth 2       # Comprehensive, depth 2 only (AA-ZZ)
python main.py discover --no-headless      # Visible browser for debugging

# Extraction Stage (get detailed data)
python main.py extract                     # Extract all pending
python main.py extract --limit 100         # Extract first 100 only

# Status & Management
python main.py status                      # Show progress summary
python main.py test-id <reg_id>            # Test single registration ID
python main.py reset --confirm             # Reset all progress (DESTRUCTIVE)
```

### Testing
```bash
# Run tests (if available)
pytest

# Test single practitioner fetch
python main.py test-id MED0004000408
```

---

## Current Architectural Decisions

### 1. Two-Stage Architecture
- **Stage 1 (Discovery):** Browser-based prefix search to find all practitioner registration IDs only
- **Stage 2 (Extraction):** HTTP POST API requests to fetch detailed profile data
- **Rationale:** Discovery requires JavaScript rendering; extraction uses lightweight HTTP requests with 30-40s delays for respectful scraping

### 2. Prefix Search Strategy
- Uses recursive name prefixes (A, B, ..., AA, AB, ..., AAA, AAB, ...)
- Two modes: Adaptive (expands only when needed) and Comprehensive (all depths)
- **Rationale:** AHPRA limits results per query; prefix search captures all ~900K practitioners

### 3. Rate Limiting Strategy (CRITICAL)
- **30-40 second delays** between each HTTP POST API call (Phase 2 extraction)
- **0.2-0.6 second delays** for UI interactions within page (Phase 1 search)
- **60 second delays** between retry attempts
- **Rationale:** Respect AHPRA server load; avoid IP bans or service disruption

### 4. Checkpoint-Based Resumability
- JSON checkpoint saves progress every 10 items or 5 minutes
- Flat file (`reg_ids.txt`) for discovered registration IDs
- Atomic writes (temp file + rename) prevent corruption
- **Rationale:** Long-running process (days/weeks) needs crash recovery

### 5. Output Format
- CSV files with 16 standardized fields
- Daily-dated output files (`practitioners_YYYY-MM-DD.csv`)
- UTF-8 encoding
- **Rationale:** Easy to process with pandas; compatible with most tools

---

## Delay Configuration Reference

| Delay Type | Setting | Current Value | Purpose |
|------------|---------|---------------|---------|
| Primary scrape delay | `MIN_DELAY` | 30 seconds | Between API calls |
| Primary scrape delay | `MAX_DELAY` | 40 seconds | Between API calls |
| UI interaction delay | `UI_MIN_DELAY` | 0.2 seconds | Form/button interactions |
| UI interaction delay | `UI_MAX_DELAY` | 0.6 seconds | Form/button interactions |
| Retry delay | `RETRY_DELAY` | 60 seconds | After failed request |

### Where Delays Are Applied

**In `src/api_client.py`:**
- `_apply_delay()` (line 67-70): Uses `MIN_DELAY`/`MAX_DELAY` (30-40s) before each HTTP POST request

**In `src/discovery.py`:**
- `random_delay()` - After page navigation, search submission (30-40s for server requests)
- `ui_delay()` - For form filling, dropdown clicks, button presses (0.2-0.6s)
- `random_delay(RETRY_DELAY, ...)` - After errors (60s+)

**In `src/utils.py`:**
- `random_delay()` - Primary delay function using `MIN_DELAY`/`MAX_DELAY` (30-40s)
- `ui_delay()` - UI interaction delay using `UI_MIN_DELAY`/`UI_MAX_DELAY` (0.2-0.6s)

---

## Pending To-Do Items

### High Priority
1. **Test with new 30-40s delays** - Verify scraper still works correctly with longer delays
2. **Monitor checkpoint saves** - Ensure checkpoints save properly during long waits

### Medium Priority
3. **Add progress estimation** - Calculate ETA based on current rate
4. **Implement parallel discovery** - Run multiple browser instances (carefully, respecting rate limits)
5. **Database output option** - Add SQLite/PostgreSQL output alongside CSV

### Low Priority / Future Enhancements
6. **Web dashboard** - Real-time progress monitoring UI
7. **Email notifications** - Alert on completion or errors
8. **Incremental updates** - Detect changed practitioner records
9. **Data validation** - Verify extracted data quality

### Known Issues
- Profile page extraction requires API workaround (implemented)
- Search state persistence issue after first search (resolved - navigate to fresh page)

---

## Coding Style Rules

### Python Style
- **Python 3.10+** required (uses modern syntax, type hints)
- **Type hints** on all public methods
- **Docstrings** on all classes and public functions
- **Line length:** ~100 characters max
- **Imports:** Standard library first, then third-party, then local

### Naming Conventions
- **Classes:** PascalCase (`DiscoveryEngine`, `CheckpointManager`)
- **Functions/methods:** snake_case (`run_discovery`, `_perform_search`)
- **Private methods:** Prefix with underscore (`_apply_delay`)
- **Constants:** UPPER_SNAKE_CASE (`MIN_DELAY`, `MAX_RETRIES`)

### Code Patterns Used
```python
# Context managers for resource cleanup
with BrowserManager(headless=True) as browser:
    engine = DiscoveryEngine(browser, checkpoint)

# Checkpoint-driven architecture
engine.run_discovery(resume=True)

# Atomic file writes
temp_file = checkpoint_file.with_suffix('.tmp')
temp_file.write_text(json.dumps(data))
temp_file.rename(checkpoint_file)

# Retry with backoff
for attempt in range(MAX_RETRIES):
    try:
        result = perform_action()
        break
    except Exception:
        time.sleep(RETRY_DELAY * (attempt + 1))
```

### Error Handling
- Use specific exception types where possible
- Log errors with `logger.error()` including context
- Re-queue failed items rather than crashing
- Save checkpoint before any graceful exit

### Logging (loguru)
```python
from loguru import logger

logger.info("Starting discovery")
logger.warning(f"Retry {attempt + 1}/{MAX_RETRIES}")
logger.error(f"Failed to fetch {reg_id}: {e}")
logger.debug("Detailed debug info")
```

---

## File Structure Quick Reference

```
AHPRA data scrape/
├── main.py                 # CLI entry point (argparse)
├── requirements.txt        # Python dependencies
├── ARCHITECTURE.md         # Detailed architecture docs
├── claude.md               # This file (AI context)
├── .env.example            # Environment variable template
│
├── config/
│   ├── settings.py         # All configuration constants
│   └── professions.py      # AHPRA professions, states data
│
├── src/
│   ├── browser.py          # Playwright browser automation
│   ├── api_client.py       # HTTP client for extraction
│   ├── search.py           # Prefix search algorithms
│   ├── discovery.py        # Stage 1: Find practitioners
│   ├── extractor.py        # Stage 2: Extract details
│   ├── parser.py           # HTML parsing (BeautifulSoup)
│   ├── checkpoint.py       # Progress tracking (JSON)
│   └── utils.py            # Utilities (logging, delays)
│
├── data/
│   ├── discovery/          # reg_ids.txt (discovered IDs)
│   ├── extracted/          # practitioners_YYYY-MM-DD.csv
│   ├── final/              # Merged/cleaned output
│   └── checkpoints/        # ahpra_checkpoint.json
│
└── logs/                   # Rotated daily log files
```

---

## Key CSS Selectors (AHPRA Website)

```python
SELECTORS = {
    # Search form
    'search_input': '#name-reg',
    'search_button': '#predictiveSearchHomeBtn',
    'profession_dropdown': '#health-profession-dropdown',
    'state_dropdown': '#state-dropdown',

    # Results
    'result_row': '.search-results-table-row[data-practitioner-row-id]',
    'results_table': '.search-results-table-body',
    'no_results': '.no-results-message',
}
```

---

## Current Progress (as of last checkpoint)

- **Discovered:** 150 registration IDs
- **Extracted:** 3 practitioners (sample test)
- **Completed prefixes:** A, B, C
- **Target:** ~900,000 practitioners

---

## Important Notes for AI Assistants

1. **ALWAYS respect rate limits** - The 30-40 second delays are intentional and critical
2. **Don't optimize for speed** - This scraper prioritizes server respect over efficiency
3. **Test changes carefully** - AHPRA may block IPs that abuse their service
4. **Preserve checkpoint compatibility** - Any changes to data structures need migration
5. **Run in background** - Use `nohup` or `screen` for long-running sessions
