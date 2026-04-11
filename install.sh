#!/bin/bash
# MTProxyMax Quick Installer (Python edition)
# Usage: curl -sL https://raw.githubusercontent.com/xoste49/MTProxyMaxPy/main/install.sh | sudo bash
set -e

REPO_URL="https://github.com/xoste49/MTProxyMaxPy.git"
INSTALL_DIR="/opt/mtproxymaxpy"

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: run as root." >&2
  exit 1
fi

# ── Install uv if not present ────────────────────────────────────────────────
# Check both PATH and the default install location
UV_BIN="$(command -v uv 2>/dev/null || echo "")"
if [ -z "$UV_BIN" ] && [ -x "$HOME/.local/bin/uv" ]; then
  UV_BIN="$HOME/.local/bin/uv"
fi

if [ -z "$UV_BIN" ]; then
  echo "[*] Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  UV_BIN="$(command -v uv)"
else
  echo "[*] uv already installed: $($UV_BIN --version)"
fi

# ── Download / update the project ─────────────────────────────────────────────
IS_UPDATE=false
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "[*] Updating MTProxyMaxPy..."
  git -C "$INSTALL_DIR" pull --ff-only
  IS_UPDATE=true
else
  echo "[*] Cloning MTProxyMaxPy..."
  git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
fi

# ── Install Python deps ────────────────────────────────────────────────────────
echo "[*] Installing Python dependencies..."
cd "$INSTALL_DIR"
"$UV_BIN" sync --no-dev

# ── Create global command symlink ─────────────────────────────────────────────
VENV_BIN="$INSTALL_DIR/.venv/bin/mtproxymaxpy"
if [ -f "$VENV_BIN" ]; then
  ln -sf "$VENV_BIN" /usr/local/bin/mtproxymaxpy
  echo "[+] Command 'mtproxymaxpy' linked to /usr/local/bin/mtproxymaxpy"
fi

# ── Run the installer (first install only) ────────────────────────────────────
if [ "$IS_UPDATE" = true ]; then
  echo "[+] Update complete. Run 'mtproxymaxpy' to open the manager."
else
  echo "[*] Starting setup wizard..."
  # If stdin is a TTY (interactive session) launch the full TUI wizard.
  # In non-interactive mode (piped curl | bash) fall back to headless install.
  if [ -t 0 ] && [ -t 1 ]; then
    "$UV_BIN" run mtproxymaxpy
  else
    "$UV_BIN" run mtproxymaxpy install
  fi
fi

echo "[+] Done. Run 'mtproxymaxpy status' to check service status."
