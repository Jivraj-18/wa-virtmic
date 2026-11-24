"""Calendar -> Meet autojoin for Nova (Google Calendar read through the gws CLI; no browser involved).

Which events Nova joins (config ~/.config/nova/autojoin.json, outside the repo; all keys optional):
    {"mode": "tagged",        # "tagged": only events whose title/description has the keyword, or that invite
                              #           one of "accounts" (use this while gws is on a PERSONAL calendar)
                              # "all":    every event with a Meet link that isn't declined (Nova's own account)
     "keyword": "nova",
     "accounts": [],          # e.g. Nova's own address once it exists: events inviting it are joined
     "lead_s": 60,            # join this many seconds before the start
     "grace_end_min": 10,     # leave at the latest this long after the scheduled end
     "calendar": "primary"}
Calendar text is untrusted data: it is only matched against the Meet-link regex and the keyword, never obeyed.
"""
import json, os, re, subprocess, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONF = Path.home() / ".config" / "nova" / "autojoin.json"
STATE_DIR = Path(os.environ.get("NOVA_STATE_DIR", str(Path.home() / ".cache" / "nova")))
JOINED = STATE_DIR / "autojoined.json"
HEARTBEAT = STATE_DIR / "autojoin.heartbeat"
MEET = re.compile(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}")
DEFAULTS = {"mode": "tagged", "keyword": "nova", "accounts": [], "lead_s": 60, "grace_end_min": 10,
            "calendar": "primary"}


def conf() -> dict:
    c = dict(DEFAULTS)
    try:
        c.update(json.loads(CONF.read_text()))
    except FileNotFoundError:
        pass
    return c


def gws(*args, timeout=60) -> dict:
    env = dict(os.environ, GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=os.environ.get("GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND", "file"))
    exe = os.environ.get("GWS", str(Path.home() / ".local" / "bin" / "gws"))
    r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()
        raise RuntimeError("gws failed: " + " | ".join(msg[-3:])[:400])
    out = r.stdout.strip()
    return json.loads(out) if out.startswith("{") else {"raw": out}


def _ts(d: dict) -> float:
    s = d.get("dateTime") or d.get("date")
    if not s:
        return 0.0
    if "T" not in s:  # all-day event
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def meet_link(ev: dict):
    if ev.get("hangoutLink"):
        return ev["hangoutLink"]
    for ep in (ev.get("conferenceData") or {}).get("entryPoints", []):
        if ep.get("entryPointType") == "video" and "meet.google.com" in ep.get("uri", ""):
            return ep["uri"]
    m = MEET.search((ev.get("location") or "") + " " + (ev.get("description") or ""))
    return m.group(0) if m else None


def events(hours=24, back_hours=2, c=None) -> list:
    c = c or conf()
    now = datetime.now(timezone.utc)
    params = {"calendarId": c["calendar"], "singleEvents": True, "orderBy": "startTime", "maxResults": 50,
              "timeMin": (now - timedelta(hours=back_hours)).isoformat(), "timeMax": (now + timedelta(hours=hours)).isoformat()}
    data = gws("calendar", "events", "list", "--params", json.dumps(params))
    out = []
    for ev in data.get("items", []):
        link = meet_link(ev)
        if not link or ev.get("status") == "cancelled":
            continue
        me = next((x for x in ev.get("attendees", []) if x.get("self")), {})
        out.append({"id": ev["id"], "title": (ev.get("summary") or "(no title)")[:120], "link": link,
                    "start": _ts(ev["start"]), "end": _ts(ev["end"]), "response": me.get("responseStatus", "owner"),
                    "organizer": (ev.get("organizer") or {}).get("email", ""),
                    "attendees": [x.get("email", "") for x in ev.get("attendees", [])],
                    "text": ((ev.get("summary") or "") + " " + (ev.get("description") or "")).lower()})
    return out


def wanted(e: dict, c: dict) -> tuple:
    if e["response"] == "declined":
        return False, "declined"
    if c["mode"] == "all":
        return True, "mode=all"
    if re.search(rf"\b{re.escape(c['keyword'].lower())}\b", e["text"]):
        return True, f"tagged '{c['keyword']}'"
    if set(a.lower() for a in c["accounts"]) & set(a.lower() for a in e["attendees"]):
        return True, "invites Nova's account"
    return False, f"not tagged (mode=tagged: put '{c['keyword']}' in the title/description)"


def upcoming(hours=24) -> list:
    c = conf()
    now = time.time()
    evs = [e for e in events(hours=hours, back_hours=4, c=c) if e["end"] > now]
    for e in evs:
        e["join"], e["why"] = wanted(e, c)
    return evs


def fmt(e) -> str:
    st = time.strftime("%a %H:%M", time.localtime(e["start"]))
    en = time.strftime("%H:%M", time.localtime(e["end"]))
    flag = "JOIN" if e.get("join") else "skip"
    return f"{st}-{en}  {flag:4}  {e['title']}  {e['link']}  [{e['response']}; {e.get('why', '')}]"


def _joined() -> dict:
    try:
        return json.loads(JOINED.read_text())
    except Exception:
        return {}


def loop(once=False, start_join=None, busy=None, refresh_s=180, tick_s=15):
    """Poll Calendar every `refresh_s`, check timing every `tick_s`. Join each wanted event once (3 tries)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    evs, fetched, err = [], 0.0, ""
    while True:
        c = conf()
        now = time.time()
        if now - fetched > refresh_s:
            try:
                evs, err = events(hours=12, back_hours=4, c=c), ""
                fetched = now
            except Exception as e:
                err = str(e)[:200]
                fetched = now - refresh_s + 60   # retry in a minute
                print(time.strftime("%T"), "calendar error:", err, flush=True)
        done = _joined()
        nxt = None
        for e in evs:
            key = f"{e['id']}@{int(e['start'])}"
            ok, why = wanted(e, c)
            if not ok or e["end"] + 60 < now:
                continue
            tries = done.get(key, {}).get("tries", 0)
            if done.get(key, {}).get("ok") or tries >= 3:
                continue
            if now >= e["start"] - c["lead_s"]:
                if busy and busy():
                    continue   # one meeting at a time
                print(time.strftime("%T"), f"joining '{e['title']}' ({why})", flush=True)
                rc = start_join(e["link"], until=e["end"] + 60 * c["grace_end_min"], event=e["id"], title=e["title"])
                done[key] = {"tries": tries + 1, "ok": rc == 0, "t": now, "title": e["title"]}
                JOINED.write_text(json.dumps(done, indent=1))
            elif nxt is None or e["start"] < nxt["start"]:
                nxt = e
        hb = f"ok {time.strftime('%T')} events={len(evs)}"
        if nxt:
            hb += f" next='{nxt['title']}' at {time.strftime('%a %H:%M', time.localtime(nxt['start']))}"
        if err:
            hb += f" ERROR: {err}"
        HEARTBEAT.write_text(hb + "\n")
        if once:
            print(hb)
            return 0
        time.sleep(tick_s)
