"""Turn off Chrome's mic processing (echo cancellation, noise suppression, auto gain) for WhatsApp Web's calls.

Our "mic" is virtmic: the AI's clean digital voice, no room, no speaker->mic echo path. WhatsApp asks getUserMedia for
EC/NS/AGC, and Chrome's APM then works on a signal it was never meant for. In the call bench (bench_call.py
--worklet, 2026-11-23, native Termux) APM on: far-end dropout 2-18 %, Gemini 3-8/10; APM off (--no-apm): dropout 0 %,
lost 0 %, Gemini 10/10 on 3 of 3 runs. (In the bench the reference is our own voice played back, the worst case for
the echo canceller; on a real call it is the caller's voice, so confirm with a real call.)

    import mic_apm; mic_apm.install(page)      # current document + every later load of that browser context

WA_MIC_APM=1 in the environment keeps WhatsApp's own constraints (old behaviour).
"""
import os

JS = r"""(() => {
  if (window.__waNoApm || !window.MediaDevices) return;
  window.__waNoApm = true;
  const gum = MediaDevices.prototype.getUserMedia;
  MediaDevices.prototype.getUserMedia = function (c) {
    if (c && c.audio) {
      const a = typeof c.audio === 'object' ? c.audio : {};
      c = Object.assign({}, c, {audio: Object.assign({}, a,
        {echoCancellation: false, noiseSuppression: false, autoGainControl: false})});
    }
    return gum.call(this, c);
  };
})()"""


def enabled():
    return os.environ.get("WA_MIC_APM", "0") != "1"


def install(page, log=print):
    """Hook getUserMedia in `page` now and in every new document of its context (survives WhatsApp's reloads while
    this Playwright connection lives). WhatsApp calls getUserMedia per call, so installing before the call is enough."""
    if not enabled():
        return False
    try:
        page.context.add_init_script(JS)
        page.evaluate(JS)
        log("mic: Chrome echo cancellation / noise suppression / auto gain OFF for WhatsApp's mic (WA_MIC_APM=1 keeps them)")
        return True
    except Exception as e:  # never block a call over this
        log(f"mic: could not turn off Chrome's mic processing: {type(e).__name__}: {e}")
        return False
