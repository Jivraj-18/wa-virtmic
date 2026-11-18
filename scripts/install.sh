#!/usr/bin/env bash
# Install everything the scripts need. Idempotent: safe to re-run, only installs what is missing.
# Runs automatically as the devcontainer's postCreateCommand; can also be run by hand after a rebuild.
#   FORCE_CHROME=1   reinstall/upgrade Google Chrome even if present
#   SKIP_CLAUDE=1    don't install Claude Code
set -euo pipefail

# --- apt: Google Chrome (.deb) + PulseAudio + ffmpeg ------------------------------------------
missing=()
for p in pulseaudio pulseaudio-utils ffmpeg ripgrep poppler-utils; do
  dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
done
debs=()
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
if ! command -v google-chrome >/dev/null 2>&1 || [ "${FORCE_CHROME:-0}" = 1 ]; then
  echo "install.sh: downloading Google Chrome"
  wget -q -O "$tmp/chrome.deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  debs+=("$tmp/chrome.deb")
fi
if [ ${#missing[@]} -gt 0 ] || [ ${#debs[@]} -gt 0 ]; then
  echo "install.sh: apt install ${debs[*]} ${missing[*]}"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${debs[@]}" "${missing[@]}"
else
  echo "install.sh: apt packages already installed"
fi

# --- pip: only the modules that don't import yet ----------------------------------------------
pipmiss=()
for pair in edge_tts:edge-tts numpy:numpy playwright:playwright websockets:websockets yaml:pyyaml; do
  python3 -c "import ${pair%%:*}" 2>/dev/null || pipmiss+=("${pair#*:}")
done
if [ ${#pipmiss[@]} -gt 0 ]; then
  echo "install.sh: pip install ${pipmiss[*]}"
  python3 -m pip install -q "${pipmiss[@]}"
else
  echo "install.sh: python modules already installed"
fi

# --- Claude Code (official native installer; npm as a fallback) -------------------------------
if [ "${SKIP_CLAUDE:-0}" != 1 ]; then
  export PATH="$HOME/.local/bin:$PATH"
  if command -v claude >/dev/null 2>&1; then
    echo "install.sh: Claude Code already installed ($(claude --version 2>/dev/null | head -1))"
  else
    echo "install.sh: installing Claude Code"
    curl -fsSL https://claude.ai/install.sh | bash \
      || { command -v npm >/dev/null 2>&1 && npm install -g @anthropic-ai/claude-code; } \
      || echo "install.sh: WARNING Claude Code install failed (not needed for the demo)"
  fi
fi

google-chrome --version
