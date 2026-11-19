#!/usr/bin/env bash
# Install everything wa-virtmic needs, inside a proot-distro Debian/Ubuntu rootfs on Android (Termux).
# Run this INSIDE the proot distro (after `proot-distro login debian`), not in Termux itself.
# Idempotent: safe to re-run, only installs what is missing. See docs/TERMUX.md for the full setup.
#
# Mirrors scripts/install.sh, with one difference: there is no arm64 build of Google Chrome, so this
# installs Debian's `chromium` package and symlinks it as `google-chrome` / `google-chrome-stable`.
# Every other script in this repo (launch_chrome.sh, doctor.py, demo.sh, scripts/meet/maya.py) looks for
# `google-chrome` by name, so they all work unmodified once the symlink is in place.
#
#   SKIP_CLAUDE=1   don't install Claude Code
set -euo pipefail

SUDO=""
if [ "$(id -u)" != 0 ]; then
  command -v sudo >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq sudo; }
  SUDO="sudo"
fi

# --- apt: chromium (arm64) + PulseAudio + ffmpeg --------------------------------------------------
missing=()
for p in chromium pulseaudio pulseaudio-utils ffmpeg ripgrep poppler-utils ca-certificates curl git python3-pip python3-venv; do
  dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "install_termux.sh: apt install ${missing[*]}"
  $SUDO apt-get update -qq
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
else
  echo "install_termux.sh: apt packages already installed"
fi

CHROME_BIN="$(command -v chromium || command -v chromium-browser || true)"
if [ -z "$CHROME_BIN" ]; then
  echo "install_termux.sh: chromium not found after apt install" >&2
  exit 1
fi
for name in google-chrome google-chrome-stable; do
  [ -e "/usr/local/bin/$name" ] || $SUDO ln -s "$CHROME_BIN" "/usr/local/bin/$name"
done
echo "install_termux.sh: $CHROME_BIN symlinked as google-chrome"

# --- pip: only the modules that don't import yet ---------------------------------------------------
pipmiss=()
for pair in edge_tts:edge-tts numpy:numpy playwright:playwright websockets:websockets yaml:pyyaml; do
  python3 -c "import ${pair%%:*}" 2>/dev/null || pipmiss+=("${pair#*:}")
done
if [ ${#pipmiss[@]} -gt 0 ]; then
  echo "install_termux.sh: pip install ${pipmiss[*]}"
  # Debian 12+ (bookworm/trixie) marks the system Python as "externally managed" (PEP 668).
  python3 -m pip install -q --break-system-packages "${pipmiss[@]}" 2>/dev/null \
    || python3 -m pip install -q "${pipmiss[@]}"
else
  echo "install_termux.sh: python modules already installed"
fi
# Playwright here is only ever used as a CDP *client* (connect_over_cdp against the chromium we just
# installed) - it never launches its own bundled browser, so it doesn't need `playwright install`.
# Its driver binary is still architecture-specific; this is the one step worth checking by hand first:
python3 -c "import playwright" 2>/dev/null \
  && echo "install_termux.sh: playwright import OK" \
  || echo "install_termux.sh: WARNING playwright import failed - see the 'known unknown' note in docs/TERMUX.md"

# --- Claude Code (official native installer; npm as a fallback) -----------------------------------
if [ "${SKIP_CLAUDE:-0}" != 1 ]; then
  export PATH="$HOME/.local/bin:$PATH"
  if command -v claude >/dev/null 2>&1; then
    echo "install_termux.sh: Claude Code already installed ($(claude --version 2>/dev/null | head -1))"
  else
    echo "install_termux.sh: installing Claude Code"
    curl -fsSL https://claude.ai/install.sh | bash \
      || { command -v npm >/dev/null 2>&1 && npm install -g @anthropic-ai/claude-code; } \
      || echo "install_termux.sh: WARNING Claude Code install failed (not needed for the demo)"
  fi
fi

"$CHROME_BIN" --version
