"""
AHPRA Scraper Configuration Settings
"""

import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Data subdirectories
DISCOVERY_DIR = DATA_DIR / "discovery"
EXTRACTED_DIR = DATA_DIR / "extracted"
FINAL_DIR = DATA_DIR / "final"
CHECKPOINT_DIR = DATA_DIR / "checkpoints"
BACKUP_DIR = DATA_DIR / "backup"

# Discovery output files:
# - discovered_ids.json: Main JSON file with all IDs and metadata (saved periodically)
# - discovered_ids.raw.txt: Append-only backup (saved IMMEDIATELY per ID, failsafe)
DISCOVERED_IDS_FILE = DISCOVERY_DIR / "discovered_ids.json"
# Note: Raw backup file is auto-created at: DISCOVERED_IDS_FILE.with_suffix('.raw.txt')

# Extraction output files:
# - extracted_backup.jsonl: JSONL format, one JSON object per line (16 fields per record)
# - extracted_backup.meta.json: Metadata file with stats
# - practitioners_YYYY-MM-DD.csv: CSV output (16 fields per record)
EXTRACTED_BACKUP_FILE = BACKUP_DIR / "extracted_backup.jsonl"

# Rate limiting (respectful approach - avoid server overload)
# These are the primary delays between data scrapes/API calls
MIN_DELAY = 0.8  # Minimum seconds between requests (increased to avoid CAPTCHA)
MAX_DELAY = 2  # Maximum seconds between requests

# UI interaction delays (for form filling, dropdown clicks within same page)
UI_MIN_DELAY = 0.5  # Quick UI interactions
UI_MAX_DELAY = 1.2  # Quick UI interactions

# Sidebar filter delays (for optimized discovery mode)
# These are longer delays to avoid triggering CAPTCHA when using sidebar filters
# Note: 7-10s triggers CAPTCHA, 10-15s works fine
# Testing 8-11s as potential optimization (monitor for CAPTCHA)
SIDEBAR_FILTER_MIN_DELAY = 1.5   # Minimum seconds between sidebar filter changes
SIDEBAR_FILTER_MAX_DELAY = 2.5  # Maximum seconds between sidebar filter changes

# Search settings
MAX_RESULTS_PER_PAGE = 100  # AHPRA typically shows ~50 results per page
MAX_PREFIX_DEPTH = 4       # Maximum recursion depth (e.g., AAAA)
PAGINATION_LIMIT = 10    # Max pages to paginate through per prefix

# Browser settings
HEADLESS = True
BROWSER_TIMEOUT = 10000    # 10 seconds
PAGE_LOAD_TIMEOUT = 20000  # 20 seconds for slow pages
VIEWPORT_WIDTH = 1080
VIEWPORT_HEIGHT = 900

# AHPRA URLs
AHPRA_BASE_URL = "https://www.ahpra.gov.au"
AHPRA_SEARCH_URL = "https://www.ahpra.gov.au/Registration/Registers-of-Practitioners.aspx"

# Output settings
OUTPUT_ENCODING = "utf-8"
CSV_SEPARATOR = ","

# Checkpoint settings
CHECKPOINT_INTERVAL = 50   # Save checkpoint every N practitioners
AUTO_SAVE_INTERVAL = 100   # Auto-save every 5 minutes (in seconds)
PROGRESS_DISPLAY_INTERVAL = 10  # Display progress every N practitioners

# Logging settings
LOG_LEVEL = "INFO"
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
LOG_ROTATION = "10 MB"
LOG_RETENTION = "30 days"

# User agent rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# Retry settings
MAX_RETRIES = 2
RETRY_DELAY = 5  # 60 seconds between retries (give server time to recover)

# Data fields to extract
DATA_FIELDS = [
    "name",
    "name_title",
    "first_name",
    "middle_name",
    "last_name",
    "reg_id",
    "profession",
    "registration_status",
    "first_reg_date",
    "reg_expiry",
    "endorsement",
    "sex",
    "suburb",
    "state",
    "postcode",
    "divisions",
]
