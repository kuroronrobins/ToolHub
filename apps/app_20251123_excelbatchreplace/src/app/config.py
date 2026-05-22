# Configuration defaults for Excel batch replace tool.

DEFAULT_TEMPLATE_DIR = "templates"
DEFAULT_BACKUP_SUBDIR = "backups"
TEMPLATE_DEFAULT_SHEET = "AllFile"
TEMPLATE_SETTINGS_SHEET = "__TemplateSettings"  # kept for backward compatibility (no longer written)

# Marker that keeps the destination cell unchanged when found in a template.
SKIP_MARKER = "--"  # easy to入力、"変更しない"の意味を示す

# Default path for persisting lightweight app/template settings.
DEFAULT_STATE_FILE = "app_state.json"

# App cache directory for lightweight persisted data.
CACHE_DIR = "cache"

# Basic app metadata shown in the UI/menu bar. Edit here to update the display.
APP_TITLE = "Excel一括置換ツール"
APP_VERSION = "1.1.0"
APP_LAST_UPDATED = "2025-11-28"
APP_LICENSE_HOLDER = "KokiKurokawa"

# GUI labels and strings can be centralized here as needed.
