#!/usr/bin/env python3
"""Log WhatsApp Web back in WITHOUT a QR scan: "link with phone number" -> 8-character code for the phone.

Chrome runs on an invisible Xvfb display (answer_daemon.sh), so nobody can see or scan the QR - and the phone
running this can't scan its own screen anyway. Instead:
    python3 scripts/wa_link.py 9198XXXXXXXX     # the WhatsApp account's number WITH country code -> prints the code
    python3 scripts/wa_link.py --code           # print the code currently shown (it ROTATES every few minutes)
Then on the phone: WhatsApp -> ⋮ -> Linked devices -> Link a device -> Link with phone number instead -> type it.
If the phone says "Incorrect code", it expired: run --code again and give the user the new one immediately.
"""
import re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from playwright.sync_api import sync_playwright  # noqa: E402
from wa_call import wa_page  # noqa: E402

CLICK_JS = """t => { const e = [...document.querySelectorAll('div,span,a,button')]
  .filter(x => x.children.length === 0 && (x.innerText || '').trim().replace(/\\.$/, '') === t);
  e.forEach(x => x.click()); return e.length; }"""  # JS click: the link is often outside the Xvfb viewport


def current_code(page):
    t = page.evaluate("document.body.innerText")
    if "Enter code on phone" not in t:
        return None
    m = re.search(r"Enter code on phone.*?\(edit\)\s*((?:\S\s*){4}-\s*(?:\S\s*){4})", t, re.S)
    return re.sub(r"\s", "", m.group(1)) if m else None


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    with sync_playwright() as pw:
        page = wa_page(pw.chromium.connect_over_cdp("http://localhost:9222"))
        page.set_default_timeout(30000)
        if page.evaluate("!!document.querySelector('#pane-side')"):
            print("already logged in (chat list visible) - nothing to do")
            return 0
        if arg == "--code":
            print(current_code(page) or "no code on screen - run with the phone number first")
            return 0
        digits = re.sub(r"\D", "", arg)
        if len(digits) < 11:
            print(__doc__)
            return 1
        if not current_code(page):
            if not page.evaluate(CLICK_JS, "Link with phone number instead"):
                print("couldn't find 'Link with phone number instead' - page text:",
                      page.evaluate("document.body.innerText")[:300])
                return 3
            page.wait_for_timeout(3000)
            inp = page.locator('input[aria-label*="phone number" i]').first
            cc = re.sub(r"\D", "", inp.input_value())  # prefilled country code, e.g. '+91 ' (from the IP)
            if cc and digits.startswith(cc):           # what worked: keep the prefix, type the rest
                inp.focus(); inp.press("End"); inp.press_sequentially(digits[len(cc):], delay=60)
            else:
                inp.fill("+" + digits)
            page.wait_for_timeout(500)
            page.evaluate(CLICK_JS, "Next")
            for _ in range(30):
                page.wait_for_timeout(1000)
                if current_code(page):
                    break
        code = current_code(page)
        print(f"CODE: {code}" if code else "no code appeared - page text: " + page.evaluate("document.body.innerText")[:300])
        return 0 if code else 3


if __name__ == "__main__":
    sys.exit(main())
