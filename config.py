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

# Avi's acrylic-supplier sheet ("Jacks_Inventory_Sheet") — same Sky-style format.
ACRYLIC_SHEET_ID = "1VtpZ4OXKSRJ7Qf1zyuAFLJWsBHynCQteA7DTOySpBLI"

# All supplier inventory sheets (same column format), read + merged into one feed.
SUPPLIER_SHEET_IDS = [SKY_SHEET_ID, ACRYLIC_SHEET_ID]

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

# === PPC budget glide-path (inventory-aware ad budget taper) ===
# Above the START day count, a campaign runs at full (baseline) budget. As FBA
# days-of-stock fall toward the FLOOR day count, the budget tapers DOWN LINEARLY to
# FLOOR_PCT of baseline — never to zero, so we keep a trickle and don't lose rank.
# When stock recovers above START, it glides back to 100%. Heroes are protected
# earlier (higher START) and a touch more gently (higher FLOOR_PCT).
PPC_TAPER_START_DAYS = 60          # regular: full budget at/above this many FBA days left
PPC_TAPER_START_DAYS_HERO = 75     # hero: full budget at/above this
PPC_TAPER_FLOOR_DAYS = 14          # regular: budget hits the floor at/below this
PPC_TAPER_FLOOR_DAYS_HERO = 21     # hero: floor at/below this
PPC_TAPER_FLOOR_PCT = 0.20         # regular: minimum budget = 20% of baseline
PPC_TAPER_FLOOR_PCT_HERO = 0.25    # hero: minimum 25% of baseline
PPC_MIN_BUDGET = 5.0               # never recommend a daily budget below this ($)
PPC_BUDGET_DEADBAND_PCT = 0.05     # ignore tiny changes (<5% off current) to avoid churn

# Behavior B (multi-SKU ad groups): pause a SKU's product ad below REMOVE days, re-enable
# it above READD days. Two thresholds (a gap) prevent day-to-day on/off flip-flopping.
PPC_AD_REMOVE_DAYS = 20
PPC_AD_READD_DAYS = 40

# Amazon Ads console "entity" id for your account (the ENTITY... value in the console
# URL). Used to build clickable links from the dashboard into Campaign Manager. NOTE:
# the console uses different campaign IDs than the API and there's no way to map them,
# so links open your account's campaign list (search the campaign name shown), not the
# exact campaign.
ADS_ENTITY_ID = "ENTITYGOPMMFSG9YH9"

# === Output ===
CACHE_DIR = "~/.config/kitchentoolz-inventory"
