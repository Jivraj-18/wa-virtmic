"""Log Nova's Chrome (CDP 9333, profile ~/.config/maya-chrome-profile) into a Google account, text only.

    python scripts/nova/google_login.py start <email>      # types the email, then reads the password from STDIN
    python scripts/nova/google_login.py code <digits>      # answer a 2FA / verification-code prompt
    python scripts/nova/google_login.py page               # what the login tab shows now (text + buttons)
    python scripts/nova/google_login.py click "<button>"   # click a button by its visible name (e.g. "Try another way")

The password is NEVER stored: pass it on stdin (`read -rs P; printf %s "$P" | ... start <email>; unset P`), the
Chrome profile keeps the session afterwards. After every step the script prints the page heading/text so the next
step (2FA, "Verify it's you", "this browser may not be secure") can be decided without a screenshot.
"""
import asyncio, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meet import browser as B  # noqa: E402

SIGNIN = "https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fmyaccount.google.com%2F"
TEXT_JS = r"""() => {
  const vis = e => e.offsetParent !== null;
  const btns = [...document.querySelectorAll('button,[role=button],a[role=link]')].filter(vis)
    .map(e => (e.innerText || e.getAttribute('aria-label') || '').trim()).filter(Boolean).slice(0, 25);
  const inputs = [...document.querySelectorAll('input')].filter(vis)
    .map(e => `${e.type}:${e.name || e.id || e.getAttribute('aria-label') || ''}`);
  return {url: location.href.slice(0, 120), title: document.title,
          text: (document.body.innerText || '').replace(/\n{2,}/g, '\n').slice(0, 1500), btns, inputs};
}"""


async def _page(ctx):
    for p in ctx.pages:
        if p.url.startswith(("https://accounts.google.com", "https://myaccount.google.com")):
            return p
    return await ctx.new_page()


async def show(page, wait=2500):
    await page.wait_for_timeout(wait)
    r = await page.evaluate(TEXT_JS)
    print(f"URL: {r['url']}\nTITLE: {r['title']}\nINPUTS: {r['inputs']}\nBUTTONS: {r['btns']}\n--- TEXT ---\n{r['text']}")
    if r["url"].startswith("https://myaccount.google.com"):
        print("\nRESULT: LOGGED IN")
    return r


async def _next(page):
    for name in ("Next", "Continue", "Verify", "Sign in"):
        loc = page.get_by_role("button", name=re.compile(rf"^{name}$", re.I))
        if await loc.count() and await loc.first.is_visible():
            await loc.first.click()
            return True
    await page.keyboard.press("Enter")
    return False


async def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "page"
    B.devices_up()
    B.launch_chrome("about:blank")
    pw, browser, ctx = await B.connect()
    try:
        page = await _page(ctx)
        if cmd == "start":
            email = sys.argv[2]
            password = sys.stdin.readline().rstrip("\n")
            if not password:
                raise SystemExit("password expected on stdin")
            await page.goto(SIGNIN, wait_until="load")
            await page.wait_for_timeout(2000)
            if page.url.startswith("https://myaccount.google.com"):
                await show(page, 0); return
            box = page.locator('input[type=email], input[name=identifier]')
            if await box.count() and await box.first.is_visible():
                await box.first.fill(email)
                await _next(page)
            pwbox = page.locator('input[type=password]:visible')
            try:
                await pwbox.first.wait_for(state="visible", timeout=15000)
            except Exception:
                print("password field did not appear - the page says:")
                await show(page, 0); return
            await pwbox.first.fill(password)
            password = None
            await _next(page)
            await show(page, 5000)
        elif cmd == "code":
            box = page.locator('input[type=tel]:visible, input[type=text]:visible, input[type=number]:visible')
            await box.first.fill(sys.argv[2])
            await _next(page)
            await show(page, 5000)
        elif cmd == "click":
            await page.get_by_text(sys.argv[2], exact=False).first.click()
            await show(page, 3000)
        else:
            await show(page, 0)
    finally:
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
