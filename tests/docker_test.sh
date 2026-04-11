#!/bin/bash
set -e

apt-get update -qq
apt-get install -y -qq curl git ca-certificates
echo "[+] deps done"

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
echo "[+] uv installed: $(uv --version)"

git clone --depth=1 https://github.com/xoste49/MTProxyMaxPy.git /opt/mtproxymaxpy
cd /opt/mtproxymaxpy
echo "[+] repo cloned"

uv sync --no-dev
echo "[+] deps synced"

# Symlink
VENV_BIN="/opt/mtproxymaxpy/.venv/bin/mtproxymaxpy"
ln -sf "$VENV_BIN" /usr/local/bin/mtproxymaxpy
echo "[+] symlink created"

# Check command is available
mtproxymaxpy --help | head -5

# Test download_binary
uv run python - <<'PYEOF'
import logging, os, stat
logging.basicConfig(level=logging.INFO)
from mtproxymaxpy.process_manager import download_binary
from mtproxymaxpy.constants import BINARY_PATH
download_binary()
info = os.stat(BINARY_PATH)
print(f"[+] Binary size  : {info.st_size} bytes")
print(f"[+] Executable   : {bool(info.st_mode & stat.S_IXUSR)}")
import subprocess
result = subprocess.run([str(BINARY_PATH), "--version"], capture_output=True, text=True)
print(f"[+] Version check: {(result.stdout or result.stderr).strip()}")
PYEOF

# Test uv already installed (second run should skip)
echo "[+] Testing uv already-installed detection..."
bash /test.sh 2>&1 | grep -E "uv already installed|Installing uv" | head -2
