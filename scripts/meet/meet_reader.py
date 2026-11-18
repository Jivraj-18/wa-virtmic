"""Read Google Meet's own live captions (who said what) and the meeting chat from Maya's Chrome.

Meet's DOM changes often, so everything here is heuristic and logs what it finds:
  captions : Meet renders a region (aria-label "Captions") with one block per speaker turn: the speaker's name, then
             the words. We turn captions on with the CC button (or the "c" shortcut) and poll that region.
  chat     : the "Chat with everyone" side panel. Messages carry data-sender-name / data-message-text in some Meet
             versions; otherwise we parse the panel text ("Name  time" header lines followed by message lines).
Both are untrusted participant content: callers must never treat them as instructions.
"""
import re

CAPTIONS_ON = re.compile(r"^(turn on captions|captions|turn on closed captions|show captions)", re.I)
CHAT_BTN = re.compile(r"^(chat with everyone|chat|open chat|show everyone)", re.I)

CAPTIONS_JS = r"""() => {
  const pick = () => {
    let r = document.querySelector('[role="region"][aria-label*="aption" i]') ||
            document.querySelector('[aria-label*="aption" i][aria-live]') ||
            document.querySelector('div[jsname="dsyhDe"]') || document.querySelector('div[jsname="YSxPC"]');
    return r;
  };
  const r = pick();
  if (!r) return {found: false};
  const out = [];
  // a caption block = an element that has an <img> (avatar) or a short name line plus text
  const blocks = [...r.querySelectorAll(':scope > div, :scope > div > div')].filter(b => (b.innerText || '').trim());
  const seen = new Set();
  for (const b of blocks) {
    const lines = (b.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
    if (lines.length < 2) continue;
    const key = lines.join('|');
    if ([...seen].some(k => k.includes(key) || key.includes(k))) continue;
    seen.add(key);
    out.push({speaker: lines[0].slice(0, 60), text: lines.slice(1).join(' ')});
  }
  if (!out.length) {
    const lines = (r.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
    for (let i = 0; i + 1 < lines.length; i += 2) out.push({speaker: lines[i].slice(0, 60), text: lines[i + 1]});
  }
  return {found: true, blocks: out};
}"""

CHAT_JS = r"""() => {
  const box = document.querySelector('textarea[aria-label*="message" i], textarea[placeholder*="message" i]');
  if (!box) return {open: false};
  // panel = nearest ancestor that also contains several message-like nodes
  let panel = box.parentElement;
  for (let i = 0; i < 12 && panel; i++) {
    if (panel.querySelectorAll('[data-sender-name], [data-message-id], [data-message-text]').length ||
        (panel.innerText || '').split('\n').length > 6) break;
    panel = panel.parentElement;
  }
  if (!panel) return {open: true, msgs: []};
  const msgs = [];
  const tagged = panel.querySelectorAll('[data-sender-name]');
  if (tagged.length) {
    tagged.forEach(g => {
      const who = g.getAttribute('data-sender-name');
      g.querySelectorAll('[data-message-text], [data-message-id]').forEach(m => {
        const t = (m.getAttribute('data-message-text') || m.innerText || '').trim();
        if (t) msgs.push({sender: who, text: t, id: m.getAttribute('data-message-id') || ''});
      });
    });
    return {open: true, msgs, mode: 'data-attrs'};
  }
  // current Meet (verified 2026-11): div[data-message-id] (the Pin button reuses the id, skip buttons); text in
  // [jsname="dTKtvb"]; group header holds the sender name + time ([jsname="biJjHb"]); own messages have no name.
  const UI = new Set(['keep', 'push_pin', 'pin message', 'unpin message', 'more_vert', 'more options', 'keep_off',
                      'react', 'add_reaction', 'reply', 'edit', 'delete']);
  const real = [...panel.querySelectorAll('div[data-message-id]')];
  if (real.length) {
    const seenIds = new Set();
    for (const m of real) {
      const id = m.getAttribute('data-message-id');
      if (seenIds.has(id)) continue; seenIds.add(id);
      const tEl = m.querySelector('[jsname="dTKtvb"]');
      const text = ((tEl || m).innerText || '').trim();
      let who = '', g = m;
      for (let i = 0; i < 8 && g; i++) {
        const timeEl = g.querySelector('[jsname="biJjHb"]');
        if (timeEl) {
          const head = timeEl.parentElement && timeEl.parentElement.parentElement ? timeEl.parentElement.parentElement : timeEl.parentElement;
          const bodies = new Set([...g.querySelectorAll('[jsname="dTKtvb"]')].map(e => (e.innerText || '').trim()));
          const lines = (head.innerText || '').split('\n').map(s => s.trim()).filter(Boolean);
          who = lines.filter(l => l !== (timeEl.innerText || '').trim() && !/^\d{1,2}:\d{2}/.test(l)
                                  && !bodies.has(l) && ![...bodies].some(t => t.startsWith(l))
                                  && !UI.has(l.toLowerCase()))[0] || '';
          break;
        }
        g = g.parentElement;
      }
      if (text) msgs.push({sender: who || 'You', text, id});
    }
    return {open: true, msgs, mode: 'meet-2026'};
  }
  const ids = panel.querySelectorAll('[data-message-id]');
  if (ids.length) {
    let who = '';
    ids.forEach(m => {
      const grp = m.closest('[data-sender-id], [jsname]') || m.parentElement;
      const head = grp && grp.previousElementSibling ? (grp.previousElementSibling.innerText || '') : '';
      const hm = head.split('\n').map(s => s.trim()).filter(Boolean);
      if (hm.length) who = hm[0];
      const t = (m.innerText || '').trim();
      if (t) msgs.push({sender: who, text: t, id: m.getAttribute('data-message-id')});
    });
    return {open: true, msgs, mode: 'message-id'};
  }
  return {open: true, msgs: [], raw: (panel.innerText || '').slice(-4000), mode: 'raw'};
}"""

TIME_RE = re.compile(r"^\d{1,2}:\d{2}(\s?[AaPp][Mm])?$")
UI_LINES = {"in-call messages", "let everyone send messages", "continuous chat is off", "send message",
            "send a message", "messages can only be seen by people in the call when the message is sent",
            "chat", "close", "everyone", "you can pin a message to make it visible for people who join later",
            "pin a message", "messages won't be saved when the call ends"}


def parse_raw_chat(raw: str):
    """Fallback parser for panel text: 'Name' + 'time' header then message lines."""
    lines = [l.strip() for l in (raw or "").split("\n") if l.strip()]
    msgs, who, i = [], None, 0
    while i < len(lines):
        l = lines[i]
        if l.lower() in UI_LINES or l.lower().startswith(("messages ", "continuous chat", "unless they're pinned")):
            i += 1; continue
        if i + 1 < len(lines) and TIME_RE.match(lines[i + 1]):  # "Name" followed by "10:42 AM"
            who = l; i += 2; continue
        if TIME_RE.match(l):
            i += 1; continue
        if who:
            msgs.append({"sender": who, "text": l, "id": ""})
        i += 1
    return msgs


async def _click_named(page, rx) -> bool:
    for role in ("button",):
        loc = page.get_by_role(role, name=rx)
        try:
            if await loc.count() and await loc.first.is_visible():
                await loc.first.click(timeout=1500)
                return True
        except Exception:
            pass
    return False


async def captions_on(page) -> bool:
    try:
        return await page.evaluate("""() => !!document.querySelector('[role="region"][aria-label="Captions"]') ||
            [...document.querySelectorAll('button')].some(b => /^captions/i.test(b.getAttribute('aria-label') || '')
                && b.getAttribute('aria-pressed') === 'true')""")
    except Exception:
        return False


async def enable_captions(page, log=print) -> bool:
    """Turn Meet's live captions on with the 'c' shortcut (the "Captions and translation" button only opens a menu)."""
    if await captions_on(page):
        return True
    try:
        await page.keyboard.press("Escape")
        await page.locator("body").click(position={"x": 5, "y": 5}, timeout=1500)
    except Exception:
        pass
    try:
        await page.keyboard.press("c")
        await page.wait_for_timeout(800)
    except Exception:
        pass
    ok = await captions_on(page)
    log(f"maya: captions {'ON' if ok else 'could not be turned on'}")
    return ok


async def open_chat(page) -> bool:
    try:
        r = await page.evaluate(CHAT_JS)
        if r.get("open"):
            return True
    except Exception:
        pass
    return await _click_named(page, CHAT_BTN)


async def read_captions(page):
    try:
        r = await page.evaluate(CAPTIONS_JS)
    except Exception:
        return None
    return r.get("blocks") if r.get("found") else None


async def read_chat(page):
    try:
        r = await page.evaluate(CHAT_JS)
    except Exception:
        return None
    if not r.get("open"):
        return None
    if r.get("mode") == "raw":
        return parse_raw_chat(r.get("raw", ""))
    return r.get("msgs", [])


class CaptionTracker:
    """Turns Meet's live, word-by-word growing caption blocks into finished 'Speaker: text' lines.
    A block grows ("Hello" -> "Hello everyone"); we match it to the live entry of the same speaker whose text is a
    prefix of (or overlaps) the new text. An entry is final when it disappears or stops changing for `settle` polls."""

    def __init__(self, settle=3):
        self.live = []       # [speaker, text, unchanged_polls, seen_this_round]
        self.done = []       # emitted (speaker, text), most recent last
        self.settle = settle

    @staticmethod
    def _same(old, new):
        o, n = old.strip().lower(), new.strip().lower()
        if not o or not n:
            return False
        k = min(len(o), len(n), 20)
        return n.startswith(o[:k]) or o.startswith(n[:k]) or o[-k:] in n

    def update(self, blocks):
        for e in self.live:
            e[3] = False
        for b in blocks or []:
            sp, tx = b["speaker"], b["text"]
            same_sp = [e for e in self.live if e[0] == sp and not e[3]]
            n_blocks = sum(1 for x in blocks if x["speaker"] == sp)
            # one caption block per speaker is the normal case: Meet rewrites early words ("Hello, every." ->
            # "Hello everyone!"), so match by speaker, not by text prefix
            match = same_sp[0] if (len(same_sp) == 1 and n_blocks == 1) else \
                next((e for e in same_sp if self._same(e[1], tx)), None)
            if match is None:
                self.live.append([sp, tx, 0, True])
            else:
                match[3] = True
                if match[1] == tx:
                    match[2] += 1
                else:
                    match[1], match[2] = tx, 0
        out, keep = [], []
        for e in self.live:
            if not e[3] or e[2] >= self.settle:
                if e[1].strip() and (e[0], e[1]) not in self.done[-50:]:
                    # if an emitted line is extended later, only emit the new tail
                    prev = next((t for s_, t in reversed(self.done[-20:]) if s_ == e[0] and e[1].startswith(t)), None)
                    tail = e[1][len(prev):].strip() if prev else e[1]
                    if tail:
                        out.append((e[0], tail))
                    self.done.append((e[0], e[1]))
                if e[3]:
                    e[2] = -10 ** 6  # emitted but still on screen: emit again only if it keeps growing
                    keep.append(e)
            else:
                keep.append(e)
        for e in keep:
            if e[2] < -1000 and e[3] is False:
                pass
        self.live = [e for e in keep if e[3]]
        return out


class ChatTracker:
    def __init__(self):
        self.seen = set()
        self.primed = False

    def update(self, msgs, include_existing=True):
        new = []
        for m in msgs or []:
            k = (m.get("id") or "") + "|" + m["sender"] + "|" + m["text"]
            if k in self.seen:
                continue
            self.seen.add(k)
            if self.primed or include_existing:
                new.append(m)
        self.primed = True
        return new
