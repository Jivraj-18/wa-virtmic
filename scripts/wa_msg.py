#!/usr/bin/env python3
"""Send a WhatsApp text message from the logged-in WhatsApp Web (CDP :9222). No screenshots, no UI search.

Usage:  python3 scripts/wa_msg.py "Some Name" "message text"     # contact name substring (must match ONE saved contact)
        python3 scripts/wa_msg.py 919876543210 "message text"     # or a number with country code
        python3 scripts/wa_msg.py "Some Name" --read [N]          # print the last N (default 8) messages, send nothing
Prints the chat name and the last message row afterwards, as proof it was sent.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from wa_call import open_chat, resolve, wa_page  # noqa: E402

ROWS_JS = "n => [...document.querySelectorAll('#main [role=row]')].slice(-n).map(r => r.innerText.replace(/\\n/g, ' '))"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    who, text = sys.argv[1], sys.argv[2]
    with sync_playwright() as pw:
        page = wa_page(pw.chromium.connect_over_cdp("http://localhost:9222"))
        page.set_default_timeout(30000)
        r = resolve(page, who)
        if r is None:
            return 2
        num, name = r
        if text == "--read":
            open_chat(page, num)
            page.wait_for_timeout(2000)
            for row in page.evaluate(ROWS_JS, int(sys.argv[3]) if len(sys.argv) > 3 else 8):
                print(row[:300])
            return 0
        open_chat(page, num, text)
        box = page.locator('#main footer [contenteditable="true"]').first
        box.wait_for()
        page.wait_for_timeout(1500)  # let the ?text= prefill land
        box.press("Enter")
        page.wait_for_timeout(3000)
        head = page.locator("#main header").first.inner_text().split("\n")[0]
        print(f"sent to {head} (+{num}); last row: {page.evaluate(ROWS_JS, 1)[0][:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
