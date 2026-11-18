#!/usr/bin/env bash
# One-time (per container rebuild) install of everything the scripts need.
set -euo pipefail
tmp=$(mktemp -d)
wget -q -O "$tmp/chrome.deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$tmp/chrome.deb" pulseaudio pulseaudio-utils ffmpeg
rm -rf "$tmp"
pip install -q edge-tts numpy playwright websockets
google-chrome --version
