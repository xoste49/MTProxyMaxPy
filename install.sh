#!/bin/bash
# MTProxyMax Quick Installer (Python edition)
# Usage: curl -sL https://raw.githubusercontent.com/xoste49/MTProxyMaxPy/main/install.sh | sudo bash
set -e

REPO_URL="https://github.com/xoste49/MTProxyMaxPy.git"
INSTALL_DIR="/opt/mtproxymaxpy"
UV_BIN="$(command -v uv 2>/dev/null || true)"

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: run as root." >&2
  exit 1
fi

# ── Install uv if not present ────────────────────────────────────────────────
if [ -z "$UV_BIN" ]; then
  echo "[*] Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  UV_BIN="$(command -v uv)"
fi

# ── Download / update the project ─────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "[*] Updating MTProxyMax..."
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "[*] Cloning MTProxyMax..."
  git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
fi

# ── Install Python deps ────────────────────────────────────────────────────────
echo "[*] Installing Python dependencies..."
cd "$INSTALL_DIR"
"$UV_BIN" sync --no-dev

# ── Run the installer wizard ───────────────────────────────────────────────────
echo "[*] Running installer..."
"$UV_BIN" run mtproxymaxpy install

echo "[+] Done. Run 'mtproxymaxpy' to open the TUI."
