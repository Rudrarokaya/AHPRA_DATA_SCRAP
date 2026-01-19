# AHPRA Practitioner Data Scraper - Architecture Documentation

## Overview

This project is a web scraper designed to extract practitioner data from the Australian Health Practitioner Regulation Agency (AHPRA) public register. It uses a two-stage approach: **Discovery** (finding all practitioners) followed by **Extraction** (collecting detailed information).

**Target URL:** https://www.ahpra.gov.au/Registration/Registers-of-Practitioners.aspx

---

## Project Structure

```
AHPRA data scrape/
├── main.py                 # CLI entry point
├── config/
│   ├── __init__.py
│   ├── settings.py         # Configuration constants
│   └── professions.py      # AHPRA professions, states, divisions data
├── src/
│   ├── __init__.py
│   ├── browser.py          # Playwright browser management
│   ├── search.py           # Search strategy algorithms
│   ├── discovery.py        # Stage 1: Find all practitioners
│   ├── extractor.py        # Stage 2: Extract detailed data
│   ├── parser.py           # HTML parsing for profile pages
│   ├── checkpoint.py       # Resumable progress tracking
│   └── utils.py            # Utility functions
├── data/
│   ├── discovery/          # Discovered practitioner URLs
│   ├── extracted/          # Extracted CSV data
│   ├── final/              # Merged/cleaned final output
│   └── checkpoints/        # Checkpoint JSON files
├── logs/                   # Log files (rotated daily)
└── requirements.txt        # Python dependencies
```

---

## Two-Stage Architecture

### Stage 1: Discovery

**Purpose:** Find all registered practitioners by systematically searching the AHPRA register.

**Challenge:** AHPRA's search interface limits results per query. To capture all ~900,000+ practitioners, we use a **prefix search strategy**.

#### Search Strategies

The scraper supports two search modes:

| Mode | Description | Total Searches |
|------|-------------|----------------|
| **Adaptive** | Starts with A-Z, expands deeper only when results hit threshold | Variable |
| **Comprehensive** | Searches all prefix depths systematically | 18,278 |

**Comprehensive Search Breakdown:**
- Depth 1 (A-Z): 26 searches
- Depth 2 (AA-ZZ): 676 searches
- Depth 3 (AAA-ZZZ): 17,576 searches
- **Total:** 18,278 prefix searches

#### Discovery Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    DISCOVERY STAGE                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│   │  Generate   │───▶│   Search    │───▶│  Collect    │    │
│   │  Prefixes   │    │  AHPRA      │    │  Results    │    │
│   │  (A-ZZZ)    │    │  Register   │    │             │    │
│   └─────────────┘    └─────────────┘    └─────────────┘    │
│         │                   │                   │           │
│         ▼                   ▼                   ▼           │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│   │  Track in   │◀───│   Handle    │◀───│   Extract   │    │
│   │  Checkpoint │    │   Errors    │    │   reg_id    │    │
│   │             │    │   & Retry   │    │   + URL     │    │
│   └─────────────┘    └─────────────┘    └─────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Data Collected in Discovery (Phase 1)

From search results (without clicking each profile):
- **`reg_id` ONLY** - Registration ID (e.g., NMW0001943612)

**Important:** Phase 1 extracts **only registration IDs** to create a list of practitioners to fetch in Phase 2. No other data (name, profession, location, etc.) is collected in Phase 1. These "keys" are used to fetch full practitioner details via API POST in Phase 2.

### Stage 2: Extraction

**Purpose:** Fetch complete practitioner information using HTTP POST API requests.

**Method:** HTTP POST requests to AHPRA (not browser automation)

**Endpoint:**
```
POST https://www.ahpra.gov.au/Registration/Registers-of-Practitioners.aspx
```

**Request Parameters:**
```python
data = {
    'health-profession': '',      # Empty (not filtering)
    'state': '',                  # Empty (not filtering)
    'suburb': '',                 # Empty (not filtering)
    'postcode': '',               # Empty (not filtering)
    'name-reg': '',               # Empty (not filtering)
    'practitioner-row-id': reg_id # KEY FIELD: Registration ID from Phase 1
}
```

**Response:** HTML of practitioner's detail page containing all 16 fields

#### Extraction Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│             EXTRACTION STAGE (API POST)                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    │
│   │   Load Pending   │───▶│  POST to AHPRA   │───▶│   Parse HTML     │    │
│   │   reg_ids from   │    │  (30-40s         │    │   Response       │    │
│   │   Phase 1        │    │   delays)        │    │                  │    │
│   └──────────────────┘    └──────────────────┘    └──────────────────┘    │
│         │                       │                       │                 │
│         ▼                       ▼                       ▼                 │
│   ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐    │
│   │  Write to CSV    │◀───│   Mark as        │◀───│   Extract 16     │    │
│   │                  │    │   Extracted in   │    │   Fields from    │    │
│   │                  │    │   Checkpoint     │    │   HTML with BS4  │    │
│   └──────────────────┘    └──────────────────┘    └──────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Data Fields (16 Total)

| Field | Description | Source | Phase |
|-------|-------------|--------|-------|
| `reg_id` | Registration ID | Phase 1 Discovered | 1 |
| `name` | Full name | Phase 2 API Response | 2 |
| `name_title` | Title (Dr, Mr, Ms, etc.) | Phase 2 API Response | 2 |
| `first_name` | First name | Parsed from name (Phase 2) | 2 |
| `middle_name` | Middle name(s) | Parsed from name (Phase 2) | 2 |
| `last_name` | Surname | Parsed from name (Phase 2) | 2 |
| `profession` | Health profession | Phase 2 API Response | 2 |
| `registration_status` | Current status | Phase 2 API Response | 2 |
| `first_reg_date` | First registration date | Phase 2 API Response | 2 |
| `reg_expiry` | Registration expiry date | Phase 2 API Response | 2 |
| `endorsement` | Endorsements/specialties | Phase 2 API Response | 2 |
| `sex` | Sex/Gender | Phase 2 API Response | 2 |
| `suburb` | Practice suburb | Phase 2 API Response | 2 |
| `state` | Practice state | Phase 2 API Response | 2 |
| `postcode` | Practice postcode | Phase 2 API Response | 2 |
| `divisions` | Professional divisions | Phase 2 API Response | 2 |

---

## Module Details

### `main.py` - CLI Entry Point

**Commands:**
```bash
python main.py discover                    # Start discovery (adaptive mode)
python main.py discover --comprehensive    # Comprehensive search (A-ZZZ)
python main.py discover -c --depth 2       # Depth 2 only (A-Z, AA-ZZ)
python main.py discover --no-headless      # Visible browser

python main.py extract                     # Extract all pending
python main.py extract --limit 100         # Extract first 100

python main.py status                      # Show progress
python main.py reset --confirm             # Reset all data

python main.py test-url <url>              # Test single URL
```

### `src/browser.py` - BrowserManager

Playwright-based browser automation with:
- Chromium browser with anti-detection flags
- User agent rotation
- Australian locale/timezone
- Configurable timeouts
- Context manager support (`with BrowserManager() as browser:`)

**Key Methods:**
- `navigate(url, wait_until)` - Navigate to URL
- `fill_input(selector, value)` - Fill form fields
- `click(selector)` - Click elements
- `get_elements(selector)` - Query multiple elements
- `rotate_user_agent()` - Switch user agent

### `src/search.py` - Search Strategies

Three strategy classes:

1. **`PrefixGenerator`** - Generates A-Z, AA-ZZ, AAA-ZZZ prefixes
2. **`RecursivePrefixSearch`** - Adaptive mode (expands when needed)
3. **`ComprehensivePrefixSearch`** - Systematic all-depth search
4. **`SearchOrchestrator`** - Coordinates search strategy

**Prefix Generation Math:**
```
Depth 1: 26^1 = 26 prefixes
Depth 2: 26^2 = 676 prefixes
Depth 3: 26^3 = 17,576 prefixes
Total:         18,278 prefixes
```

### `src/discovery.py` - DiscoveryEngine

**CSS Selectors (AHPRA-specific):**
```python
SELECTORS = {
    'search_input': '#name-reg',
    'search_button': '#predictiveSearchHomeBtn',
    'result_row': '.search-results-table-row[data-practitioner-row-id]',
    'no_results': '.no-results-message',
}
```

**Key Methods:**
- `initialize()` - Navigate to search page
- `run_discovery(resume)` - Main discovery loop
- `_search_prefix(prefix)` - Search single prefix
- `_perform_search(term)` - Execute search form
- `_collect_practitioners_from_page()` - Extract from results

### `src/extractor.py` - ExtractionEngine

Fetches practitioner details via HTTP POST API:
- Loads pending `reg_ids` from Phase 1 checkpoint
- Makes HTTP POST requests with `practitioner-row-id` parameter
- Applies 30-40 second rate limiting delays between requests
- Parses HTML responses using `PractitionerParser`
- Writes to CSV file
- Supports resume and limit options

### `src/parser.py` - PractitionerParser

BeautifulSoup-based HTML parser for Phase 2 responses:
- Extracts 16 fields from API response HTML
- Uses CSS selectors to locate field-title and field-entry pairs
- Uses regex patterns for dates, IDs
- Parses name into components (title, first, middle, last)
- Normalizes dates to DD/MM/YYYY format

### `src/checkpoint.py` - CheckpointManager

JSON-based progress tracking across both phases:

**Phase 1 (Discovery):**
- `completed_prefixes` - Set of finished search prefixes
- `scraped_reg_ids` - Set of discovered registration IDs (also in `data/discovery/reg_ids.txt`)

**Phase 2 (Extraction):**
- `extracted_reg_ids` - Set of fully extracted IDs
- Auto-save every 5 minutes
- Atomic file writes (temp file + rename) prevent corruption

**Checkpoint File:** `data/checkpoints/ahpra_checkpoint.json`

### `config/settings.py` - Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| `MIN_DELAY` | 30s | Min between data scrapes (server-respectful) |
| `MAX_DELAY` | 40s | Max between data scrapes (server-respectful) |
| `UI_MIN_DELAY` | 0.2s | Min for UI interactions within page |
| `UI_MAX_DELAY` | 0.6s | Max for UI interactions within page |
| `BROWSER_TIMEOUT` | 60s | Element timeout |
| `PAGE_LOAD_TIMEOUT` | 120s | Navigation timeout |
| `CHECKPOINT_INTERVAL` | 10 | Save every N items |
| `MAX_RETRIES` | 3 | Retries per failure |
| `RETRY_DELAY` | 60s | Wait between retry attempts |

### `config/professions.py` - Reference Data

- 16 registered health professions
- 8 Australian states/territories
- Professional divisions by profession
- High-volume prefix hints (SM, JO, WI, etc.)

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         DATA FLOW                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  AHPRA Website                                                   │
│       │                                                          │
│       ▼                                                          │
│  ┌─────────────┐                                                 │
│  │   Search    │◀─── Prefix (A, AA, AAA...)                      │
│  │   Results   │                                                 │
│  └─────────────┘                                                 │
│       │                                                          │
│       │ Extract reg_id, name, profession, location               │
│       ▼                                                          │
│  ┌─────────────┐                                                 │
│  │ Checkpoint  │───▶ data/checkpoints/ahpra_checkpoint.json      │
│  │   (JSON)    │                                                 │
│  └─────────────┘                                                 │
│       │                                                          │
│       │ Pending URLs                                             │
│       ▼                                                          │
│  ┌─────────────┐                                                 │
│  │   Profile   │◀─── Click each practitioner                     │
│  │    Pages    │                                                 │
│  └─────────────┘                                                 │
│       │                                                          │
│       │ Extract all 16 fields                                    │
│       ▼                                                          │
│  ┌─────────────┐                                                 │
│  │  CSV Output │───▶ data/extracted/practitioners_YYYY-MM-DD.csv │
│  │             │                                                 │
│  └─────────────┘                                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Error Handling & Resilience

1. **Checkpoint System** - Progress saved every 10 items or 5 minutes
2. **Retry Logic** - 3 retries with exponential backoff
3. **Queue Re-insertion** - Failed prefixes re-added to end of queue
4. **Atomic Saves** - Write to temp file, then rename
5. **Graceful Interruption** - Ctrl+C saves checkpoint before exit

---

## Rate Limiting

To avoid overwhelming AHPRA servers and respect their infrastructure:

### Primary Delays (Between Data Scrapes)
- **30-40 seconds** random delay between each API call/data extraction
- This applies to:
  - Each prefix search in discovery stage
  - Each practitioner profile fetch in extraction stage
  - Any request that hits AHPRA servers

### UI Interaction Delays (Within Same Page)
- **0.2-0.6 seconds** for quick UI interactions
- These are for form filling, dropdown clicks, button presses
- These don't generate additional server requests

### Retry Delays
- **60 seconds** wait before retrying a failed request
- Gives server time to recover from any issues

### Anti-Detection Measures
- User agent rotation (every 10 requests)
- Australian locale simulation
- Session cookie management
- Respectful crawl rate

### Why These Delays Matter
At 30-40 seconds per request:
- Discovery of 18,278 prefixes takes ~152-203 hours (6-8 days)
- Extraction of 900,000 practitioners takes ~7,500-10,000 hours
- This is intentionally slow to minimize server impact

---

## Known Issues & Current Status

### Issue: Profile Page Extraction Not Integrated

**Problem:** The current `discovery.py` only extracts data visible in search results. Detailed fields (registration dates, sex, endorsements) require clicking on each practitioner's name to open their profile page.

**Solution Found:** Through testing, we confirmed that:
1. Clicking practitioner name opens detailed profile page
2. Profile page contains ALL 16 required fields
3. Regex patterns can extract data from profile text content

**Next Step Required:** Integrate the profile page extraction into the workflow:
- Either in discovery stage (click each result)
- Or in extraction stage (visit profile URLs)

### Issue: Search Failures After First Prefix

**Problem:** After the first search, subsequent searches fail because the page navigates to results anchor (`#search-results-anchor`) and the search input becomes detached from DOM.

**Solution Implemented:** Navigate to fresh search page (`AHPRA_SEARCH_URL`) before each prefix search.

---

## Dependencies

```
playwright>=1.40.0      # Browser automation
pandas>=2.0.0           # Data processing
beautifulsoup4>=4.12.0  # HTML parsing
lxml>=5.0.0             # Fast XML/HTML parser
loguru>=0.7.0           # Logging
tqdm>=4.66.0            # Progress bars
python-dotenv>=1.0.0    # Environment variables
```

---

## Usage Examples

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run discovery (comprehensive, visible browser)
python main.py discover --comprehensive --no-headless

# Check progress
python main.py status

# Run extraction (after discovery completes)
python main.py extract --limit 1000

# Test single profile URL
python main.py test-url "https://www.ahpra.gov.au/Registration/Registers-of-Practitioners.aspx?id=NMW0001943612"
```

---

## Estimated Scale

| Metric | Estimate |
|--------|----------|
| Total practitioners | ~900,000+ |
| Prefix searches (comprehensive) | 18,278 |
| Time per search | ~30-40 seconds (respectful delay) |
| Discovery time (comprehensive) | ~152-203 hours (6-8 days) |
| Extraction time (per 1000) | ~8-11 hours |
| Full extraction time | ~7,500-10,000 hours |

**Note:** These long times are intentional to respect AHPRA server load. The scraper is designed to run slowly over extended periods rather than overwhelming the server with rapid requests.

---

## Output Format

**CSV Fields:**
```
name,name_title,first_name,middle_name,last_name,reg_id,profession,registration_status,first_reg_date,reg_expiry,endorsement,sex,suburb,state,postcode,divisions
```

**Example Row:**
```
"Elizabeth Jane Smith",Ms,Elizabeth,Jane,Smith,NMW0001943612,Registered Nurse,Registered,09/01/2015,31/05/2026,,Female,NAMBOUR,QLD,4560,Registered nurse
```
