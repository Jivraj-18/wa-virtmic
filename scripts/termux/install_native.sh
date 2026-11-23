#!/data/data/com.termux/files/usr/bin/bash
# Native Termux install (no proot): everything the answerer and the bench need. Idempotent; run from Termux.
#   bash scripts/termux/install_native.sh
# See docs/TERMUX_NATIVE.md for why (proot's ptrace tracer froze PulseAudio during calls).
set -euo pipefail
[ "$(uname -o)" = Android ] || { echo "run this in plain Termux, not inside proot"; exit 1; }
pkg install -y x11-repo
pkg install -y chromium xorg-server-xvfb xorg-xdpyinfo pulseaudio python-playwright nodejs python-numpy ffmpeg \
  python-cryptography python-pip clang make pkg-config libsrtp libvpx libopus termux-api
python -c "import aiortc, av" 2>/dev/null || pip install aiortc
# Termux names it chromium-browser; the scripts (launch_chrome.sh, meet/browser.py) call google-chrome.
mkdir -p "$HOME/.local/bin"
ln -sfn "$PREFIX/bin/chromium-browser" "$HOME/.local/bin/google-chrome"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "NOTE: add ~/.local/bin to PATH (e.g. in ~/.bashrc)";; esac
python -W ignore -c "import aiortc, av, numpy, playwright; print('python modules OK')"
echo "chromium: $(chromium-browser --version 2>/dev/null)"
