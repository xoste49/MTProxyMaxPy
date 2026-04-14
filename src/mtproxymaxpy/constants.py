"""Global constants for MTProxyMaxPy."""

from pathlib import Path

# ── Version ────────────────────────────────────────────────────────────────────
VERSION = "1.0.0"
TELEMT_MIN_VERSION = "3.3.39"
TELEMT_VERSION = "3.3.39"
TELEMT_COMMIT = "bc69153"

# ── Paths ──────────────────────────────────────────────────────────────────────
INSTALL_DIR = Path("/opt/mtproxymaxpy")
CONFIG_DIR = INSTALL_DIR / "mtproxy"
STATS_DIR = INSTALL_DIR / "relay_stats"
BACKUP_DIR = INSTALL_DIR / "backups"
SSH_DIR = INSTALL_DIR / ".ssh"

SETTINGS_FILE = INSTALL_DIR / "settings.toml"
SECRETS_FILE = INSTALL_DIR / "secrets.json"
UPSTREAMS_FILE = INSTALL_DIR / "upstreams.json"
INSTANCES_FILE = INSTALL_DIR / "instances.json"
TOML_CONFIG_FILE = CONFIG_DIR / "config.toml"
CONNECTION_LOG = INSTALL_DIR / "connection.log"

# Legacy bash MTProxyMax install dir (no 'py' suffix — original bash project)
LEGACY_BASH_DIR = Path("/opt/mtproxymax")

# Legacy bash config paths — check both possible locations:
#   /opt/mtproxymaxpy/settings.conf  (if user copied files here)
#   /opt/mtproxymax/settings.conf    (default bash install)
LEGACY_SETTINGS_FILE = INSTALL_DIR / "settings.conf"
LEGACY_SECRETS_FILE = INSTALL_DIR / "secrets.conf"
LEGACY_UPSTREAMS_FILE = INSTALL_DIR / "upstreams.conf"
LEGACY_INSTANCES_FILE = INSTALL_DIR / "instances.conf"

LEGACY_BASH_SETTINGS_FILE = LEGACY_BASH_DIR / "settings.conf"
LEGACY_BASH_SECRETS_FILE = LEGACY_BASH_DIR / "secrets.conf"
LEGACY_BASH_UPSTREAMS_FILE = LEGACY_BASH_DIR / "upstreams.conf"
LEGACY_BASH_INSTANCES_FILE = LEGACY_BASH_DIR / "instances.conf"

# ── Self-update ────────────────────────────────────────────────────────────────
GITHUB_REPO = "xoste49/MTProxyMaxPy"
GITHUB_API_COMMITS = "https://api.github.com/repos/xoste49/MTProxyMaxPy/commits/main"
UPDATE_SHA_FILE = INSTALL_DIR / ".update_sha"
UPDATE_BADGE_FILE = Path("/tmp/.mtproxymaxpy_update_available")

# ── Telemt binary ──────────────────────────────────────────────────────────────
BINARY_DIR = INSTALL_DIR / "bin"
BINARY_NAME = "telemt"
BINARY_PATH = BINARY_DIR / BINARY_NAME

TELEMT_RELEASES_URL = "https://github.com/telemt/telemt/releases/download"
TELEMT_GITHUB_API = "https://api.github.com/repos/telemt/telemt/releases/latest"

# Fallback download URL template: {version} and {arch} are substituted at runtime
# Assets are named e.g. telemt-x86_64-linux-gnu.tar.gz (no 'v' prefix on tag)
TELEMT_DOWNLOAD_URL_TEMPLATE = (
    "https://github.com/telemt/telemt/releases/download/{version}/telemt-{arch}-linux-gnu.tar.gz"
)

# ── Defaults ───────────────────────────────────────────────────────────────────
DEFAULT_PORT = 443
DEFAULT_METRICS_PORT = 9090
DEFAULT_DOMAIN = "cloudflare.com"
DEFAULT_CONCURRENCY = 8192
DEFAULT_FAKE_CERT_LEN = 2048
DEFAULT_MASKING_HOST = "cloudflare.com"
DEFAULT_MASKING_PORT = 443
DEFAULT_TELEGRAM_INTERVAL_HOURS = 6
DEFAULT_REPLICATION_SYNC_INTERVAL = 60
DEFAULT_SSH_PORT = 22
DEFAULT_MANAGER_UPDATE_BRANCH = "main"

# ── Systemd unit names ─────────────────────────────────────────────────────────
SYSTEMD_SERVICE = "mtproxymaxpy"
SYSTEMD_TELEGRAM_SERVICE = "mtproxymaxpy-telegram"
SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")

# ── Public IP detection endpoints ─────────────────────────────────────────────
PUBLIC_IP_ENDPOINTS = [
    "https://api.ipify.org?format=json",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
]
PUBLIC_IP_CACHE_TTL = 300  # seconds

# ── Terminal UI ────────────────────────────────────────────────────────────────
APP_TITLE = "MTProxyMaxPy"
BANNER = r"""
  __  __ _____ ___                       __  __
 |  \/  |_   _| _ \_ _ _____ ___  _  _|  \/  |__ ___ __
 | |\/| | | | |  _/ '_/ _ \ \ / || | | |\/| / _` \ \ /
 |_|  |_| |_| |_| |_| \___/_\_\_, | |_|  |_\__,_/_\_\
                                |__/
"""
