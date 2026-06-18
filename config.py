"""Configuration: sheet IDs, default thresholds, lead times."""

# === Google Sheet IDs ===
# Sellerboard inventory data (read-only, owned by Matan at GNO Partners)
SELLERBOARD_SHEET_ID = "1nBrMZfhDJeLI-EpOgar4WF_MvdAw7PkQ5LvhNFSqfNo"
SELLERBOARD_TAB = "Inv_Data"

# Shimon's editable China inventory — now lives as the "China Inventory" tab inside
# the dashboard workbook (everything in one place). Original standalone sheet kept as
# a backup at 1Dnc2AIv6jLYYz4Ay1A1fNsIxv0Fo-xw0jC5ygW6rqaQ.
CHINA_SHEET_ID = "1QHiUJcJKBBYszsivo_OS9KW8kJMH6GeUyDHhfFravqM"
CHINA_TAB = "China Inventory"

# Sky's master inventory sheet ("Inventory details from Sky"). Read-only source for
# live warehouse stock + in-production quantities, joined to our SKUs on "Sku name".
SKY_SHEET_ID = "1l3vYla_vwnC767ZXsx31KQx2H5VCjASy2vywdlpEehA"

# === Default thresholds ===
# Days-of-inventory (DOI) buffers in FBA. Per-SKU overrides win if set in China sheet.
DEFAULT_MIN_FBA_DOI = 60     # below this → consider Ship-Now
DEFAULT_MAX_FBA_DOI = 90     # above this → no action needed
HERO_MIN_FBA_DOI = 90        # heroes get deeper buffers
HERO_MAX_FBA_DOI = 120

# === Lead times (default per-SKU, China-side replenishment cycle) ===
DEFAULT_MANUF_LEAD_TIME_DAYS = 45    # factory production time
DEFAULT_OCEAN_TRANSIT_DAYS = 35      # China port → US port
DEFAULT_FBA_CHECK_IN_DAYS = 10       # US port → checked in at FBA

# === Alert thresholds ===
OOS_WARNING_DAYS = 30                # OOS warning if fewer than N days left in FBA
SHIP_NOW_CRITICAL_DAYS = 14          # CRITICAL urgency below N days FBA left

# === Output ===
CACHE_DIR = "~/.config/kitchentoolz-inventory"
