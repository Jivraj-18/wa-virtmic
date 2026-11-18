/* E6 page data: the make doctor checklist (results table). Uses renderTable from app.js. */
window.E6_CHECKS = [
  {check: "binaries + modules", verifies: "google-chrome, pulseaudio, pactl/parec/pacat/paplay/parecord, ffmpeg, curl; Python edge_tts, numpy, playwright, websockets, yaml", fix: "bash scripts/install.sh", here: "PASS"},
  {check: "claude code", verifies: "claude CLI installed (WARN only: not needed for the demo)", fix: "bash scripts/install.sh", here: "PASS"},
  {check: "pulseaudio daemon", verifies: "pactl info answers", fix: "bash scripts/audio_setup.sh", here: "PASS"},
  {check: "virtual audio devices", verifies: "virtmic_sink, virtmic, callout_sink exist", fix: "bash scripts/audio_setup.sh", here: "PASS"},
  {check: "default devices", verifies: "default source = virtmic, default sink = callout_sink; virtmic unmuted", fix: "bash scripts/audio_setup.sh", here: "PASS"},
  {check: "suspend-on-idle", verifies: "module-suspend-on-idle unloaded (WARN otherwise)", fix: "bash scripts/audio_setup.sh", here: "PASS (not shown)"},
  {check: "noVNC (port 6080)", verifies: "something listens on :6080; prints the forwarded URL", fix: "/usr/local/share/desktop-init.sh true, or rebuild", here: "PASS"},
  {check: "X display", verifies: "/tmp/.X11-unix/X1 exists", fix: "/usr/local/share/desktop-init.sh true, or rebuild", here: "PASS"},
  {check: "/dev/shm", verifies: ">= 512 MB (WARN otherwise)", fix: "runArgs --shm-size=1g, rebuild", here: "PASS"},
  {check: "chrome CDP (:9222)", verifies: "GET /json/version", fix: "bash scripts/launch_chrome.sh", here: "PASS; FAIL path tested on a closed port"},
  {check: "whatsapp login", verifies: "read-only DOM probe (Runtime.evaluate) of the WhatsApp tab: chat list / QR / loading", fix: "open noVNC and scan the QR (Linked devices)", here: "PASS; QR path tested on a separate headless Chrome"},
  {check: "auto_answer.py", verifies: "exactly one python auto_answer.py process (WARN if 0 or 2+)", fix: "make demo / make stop", here: "PASS"},
  {check: "scripts/.env", verifies: "file exists, LLM_GATEWAY_BASE + LLM_GATEWAY_TOKEN set", fix: "cp scripts/.env.example scripts/.env and fill in", here: "PASS; FAIL path tested"},
  {check: "gateway reachable", verifies: "TCP + TLS connect to the gateway host (no HTTP request)", fix: "check LLM_GATEWAY_BASE / network", here: "PASS"},
  {check: "realtime client secret", verifies: "one POST /openai/v1/realtime/client_secrets with a nonce, expects ek_...", fix: "per HTTP code: 401 token, 403 access, 429 wait", here: "PASS (about 1 s)"},
  {check: "realtime host reachable", verifies: "TCP connect api.openai.com:443 (the WebSocket bypasses the gateway)", fix: "firewall / proxy rules", here: "PASS"},
];

function renderChecks(el) {
  renderTable(el, window.E6_CHECKS, [
    {key: "check", label: "Check"},
    {key: "verifies", label: "What it verifies (read-only)"},
    {key: "fix", label: "Fix it prints"},
    {key: "here", label: "In this Codespace"},
  ]);
}
