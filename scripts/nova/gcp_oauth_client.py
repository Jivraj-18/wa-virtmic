"""Create the gws OAuth setup in a Cloud project from Nova's Chrome (the one step gcloud can't do), text only.

    python scripts/nova/gcp_oauth_client.py <project-id> <account-email>
Does: Google Auth Platform branding (app "Nova gws", External, Testing), adds <account-email> as test user,
creates a Desktop OAuth client "gws-termux" and writes ~/.config/gws/client_secret.json (mode 600).
gcloud does the rest (login, `gcloud services enable ...`): see the nova-gws skill. Prereq: Nova's Chrome is
signed in to <account-email> (scripts/nova/google_login.py). Prints each page's text; safe to re-run (skips steps
already done). The console DOM changes: if a step fails, `python scripts/nova/web.py text` shows the page.
"""
import asyncio, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from meet import browser as B  # noqa: E402

C = "https://console.cloud.google.com"


async def wait_text(page, rx, timeout=60):
    for _ in range(int(timeout / 2)):
        t = await page.evaluate("() => document.body.innerText")
        if re.search(rx, t, re.I):
            return t
        await page.wait_for_timeout(2000)
    raise RuntimeError(f"timeout waiting for /{rx}/; page says: {t[-600:]}")


async def click(page, name, role="button", exact=True):
    rx = re.compile(rf"^\s*{re.escape(name)}\s*$", re.I) if exact else re.compile(re.escape(name), re.I)
    for loc in (page.get_by_role(role, name=rx), page.get_by_role("link", name=rx), page.get_by_text(rx)):
        try:
            if await loc.count() and await loc.first.is_visible():
                await loc.first.click(timeout=15000)
                break
        except Exception:
            continue
    else:
        raise RuntimeError(f"no clickable {name!r}; page: {(await page.evaluate('() => document.body.innerText'))[-500:]}")
    await page.wait_for_timeout(1500)


async def branding(page, email):
    await page.goto(f"{C}/auth/overview?project={PROJECT}", wait_until="domcontentloaded")
    t = await wait_text(page, r"Get started|Create OAuth client|Metrics|OAuth Overview")
    if "not configured yet" not in t and "Create branding" not in t:
        print("branding: already configured"); return
    if "Create branding" not in t:
        await click(page, "Get started")
        await wait_text(page, r"App name")
    await page.locator('input[formcontrolname="displayName"]').fill("Nova gws")
    await page.locator('cfc-select[formcontrolname="userSupportEmail"]').click()
    await page.wait_for_timeout(1000)
    await page.get_by_role("option", name=re.compile(re.escape(email), re.I)).first.click()
    await click(page, "Next")
    await page.locator('input[type=radio][value="external"]').check(force=True)
    await click(page, "Next")
    box = page.get_by_label("Text field for emails")
    await box.fill(email); await box.press("Enter")
    await click(page, "Next")
    await page.locator('input[type=checkbox]').last.check(force=True)
    await click(page, "Continue") if await page.get_by_role("button", name=re.compile("^continue$", re.I)).count() else None
    await click(page, "Create")
    await wait_text(page, r"Create OAuth client|Metrics|OAuth Overview|Clients", 90)
    print("branding: created (External, Testing)")


async def test_user(page, email):
    await page.goto(f"{C}/auth/audience?project={PROJECT}", wait_until="domcontentloaded")
    t = await wait_text(page, r"Test users")
    if email.lower() in t.lower():
        print("test user: already there"); return
    await click(page, "Add users")
    await page.wait_for_timeout(1500)
    box = page.locator('[role=dialog] input[aria-label="Text field for emails"], [role=dialog] input[type=email], '
                       'cfc-dialog input, mat-dialog-container input, input[aria-label="Text field for emails"]').last
    await box.fill(email); await box.press("Enter")
    await page.wait_for_timeout(800)
    await click(page, "Save")
    await wait_text(page, re.escape(email), 30)
    print("test user: added")


async def client(page):
    out = Path.home() / ".config" / "gws" / "client_secret.json"
    if out.exists():
        print(f"client: {out} exists - delete it to create a new one"); return
    await page.goto(f"{C}/auth/clients/create?project={PROJECT}", wait_until="domcontentloaded")
    await wait_text(page, r"Application type")
    await page.get_by_role("combobox").first.click()
    await page.wait_for_timeout(800)
    await page.get_by_role("option", name=re.compile(r"^\s*Desktop app", re.I)).first.click()
    await page.wait_for_timeout(800)
    name = page.locator('input[formcontrolname="displayName"], input[aria-label*="Name" i]').first
    await name.fill("gws-termux")
    await click(page, "Create")
    t = await wait_text(page, r"Client secret|OAuth client created", 60)
    ids = re.findall(r"[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com", t)
    secrets = re.findall(r"GOCSPX-[A-Za-z0-9_-]+", t)
    if not ids or not secrets:
        # values may sit in inputs / copy buttons rather than text
        vals = await page.evaluate("""() => [...document.querySelectorAll('input,[cdkcopytoclipboard],[data-value]')]
            .map(e => e.value || e.getAttribute('cdkcopytoclipboard') || e.getAttribute('data-value') || '')""")
        ids = ids or [v for v in vals if v.endswith(".apps.googleusercontent.com")]
        secrets = secrets or [v for v in vals if v.startswith("GOCSPX-")]
    if not ids or not secrets:
        raise RuntimeError("client created but id/secret not found on the page (see `web.py text --all`)")
    out.parent.mkdir(parents=True, exist_ok=True); os.chmod(out.parent, 0o700)
    out.write_text(json.dumps({"installed": {
        "client_id": ids[0], "client_secret": secrets[0], "project_id": PROJECT,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "redirect_uris": ["http://localhost"]}}))
    os.chmod(out, 0o600)
    print(f"client: created, saved to {out} (id ...{ids[0][-30:]})")
    await click(page, "OK") if await page.get_by_role("button", name=re.compile("^ok$", re.I)).count() else None


async def main():
    global PROJECT
    PROJECT, email = sys.argv[1], sys.argv[2]
    pw, br, ctx = await B.connect()
    page = await ctx.new_page()
    try:
        for step in (lambda: branding(page, email), lambda: test_user(page, email), lambda: client(page)):
            await step()
    finally:
        await page.close()
        await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
