"""Headless smoke test of Maya's Chrome launch + Meet page control against a local mock page (no Google, no :1).

  python3 tests/test_meet_browser.py
Uses a temp profile and CDP port 9334; never touches port 9222 or the WhatsApp devices.
"""
import asyncio, os, signal, sys, tempfile, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from meet import browser as B

PORT = 9334


async def main():
    with tempfile.TemporaryDirectory() as prof:
        proc = B.launch_chrome("about:blank", port=PORT, profile=prof, headless=True)
        try:
            assert B.chrome_pids(PORT) and os.getpid() not in B.chrome_pids(PORT)
            pw, browser, ctx = await B.connect(PORT)
            page = await B.meet_page(ctx)
            url = (pathlib.Path(__file__).parent / "meet_mock.html").resolve().as_uri()
            assert await B.join_meet(page, url, name="Maya", lobby_timeout=10, log=lambda *a: None) == "joined"
            log = await page.evaluate("window.log")
            assert log == ["cam_off", "mic_on", "join:Maya"], log
            assert await B.in_meeting(page)
            assert await B.send_chat(page, "Maybe consider a pilot first.", log=lambda *a: None)
            assert await B.send_chat(page, "Second tip.", log=lambda *a: None)
            assert await page.evaluate("window.sent") == ["Maybe consider a pilot first.", "Second tip."]
            assert any("leave call" in ln.lower() for ln in await B.probe(page))
            await B.leave_meet(page)
            assert (await page.evaluate("window.log"))[-1] == "left"
            await pw.stop()
        finally:
            if proc:
                os.killpg(proc.pid, signal.SIGTERM); proc.wait(10)
    try:
        B._check_port(9222); raise AssertionError("9222 must be refused")
    except SystemExit:
        pass
    # devices with a throwaway prefix (never the WhatsApp ones)
    B.devices_up("mayatest")
    names = B._names("sinks") | B._names("sources")
    assert {"mayatest_out", "mayatest_mic_sink", "mayatest_mic"} <= names, names
    B.devices_down("mayatest")
    names = B._names("sinks") | B._names("sources")
    assert not any(n.startswith("mayatest") for n in names), names
    assert {"virtmic_sink", "callout_sink"} <= B._names("sinks")
    print("browser/devices: all tests passed")


if __name__ == "__main__":
    asyncio.run(main())
