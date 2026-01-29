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

# Multi-Dimensional Discovery (profession × state × prefix)
python main.py discover --multi-dimensional          # Search all profession/state/prefix combos
python main.py discover -m                           # Short form
python main.py discover -m --include-suburbs         # Include suburb-level searches (NSW/VIC/QLD)

# COMBINED MODE: Multi-Dimensional + Comprehensive Prefixes (Maximum Coverage)
python main.py discover -m -c                        # profession × state × prefixes (A-ZZZ)
python main.py discover -m -c --depth 2              # profession × state × prefixes (A-ZZ)
python main.py discover -m -c --depth 1              # Same as -m alone (A-Z only)

# Extraction Stage (get detailed data) - USE BROWSER METHOD
python phase2_browser_extract.py                    # Extract all pending (browser-based)
python phase2_browser_extract.py --limit 100        # Extract first 100 only
python phase2_browser_extract.py --no-headless      # Visible browser for debugging

# Alternative: HTTP-based (may hit WAF after ~19 requests)
python phase2_extract.py --limit 100                # HTTP POST method

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
- **Stage 2 (Extraction):** Browser-based extraction of detailed profile data
- **Rationale:** Discovery requires JavaScript rendering; extraction also uses browser to bypass Imperva WAF protection

### 2. Extraction Approach (IMPORTANT)
The AHPRA website uses **Imperva/Incapsula WAF** which blocks HTTP POST requests after ~19 calls.

**Solution:** Use Playwright browser with natural user interactions:
1. Press `Escape` to dismiss any overlays
2. `type()` (not `fill()`) to trigger the typeahead search
3. Click search button with `force=True`
4. Use JavaScript to click the `a.practitioner-name-link` (results are in a modal)
5. Extract data from the detail page
6. Navigate back and repeat

**Key files:**
- `phase2_browser_extract.py` - Main browser-based extraction (RECOMMENDED)
- `phase2_extract.py` - HTTP-based extraction (blocked by WAF after ~19 requests)

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
| Browser extraction delay | `MIN_DELAY` | 15 seconds | Between browser extractions |
| Browser extraction delay | `MAX_DELAY` | 25 seconds | Between browser extractions |
| Short cooldown | `SHORT_COOLDOWN_DURATION` | 60 seconds | After 3 failures |
| Long cooldown | `LONG_COOLDOWN_DURATION` | 300 seconds | After 3 consecutive failures |

### Where Delays Are Applied

**In `phase2_browser_extract.py`:**
- Base delay (15-25s) between each extraction = ~3 req/min
- 60s cooldown after 3 total failures (resets WAF short-term window)
- 300s (5-min) cooldown after 3 consecutive failures (resets WAF sliding window)

**In `src/api_client.py`:** (HTTP method - may be blocked by WAF)
- `_apply_delay()`: 15s base + 5s per consecutive failure
- Adaptive backoff: 15s → 20s → 25s → 30s

---

## Pending To-Do Items

### High Priority
1. **Run full extraction** - Execute browser-based extraction on all discovered IDs
2. **Monitor for CAPTCHA** - If CAPTCHA appears, increase delays or add cooldowns

### Medium Priority
3. **Database output option** - Add SQLite/PostgreSQL output alongside CSV
4. **Parallel discovery** - Run multiple browser instances (carefully, respecting rate limits)

### Low Priority / Future Enhancements
5. **Web dashboard** - Real-time progress monitoring UI
6. **Email notifications** - Alert on completion or errors
7. **Incremental updates** - Detect changed practitioner records

### Known Issues (Resolved)
- ~~Imperva WAF blocks HTTP POST after ~19 requests~~ → Use browser-based extraction
- ~~Search results not clickable~~ → Use JavaScript click on `a.practitioner-name-link`
- ~~Modal overlay blocking clicks~~ → Press `Escape` before interactions
- ~~`fill()` doesn't trigger typeahead~~ → Use `type(delay=50)` instead

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
├── main.py                     # CLI entry point (argparse)
├── phase2_browser_extract.py   # Browser-based extraction (RECOMMENDED)
├── phase2_extract.py           # HTTP-based extraction (may hit WAF)
├── requirements.txt            # Python dependencies
├── ARCHITECTURE.md             # Detailed architecture docs
├── CLAUDE.md                   # This file (AI context)
├── .env.example                # Environment variable template
│
├── config/
│   ├── settings.py             # All configuration constants
│   └── professions.py          # AHPRA professions, states data
│
├── src/
│   ├── browser.py              # Playwright browser automation
│   ├── api_client.py           # HTTP client (with WAF bypass headers)
│   ├── search.py               # Prefix search algorithms
│   ├── discovery.py            # Stage 1: Find practitioners
│   ├── extractor.py            # Stage 2: HTTP extraction
│   ├── parser.py               # HTML parsing (BeautifulSoup)
│   ├── checkpoint.py           # Progress tracking (JSON)
│   └── utils.py                # Utilities (logging, delays)
│
├── data/
│   ├── discovery/              # discovered_ids.json (discovered IDs)
│   ├── extracted/              # practitioners_YYYY-MM-DD.csv
│   ├── backup/                 # extracted_backup.jsonl (JSONL backup)
│   └── checkpoints/            # ahpra_checkpoint.json
│
└── logs/                       # Rotated daily log files
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

    # Search Results (appear in a MODAL, not a table!)
    'result_row': 'div[data-practitioner-id]',           # NOT data-practitioner-row-id
    'practitioner_name_link': 'a.practitioner-name-link', # Blue clickable name
    'modal_body': '.modal-body',
    'no_results': '.no-results-message',
}
```

**IMPORTANT:** Search results appear in a modal popup. The name link (`a.practitioner-name-link`)
is not "visible" to Playwright's normal click, so use JavaScript: `document.querySelector('a.practitioner-name-link').click()`

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
