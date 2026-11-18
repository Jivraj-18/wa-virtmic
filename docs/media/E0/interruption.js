window.RUNS = window.RUNS || {};
window.RUNS["E0/interruption"] = {
 "transcript": [
  {
   "t": 0.28,
   "end": 5.12,
   "who": "AGENT",
   "text": "Hello and welcome! I'm an AI assistant on a test call. Can you hear me clearly?"
  },
  {
   "t": 6.7,
   "end": 9.2,
   "who": "CALLER",
   "text": "Hello, yes I can hear you."
  },
  {
   "t": 10.3,
   "end": 14.36,
   "who": "AGENT",
   "text": "Great! Let me know what you'd like to test or talk about, and I'll be here to help."
  },
  {
   "t": 15.97,
   "end": 20.36,
   "who": "CALLER",
   "text": "Can you tell me a long story about a cat who travels around India?"
  },
  {
   "t": 20.83,
   "end": 22.13,
   "who": "CALLER",
   "text": "ایک یار ٹائم"
  },
  {
   "t": 22.96,
   "end": 29.42,
   "who": "AGENT",
   "text": "ज़रूर, बताइए आपको क्या पसंद आएगा। मैं कहानी को छोटा और सिंपल रखता हूँ ताकि ब।"
  },
  {
   "t": 26.23,
   "end": 28.1,
   "who": "CALLER",
   "text": "Sorry, stop, stop."
  },
  {
   "t": 28.72,
   "end": 32.15,
   "who": "CALLER",
   "text": "Quick question instead, what is twelve times twelve?"
  },
  {
   "t": 32.95,
   "end": 35.66,
   "who": "AGENT",
   "text": "Twelve times twelve is one hundred forty-four."
  },
  {
   "t": 37.27,
   "end": 38.12,
   "who": "CALLER",
   "text": "Thanks."
  },
  {
   "t": 38.59,
   "end": 39.71,
   "who": "CALLER",
   "text": "That's all."
  },
  {
   "t": 40.51,
   "end": 43.91,
   "who": "AGENT",
   "text": "Got it. Feel free to reach out anytime. Take care!"
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hello, yes I can hear you.",
   "interrupt": "False",
   "caller_start_s": "6.92",
   "caller_end_s": "9.02",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.48",
   "reply_duration_s": "3.66"
  },
  {
   "turn": "2",
   "caller_text": "Can you tell me a long story about a cat who travels around India? Take your time.",
   "interrupt": "False",
   "caller_start_s": "16.2",
   "caller_end_s": "21.94",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.22",
   "reply_duration_s": "3.3"
  },
  {
   "turn": "3",
   "caller_text": "Sorry, stop, stop. Quick question instead: what is twelve times twelve?",
   "interrupt": "True",
   "caller_start_s": "26.46",
   "caller_end_s": "31.94",
   "agent_talking_at_caller_start": "True",
   "agent_stop_latency_s": "1.54",
   "first_audio_latency_s": "1.2",
   "reply_duration_s": "2.32"
  },
  {
   "turn": "4",
   "caller_text": "Thanks. That's all.",
   "interrupt": "False",
   "caller_start_s": "37.48",
   "caller_end_s": "39.48",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.22",
   "reply_duration_s": "3.02"
  }
 ],
 "summary": {
  "script": "interruption",
  "tag": "E0",
  "turns": 4,
  "agent_cmd": "{python} scripts/realtime_agent.py --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 4,
  "latency_median_s": 1.22,
  "latency_p90_s": 1.402,
  "interruptions": 1,
  "barge_in_stop_median_s": 1.54,
  "barge_ins_handled": 0
 },
 "clip": "media/E0/interruption.mp3"
};
