"""WhatsApp Web data WITHOUT navigating the page - safe during a call.

wa_msg.py / wa_call.open_chat() go to web.whatsapp.com/send?phone=..., which RELOADS WhatsApp Web and would drop a
call in progress. These helpers use WhatsApp Web's own in-memory models instead (window.require('WAWebCollections'),
the same modules whatsapp-web.js uses). Message bodies in IndexedDB are encrypted at rest; the in-memory models are
decrypted. Internal module names may change with WhatsApp updates: every helper raises a clear error if so.

    import wa_store
    wa_store.find(page, "919876543210")           # or an exact saved name -> {num, name, chat}
    wa_store.read(page, "919876543210", 20)       # [{t, who, type, body, id, media}]
    wa_store.send(page, "919876543210", "hi")
    wa_store.media(page, "919876543210", msg_id)  # -> (bytes, mimetype)
"""
import base64

_FIND = r"""
const C = window.require('WAWebCollections');
const digits = s => String(s || '').replace(/\D/g, '');
const findContact = (who) => {
  const q = String(who).trim(), d = digits(q), all = C.Contact.getModelsArray();
  const num = c => (c.phoneNumber && c.phoneNumber.user) || (c.id && c.id.server === 'c.us' ? c.id.user : '');
  let c = null;
  if (d.length >= 8 && d.length === q.replace(/[\s+()-]/g, '').length) c = all.find(c => num(c) === d);
  if (!c) c = all.find(c => (c.name || '') === q) || all.find(c => (c.name || '').toLowerCase() === q.toLowerCase());
  if (!c && d.length >= 8) return {num: d, name: '', contact: null};
  return c ? {num: num(c), name: c.name || c.pushname || '', contact: c} : null;
};
const findChat = async (who, create) => {
  const f = findContact(who);
  if (!f) throw new Error('no WhatsApp contact matches ' + who);
  let chat = (f.contact && C.Chat.get(f.contact.id)) || C.Chat.get(f.num + '@c.us');
  if (!chat && f.contact && f.contact.phoneNumber) chat = C.Chat.get(f.contact.phoneNumber);
  if (!chat) chat = C.Chat.getModelsArray().find(ch => ch.id.user === f.num ||
    (ch.contact && ch.contact.phoneNumber && ch.contact.phoneNumber.user === f.num));
  if (!chat && create) {
    const W = window.require('WAWebWidFactory'), F = window.require('WAWebFindChatAction');
    const r = await F.findOrCreateLatestChat(W.createWid(f.num + '@c.us'));
    chat = r && (r.chat || r);
  }
  return {f, chat};
};
"""

_READ = "async ([who, n]) => {" + _FIND + r"""
  const {f, chat} = await findChat(who, false);
  if (!chat) return {num: f.num, name: f.name, msgs: []};
  const L = window.require('WAWebChatLoadMessages');
  for (let i = 0; i < 3 && chat.msgs.length < n; i++) {
    try { const before = chat.msgs.length; await L.loadEarlierMsgs(chat); if (chat.msgs.length === before) break; }
    catch (e) { break; }
  }
  const msgs = chat.msgs.getModelsArray().slice(-n).map(m => ({
    t: m.t, who: m.id.fromMe ? 'me' : 'them', type: m.type, id: m.id._serialized,
    body: m.type === 'chat' ? (m.body || '') : (m.caption || ''),
    media: !!(m.directPath && m.mediaKey), mimetype: m.mimetype || '', duration: m.duration || 0}));
  return {num: f.num, name: f.name, msgs};
}"""

_SEND = "async ([who, text]) => {" + _FIND + r"""
  const {f, chat} = await findChat(who, true);
  if (!chat) throw new Error('could not open a chat with ' + who);
  await window.require('WAWebSendTextMsgChatAction').sendTextMsgToChat(chat, text);
  return {num: f.num, name: f.name};
}"""

_MEDIA = "async ([who, id]) => {" + _FIND + r"""
  const {chat} = await findChat(who, false);
  const m = chat && chat.msgs.getModelsArray().find(m => m.id._serialized === id);
  if (!m) throw new Error('message not found in the loaded chat: ' + id);
  const D = window.require('WAWebDownloadManager').downloadManager;
  const buf = await D.downloadAndMaybeDecrypt({directPath: m.directPath, encFilehash: m.encFilehash,
    filehash: m.filehash, mediaKey: m.mediaKey, mediaKeyTimestamp: m.mediaKeyTimestamp, type: m.type,
    signal: new AbortController().signal});
  const b = new Uint8Array(buf); let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return {b64: btoa(s), mimetype: m.mimetype || ''};
}"""

_ME = r"""() => { const w = window.require('WAWebUserPrefsMeUser').getMaybeMePnUser(); return w ? w.user : null; }"""


def find(page, who):
    return read(page, who, 0)


def read(page, who, n=20):
    return page.evaluate(_READ, [str(who), int(n)])


def send(page, who, text):
    return page.evaluate(_SEND, [str(who), str(text)])


def media(page, who, msg_id):
    r = page.evaluate(_MEDIA, [str(who), msg_id])
    return base64.b64decode(r["b64"]), r["mimetype"]


def me(page):
    return page.evaluate(_ME)


def wa_page(browser):
    """The WhatsApp Web tab (no navigation)."""
    for c in browser.contexts:
        for p in c.pages:
            if "web.whatsapp.com" in p.url:
                return p
    raise RuntimeError("no WhatsApp Web tab open")
