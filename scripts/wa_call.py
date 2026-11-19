#!/usr/bin/env python3
"""Place an outgoing WhatsApp voice call from the logged-in WhatsApp Web (CDP :9222) and let the live AI talk.

Usage:  python3 scripts/wa_call.py "Some Name"          # contact name (substring, case-insensitive)
        python3 scripts/wa_call.py 919876543210          # or a number with country code, digits only
        python3 scripts/wa_call.py --lookup ritik        # just print matching contacts + numbers, no call

No UI searching: names are resolved from WhatsApp Web's own local contact store (IndexedDB 'model-storage'
-> 'contact'), and the chat is opened with web.whatsapp.com/send?phone=<number>. The agent starts silent and
answers once the callee speaks, so it doesn't talk over the ringing. Recording/transcripts: same as
auto_answer.py (scripts/calls/<ts>/).
"""
import argparse, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from playwright.sync_api import sync_playwright  # noqa: E402

LOOKUP_JS = r"""async (q) => {
  const db = await new Promise((res, rej) => { const r = indexedDB.open('model-storage'); r.onsuccess = () => res(r.result); r.onerror = rej; });
  const all = await new Promise(res => { const r = db.transaction('contact').objectStore('contact').getAll(); r.onsuccess = () => res(r.result); });
  const out = {};
  for (const c of all) {
    const name = c.name || c.shortName || c.pushname || c.verifiedName || '';
    const num = ((c.phoneNumber || '').match(/^(\d+)@c\.us$/) || (String(c.id).match(/^(\d+)@(c\.us|s\.whatsapp\.net)$/)) || [])[1];
    if (num && name.toLowerCase().includes(q.toLowerCase()) && !out[num]) out[num] = {name, saved: !!c.name};
  }
  return Object.entries(out).map(([num, v]) => ({num, ...v}));
}"""


def wa_page(browser):
    for ctx in browser.contexts:
        for p in ctx.pages:
            if "web.whatsapp.com" in p.url:
                return p
    raise SystemExit("no web.whatsapp.com tab found (is Chrome running? bash scripts/launch_chrome.sh)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("who", help="contact name substring, or a phone number with country code")
    ap.add_argument("--lookup", action="store_true", help="only list matching contacts, don't call")
    ap.add_argument("--max", type=int, default=600, help="max call seconds (default 600)")
    ap.add_argument("--brief", default="", help="extra instructions for this call (purpose, message to pass on)")
    a = ap.parse_args()

    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp("http://localhost:9222")
        page = wa_page(b)
        page.set_default_timeout(30000)
        digits = re.sub(r"\D", "", a.who)
        if len(digits) >= 10 and len(digits) == len(re.sub(r"[\s+\-()]", "", a.who)):
            num, name = digits, a.who
        else:
            hits = page.evaluate(LOOKUP_JS, a.who)
            saved = [h for h in hits if h["saved"]] or hits
            if a.lookup or len(saved) != 1:
                for h in hits:
                    print(f"{h['num']}  {h['name']}{'' if h['saved'] else '  (not in address book)'}")
                if not a.lookup:
                    print(f"\n{len(saved)} saved matches for {a.who!r} - be more specific, or pass the number.")
                return 0 if a.lookup else 2
            num, name = saved[0]["num"], saved[0]["name"]
        if a.lookup:
            print(num, name)
            return 0

        import auto_answer as aa  # heavy imports only when actually calling
        # Without this WhatsApp shows "Allow microphone" and the call never starts (stuck at "Connecting").
        b.new_browser_cdp_session().send("Browser.grantPermissions",
                                         {"origin": aa.ORIGIN, "permissions": ["audioCapture"]})
        aa.log(f"opening chat for {name} (+{num})")
        page.goto(f"https://web.whatsapp.com/send?phone={num}", wait_until="domcontentloaded")
        btn = page.locator('#main header [aria-label="Voice call"]').first
        btn.wait_for(timeout=90000)  # WhatsApp Web reloads; on a phone this takes a while
        btn.click()
        aa.log(f"dialing {name} (+{num}) - agent waits for them to speak first")
        time.sleep(2)
        aa.handle_call(page, str(aa.HERE / "greeting.wav"), a.max, "realtime", None, name, speak_first=False,
                       extra_instructions="\nThis is an OUTGOING call you placed. Wait for the other person to "
                                          "say hello, then introduce yourself briefly. Ignore ringing tones."
                                          + (f"\nCall brief: {a.brief}" if a.brief else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
