#!/usr/bin/env python3
"""Inspect the WhatsApp tab via CDP (port 9222). Usage: cdp_eval.py [status|console SECONDS|js EXPR]"""
import sys
from playwright.sync_api import sync_playwright

def wa_page(browser):
    for ctx in browser.contexts:
        for p in ctx.pages:
            if "web.whatsapp.com" in p.url:
                return p
    raise SystemExit("no web.whatsapp.com tab found")

STATUS_JS = """() => ({
  title: document.title,
  qr: !!document.querySelector('[aria-label*="QR code" i]'),
  loading: document.body.innerText.includes('Loading your chats'),
  chatList: !!document.querySelector('#pane-side, [aria-label="Chat list"], div[role="grid"]'),
  chats: document.querySelectorAll('#pane-side [role="listitem"], #pane-side [role="row"]').length,
})"""

with sync_playwright() as pw:
    b = pw.chromium.connect_over_cdp("http://localhost:9222")
    page = wa_page(b)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        print(page.url, page.evaluate(STATUS_JS))
    elif cmd == "js":
        print(page.evaluate(sys.argv[2]))
    elif cmd == "console":
        secs = float(sys.argv[2]) if len(sys.argv) > 2 else 15
        page.on("console", lambda m: print(f"[{m.type}] {m.text}"))
        page.wait_for_timeout(secs * 1000)
