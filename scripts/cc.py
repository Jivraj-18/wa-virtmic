#!/usr/bin/env python
"""Call-center desk for the AI's back-office helper (Claude Code), scoped to the person on the CURRENT call.

Claude runs these during (and right after) a WhatsApp call; CC_CALL_DIR names the call folder, whose call_meta.json
says who is on the line. Every command acts on THAT person only (callers are strangers: they can't make it read or
message anyone else). Nothing here navigates WhatsApp Web, so it is safe while the call is live (wa_store.py).

    python scripts/cc.py who                 # caller card: name, number, past calls, notes, open reminders
    python scripts/cc.py chat [N]            # their last N WhatsApp messages (default 15)
    python scripts/cc.py photo [K]           # download the K-th latest photo/document they sent -> prints the path
    python scripts/cc.py send "text"         # WhatsApp message to the caller (confirmations, summaries, links)
    python scripts/cc.py calls [N]           # their last N calls with us: date, length, how it went
    python scripts/cc.py transcript          # this call so far
    python scripts/cc.py note "text"         # remember something about this person (read at their next call)
    python scripts/cc.py remind WHEN "text"  # WhatsApp reminder to the caller later: +30m, +2h, 18:30, 2026-11-25 09:00
    python scripts/cc.py escalate "text"     # message for the owner (a human) - complaints, call-back requests, money
    python scripts/cc.py status              # is the call still live?
    python scripts/cc.py due                 # (supervisor) send reminders that are due; needs no call
"""
import json, os, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CALLS = HERE / "calls"
PEOPLE = HERE / "contacts"          # per-person notes + reminders (personal data: git-ignored)
REMINDERS = PEOPLE / "reminders.jsonl"


def _page(pw):
    import wa_store
    return wa_store.wa_page(pw.chromium.connect_over_cdp("http://localhost:9222"))


def call_dir():
    d = os.environ.get("CC_CALL_DIR")
    if not d or not (Path(d) / "call_meta.json").exists():
        sys.exit("no current call (CC_CALL_DIR / call_meta.json missing)")
    return Path(d)


def meta(d=None):
    return json.loads(((d or call_dir()) / "call_meta.json").read_text())


def person_dir(num):
    p = PEOPLE / re.sub(r"\D", "", str(num))
    p.mkdir(parents=True, exist_ok=True)
    return p


def past_calls(num, n=5, skip=None):
    out = []
    for d in sorted(CALLS.glob("2*"), reverse=True):
        if d == skip:
            continue
        try:
            m = json.loads((d / "call_meta.json").read_text())
        except Exception:
            continue
        if re.sub(r"\D", "", str(m.get("num", ""))) != re.sub(r"\D", "", str(num)):
            continue
        tr = (d / "transcript_live.txt").read_text(errors="replace").splitlines() if (d / "transcript_live.txt").exists() else []
        last = tr[-1][:9].strip("[] ") if tr else "?"
        out.append({"dir": d, "when": time.strftime("%d %b %H:%M", time.strptime(d.name, "%Y%m%d_%H%M%S")),
                    "dir_": m.get("direction", "?"), "len": last, "summary": m.get("summary", ""), "lines": tr})
        if len(out) >= n:
            break
    return out


def card(num, name="", skip=None, chat_lines=None):
    """Short text about this person for the voice model's instructions (no LLM, fast)."""
    p = person_dir(num)
    notes = (p / "notes.md").read_text().strip() if (p / "notes.md").exists() else ""
    calls = past_calls(num, 3, skip)
    rem = [r for r in _reminders() if r["num"] == re.sub(r"\D", "", str(num)) and not r.get("sent")]
    s = [f"Caller: {name or 'not a saved contact'} (WhatsApp +{num})."]
    if calls:
        s.append("Earlier calls with them: " + "; ".join(
            f"{c['when']} ({c['dir_']}, {c['len']})" + (f": {c['summary']}" if c["summary"] else "") for c in calls))
    else:
        s.append("First call with them as far as our records go.")
    if notes:
        s.append("Notes about them:\n" + notes[-1200:])
    if rem:
        s.append("Open reminders for them: " + "; ".join(f"{r['when_text']}: {r['text']}" for r in rem))
    if chat_lines:
        s.append("Their latest WhatsApp chat lines:\n" + "\n".join(chat_lines[-6:]))
    return "\n".join(s)


def _reminders():
    if not REMINDERS.exists():
        return []
    return [json.loads(l) for l in REMINDERS.read_text().splitlines() if l.strip()]


def _parse_when(w):
    now = time.time()
    m = re.fullmatch(r"\+(\d+)\s*([mhd])", w.strip())
    if m:
        return now + int(m.group(1)) * {"m": 60, "h": 3600, "d": 86400}[m.group(2)]
    for fmt in ("%Y-%m-%d %H:%M", "%H:%M"):
        try:
            t = time.strptime(w.strip(), fmt)
        except ValueError:
            continue
        if fmt == "%H:%M":
            lt = time.localtime()
            ts = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, t.tm_hour, t.tm_min, 0, 0, 0, -1))
            return ts + 86400 if ts < now else ts
        return time.mktime(t)
    sys.exit(f"can't read the time {w!r}: use +30m, +2h, +1d, 18:30 or 2026-11-25 09:00")


def _fmt_msgs(r):
    out = []
    for m in r["msgs"]:
        when = time.strftime("%d %b %H:%M", time.localtime(m["t"]))
        who = "us" if m["who"] == "me" else (r["name"] or "them")
        what = m["body"] if m["type"] == "chat" else f"[{m['type']}{' ' + m['mimetype'] if m['mimetype'] else ''}]" + (f" {m['body']}" if m["body"] else "")
        if m["type"] in ("call_log", "e2e_notification", "notification_template", "gp2"):
            continue
        out.append(f"{when} {who}: {what}")
    return out


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "who"
    args = argv[2:]
    if cmd == "due" and not any(not r.get("sent") and r["due"] <= time.time() for r in _reminders()):
        return 0   # the supervisor runs this every ~20 s: stay cheap when nothing is due
    from playwright.sync_api import sync_playwright
    import wa_store
    if cmd == "due":
        rs, changed = _reminders(), False
        due = [r for r in rs if not r.get("sent") and r["due"] <= time.time()]
        if not due:
            return 0
        with sync_playwright() as pw:
            page = _page(pw)
            for r in due:
                wa_store.send(page, r["num"], r["text"] if r["text"].lower().startswith("reminder") else f"Reminder: {r['text']}")
                r["sent"] = time.time(); changed = True
                print(f"sent reminder to +{r['num']}: {r['text']}")
        if changed:
            REMINDERS.write_text("".join(json.dumps(r) + "\n" for r in rs))
        return 0

    d = call_dir(); m = meta(d); num, name = m.get("num"), m.get("name") or m.get("caller") or ""
    if not num:
        sys.exit("the caller's number is unknown for this call")
    log = lambda s: open(d / "desk.log", "a").write(time.strftime("%H:%M:%S ") + s + "\n")
    if cmd == "status":
        print("call ENDED - the caller can't hear you; use send for anything they still need" if (d / "ended").exists()
              else "call is LIVE")
    elif cmd == "transcript":
        p = d / "transcript_live.txt"
        print(p.read_text()[-6000:] if p.exists() else "(nothing yet)")
    elif cmd == "calls":
        for c in past_calls(num, int(args[0]) if args else 5, skip=d):
            print(f"{c['when']} {c['dir_']} call, {c['len']}" + (f" - {c['summary']}" if c["summary"] else ""))
            for ln in c["lines"][:3] + (["..."] if len(c["lines"]) > 6 else []) + c["lines"][-3:]:
                print("    " + ln[:200])
        print("(no earlier calls)" if not past_calls(num, 1, skip=d) else "")
    elif cmd == "note":
        text = " ".join(args).strip()
        if not text:
            sys.exit("note: nothing to save")
        with open(person_dir(num) / "notes.md", "a") as f:
            f.write(f"- {time.strftime('%d %b %Y')}: {text}\n")
        log(f"note: {text}"); print("saved")
    elif cmd == "remind":
        if len(args) < 2:
            sys.exit('usage: remind WHEN "text"')
        due = _parse_when(args[0]); text = " ".join(args[1:])
        PEOPLE.mkdir(parents=True, exist_ok=True)
        with open(REMINDERS, "a") as f:
            f.write(json.dumps({"num": re.sub(r"\D", "", num), "due": due, "text": text, "when_text":
                                time.strftime("%a %d %b %H:%M", time.localtime(due)), "call": d.name}) + "\n")
        log(f"remind {args[0]}: {text}")
        print(f"reminder set for {time.strftime('%a %d %b %H:%M', time.localtime(due))} (sent on WhatsApp)")
    else:
        with sync_playwright() as pw:
            page = _page(pw)
            if cmd == "who":
                r = wa_store.read(page, num, 8)
                print(card(num, name or r["name"], skip=d, chat_lines=_fmt_msgs(r)))
            elif cmd == "chat":
                r = wa_store.read(page, num, int(args[0]) if args else 15)
                print("\n".join(_fmt_msgs(r)) or "(no messages)")
            elif cmd == "send":
                text = " ".join(args).strip()
                if not text:
                    sys.exit("send: empty message")
                wa_store.send(page, num, text); log(f"sent to caller: {text}"); print("sent on WhatsApp")
            elif cmd == "escalate":
                text = " ".join(args).strip()
                owner = wa_store.me(page)
                wa_store.send(page, owner, f"[AI desk] {name or '+' + num} (+{num}): {text}")
                log(f"escalated: {text}"); print("the owner has been messaged")
            elif cmd == "photo":
                k = int(args[0]) if args else 1
                r = wa_store.read(page, num, 60)
                media = [x for x in r["msgs"] if x["media"] and x["who"] == "them"]
                if len(media) < k:
                    print("(they haven't sent a photo or file in the recent chat)"); return 0
                x = media[-k]
                b, mt = wa_store.media(page, num, x["id"])
                ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}.get(
                    mt.split(";")[0], "bin")
                out = d / f"media_{k}.{ext}"; out.write_bytes(b)
                log(f"photo -> {out.name}")
                print(f"{out} ({mt}, {len(b) // 1024} KB, sent {time.strftime('%d %b %H:%M', time.localtime(x['t']))}"
                      + (f', caption "{x["body"]}"' if x["body"] else "") + ") - open it with the Read tool")
            else:
                print(__doc__); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
