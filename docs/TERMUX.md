# Running on your own Android phone (Termux + proot-distro, no Codespace)

> **UNTESTED ON A REAL DEVICE.** Written and reasoned through from the Codespace path (which *is* tested -
> see the root README) plus well-documented Termux/proot-distro/Termux:X11 patterns, but not yet run start
> to finish on a phone. Expect to debug one or two steps; `scripts/doctor.py` and `scripts/measure_resources.sh`
> below will tell you exactly where. Report back what broke and this doc gets fixed.

Same software as the Codespace - Chromium + PulseAudio virtual devices + the Python scripts + Claude Code -
just running on the phone itself instead of a cloud container. Nothing in `install.sh`/`audio_setup.sh`/
`launch_chrome.sh`/`demo.sh` is Codespaces-specific; they're plain Debian + PulseAudio + Chrome commands.

## Why proot-distro (and not raw Termux, and not Docker)

- Termux itself runs on Android's **bionic** libc, not glibc. Playwright's driver and some pip wheels
  (built for standard Linux) don't run on it directly.
- Unrooted Android has no privilege for Docker's cgroups/namespaces/overlayfs - there's no real `dockerd` here.
- **`proot-distro`** gives you a real Debian/Ubuntu **arm64** glibc rootfs inside Termux (ptrace-based syscall
  translation, no root needed). It's not kernel-level container isolation, but it's isolated and disposable
  (`proot-distro reset debian` wipes it clean), and it's a standard enough Linux that the existing scripts
  need almost no changes - just `chromium` instead of the x86-only Google Chrome `.deb` (handled by
  `scripts/install_termux.sh`, which symlinks it as `google-chrome` so nothing else has to change).
- Nothing in this pipeline touches the phone's real speaker/mic - it's virtual PulseAudio loopback sinks
  talking to Chromium, same as the Codespace - so there's no Android audio-HAL bridging to get right either.

If you're on a Pixel 6+ on Android 15+, Google's built-in **Linux Terminal** (Settings > System > Developer
options) is a real VM and may be worth trying instead - better isolation/perf, but far less tested anywhere
for this kind of GUI+audio workload, and only available on that specific hardware.

## What you end up with

```
Termux (Android, bionic)
 ├─ Termux:X11 app            - the GUI surface (shows Chromium's window)
 ├─ proot-distro: Debian      - the actual "container"
 │   ├─ chromium (symlinked google-chrome), PulseAudio (virtmic/callout_sink), ffmpeg
 │   ├─ scripts/*.py, auto_answer.py / scripts/meet/maya.py
 │   └─ Claude Code  →  `claude remote-control`  →  driven from claude.ai, from anywhere
 └─ x11vnc + novnc + cloudflared  - optional: view the desktop (QR scan) from any browser, anywhere
```

## Step by step (assume nothing is installed yet)

### 1. Install the two apps

- **Termux** - from [F-Droid](https://f-droid.org/packages/com.termux/), **not** the Play Store build (it's
  outdated/unmaintained there).
- **Termux:X11** - from the [termux-x11 GitHub releases](https://github.com/termux/termux-x11/releases).
  Install the matching version from the same project; mismatched builds are the #1 reported issue.

### 2. Baseline Termux setup

```bash
termux-setup-storage
pkg update -y && pkg upgrade -y
pkg install -y git proot-distro
```

### 3. Clone the repo and take the "before" snapshot

```bash
git clone https://github.com/Jivraj-18/wa-virtmic.git
cd wa-virtmic
bash scripts/measure_resources.sh before
```

This is your baseline: Termux + git + an empty clone, nothing else installed yet.

### 4. Install Debian inside proot-distro

```bash
proot-distro install debian
proot-distro login debian
```

You're now root inside a Debian arm64 rootfs. Everything from here until you `exit` runs there.

### 5. Clone the repo again, inside the distro, and install dependencies

(proot-distro's rootfs is its own filesystem - it doesn't automatically see Termux's `$HOME`, so clone fresh here.)

```bash
git clone https://github.com/Jivraj-18/wa-virtmic.git
cd wa-virtmic
bash scripts/install_termux.sh
```

This installs chromium (symlinked as `google-chrome`), PulseAudio, ffmpeg, the Python modules and Claude Code -
same idempotent pattern as `scripts/install.sh`, just arm64-flavored. Re-run any time; it skips what's already there.

### 6. LLM gateway settings

```bash
cp scripts/.env.example scripts/.env
# edit scripts/.env: set LLM_GATEWAY_BASE and LLM_GATEWAY_TOKEN
```

### 7. Start the GUI surface (Termux:X11)

The `termux-x11` command isn't installed yet - it comes from a separate Termux package, not just the
Termux:X11 app. From your Debian login (step 4-6), go back to plain Termux first:

```bash
exit
```

(this only leaves the proot-distro login shell - your files and the Debian rootfs are untouched). Then,
in Termux itself:

```bash
pkg install -y x11-repo
pkg install -y termux-x11-nightly
termux-x11 :0 &
```

Open the **Termux:X11** app - it connects to that `:0` display. You'll see a blank desktop; that's expected
until Chrome starts in a later step. You do **not** need a second Termux session for this: `termux-x11 :0 &`
stays running in the background of this same Termux shell even after you log back into the Debian proot on
top of it in the next step (`proot-distro login debian` runs the login as a child process - it doesn't
replace or kill this shell's background jobs). If you'd rather use a second session anyway, Termux's
left-edge drawer may be intercepted by Android's gesture navigation on some phones - the hamburger icon
in Termux's notification, or holding Volume Down and pressing N, also opens a new session on most devices.

### 8. Audio + Chrome, back in the Debian session

Switch back to the Debian login session from step 5:

```bash
export DISPLAY=:0
bash scripts/audio_setup.sh
bash scripts/test_virtmic.sh        # should print AUDIO PRESENT
bash scripts/launch_chrome.sh       # opens Chromium on Termux:X11, CDP on :9222
```

If `launch_chrome.sh` can't connect to the display, check that the X11 socket is visible inside the distro
(`ls /tmp/.X11-unix/`) - proot-distro normally shares Termux's `/tmp`, but this is the step most likely to
need a tweak on a given device/Termux version.

### 9. Run the demo

```bash
python3 scripts/doctor.py          # should be all PASS/WARN, no FAIL
bash scripts/demo.sh                # or: make demo, if you `apt install make`
```

Follow the same WhatsApp QR / Google Meet join flow as the Codespace README - just view it through
Termux:X11 (locally) or the tunnel below (remotely, e.g. to scan the QR with a *different* phone/camera
while this phone is the one running the stack).

### 10. "After" snapshot and compare

From a Termux session (not inside the proot login):

```bash
cd ~/wa-virtmic
bash scripts/measure_resources.sh after
bash scripts/measure_resources.sh diff
```

`diff` prints a unified diff of the two snapshots (memory, load average, top processes by RSS, disk usage,
and the Debian rootfs size) so you can see exactly what running the full stack costs on your phone.

### 11. View the desktop from anywhere (optional) - Cloudflare Tunnel

Only needed if you want to see the GUI on a different screen (e.g. to scan the WhatsApp QR with another
device's camera while this phone just runs headless). In the Debian session:

```bash
apt install -y x11vnc novnc
x11vnc -display :0 -nopw -forever -shared &
websockify -D 6080 localhost:5900
```

Then tunnel port 6080 publicly (no account needed for a quick tunnel):

```bash
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
cloudflared tunnel --url http://localhost:6080
```

It prints a `https://*.trycloudflare.com` URL - open `<that url>/vnc.html?autoconnect=true` in any browser,
anywhere. For a stable (non-random) URL instead of a fresh one each run, use a named tunnel with a free
Cloudflare account (`cloudflared tunnel login` / `create` / a `config.yml` route) - one-time extra setup.

### 12. Control it with Claude Code's Remote Control

Still in the Debian session, with Claude Code installed (step 5):

```bash
claude
# inside Claude Code:
/remote-control   # or: claude remote-control, depending on your Claude Code version
```

This registers the `~/wa-virtmic` folder on the phone as attachable. From then on, any Claude Code session
(including a cloud one at claude.ai/code) can attach to it and run `make demo`, read `auto_answer.log`,
restart the audio setup, edit files, etc. directly on the phone - no SSH needed. Use this for the "driving
it" half; Termux:X11/the tunnel above is for the "watching the Chrome window" half - you'll likely want both
at least for the first WhatsApp QR scan / Meet join.

## Keeping it alive in the background

Android aggressively kills idle background apps. Before closing the Termux app / turning the screen off:

```bash
termux-wake-lock          # needs the Termux:API app + `pkg install termux-api`
```

And in Android's own battery settings, disable battery optimization for Termux (Settings > Apps > Termux >
Battery > Unrestricted). `auto_answer.py`/`maya.py` are started with `nohup`/`setsid` so they survive the
login shell exiting, but the whole proot-distro process tree still dies if Android kills Termux itself.

## Troubleshooting

| Symptom | Likely fix |
|---|---|
| `playwright` import fails inside Debian | arm64 wheel/driver issue - the one step flagged as unverified; try `pip install --force-reinstall playwright` or check the Playwright GitHub issues for `linux-arm64` |
| Chrome "cannot open display" | `export DISPLAY=:0` not set, or `termux-x11 :0 &` not running, or the X11 socket isn't shared into the proot - check `ls /tmp/.X11-unix/` inside the distro |
| Termux/Debian processes die when the screen turns off | `termux-wake-lock`, disable battery optimization for Termux |
| `pip install` fails with "externally-managed-environment" | already handled by `install_termux.sh` (`--break-system-packages`); if calling pip by hand, add that flag |
| Want to start over cleanly | `proot-distro reset debian` (wipes only the distro, not Termux itself) |

## Isolation note

`proot-distro` is process/filesystem isolation via ptrace, not kernel namespaces - good enough to keep this
stack's dependencies and WhatsApp/Meet Chrome profiles contained and easy to wipe, but not a true security
boundary the way Docker or a VM is. Don't treat it as a sandbox against hostile code.
