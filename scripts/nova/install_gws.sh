#!/data/data/com.termux/files/usr/bin/bash
# Install the Google Workspace CLI (gws) on native Termux (aarch64). Safe to re-run.
#   bash scripts/nova/install_gws.sh [version]
# The npm package has no Android build; the static aarch64-musl release runs, but musl looks for /etc/resolv.conf
# and /etc/ssl (absent on Android) -> ~/.local/bin/gws is a wrapper that binds Termux's copies with proot.
set -euo pipefail
V="${1:-0.22.5}"
A=google-workspace-cli-aarch64-unknown-linux-musl.tar.gz
U="https://github.com/googleworkspace/cli/releases/download/v$V/$A"
command -v proot >/dev/null || pkg install -y proot
D=$(mktemp -d); trap 'rm -rf "$D"' EXIT
curl -fsSL "$U" -o "$D/$A"; curl -fsSL "$U.sha256" -o "$D/sum"
[ "$(cut -d' ' -f1 "$D/sum")" = "$(sha256sum "$D/$A" | cut -d' ' -f1)" ] || { echo "checksum mismatch"; exit 1; }
tar xzf "$D/$A" -C "$D"; mkdir -p ~/.local/bin; install -m 755 "$(find "$D" -name gws -type f | head -1)" ~/.local/bin/gws.bin
cat > ~/.local/bin/gws <<'W'
#!/data/data/com.termux/files/usr/bin/bash
# gws (static musl build) on native Termux: bind Termux's resolv.conf + CA certs where musl expects them.
export GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND="${GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND:-file}"
export SSL_CERT_FILE="${SSL_CERT_FILE:-$PREFIX/etc/tls/cert.pem}"
exec proot -b "$PREFIX/etc/resolv.conf:/etc/resolv.conf" -b "$PREFIX/etc/tls:/etc/ssl" "$HOME/.local/bin/gws.bin" "$@"
W
chmod 755 ~/.local/bin/gws; mkdir -p ~/.config/gws; chmod 700 ~/.config/gws
gws --version && gws schema calendar.events.list >/dev/null && echo "gws OK (network + discovery work)"
