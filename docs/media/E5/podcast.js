window.RUNS = window.RUNS || {};
window.RUNS["E5/podcast"] = {
 "transcript": [
  {
   "t": 1.45,
   "end": 9.47,
   "who": "AGENT",
   "text": "Hi, this is Pocket Radio. I can play the latest team update, or some focus music, or make you a short podcast. What would you like?"
  },
  {
   "t": 11.14,
   "end": 11.78,
   "who": "CALLER",
   "text": "Hi"
  },
  {
   "t": 12.25,
   "end": 16.28,
   "who": "CALLER",
   "text": "Can you make me a one-minute podcast about Project Nimbus?"
  },
  {
   "t": 18.01,
   "end": 20.69,
   "who": "AGENT",
   "text": "It'll take about ten seconds to put that together."
  },
  {
   "t": 23.53,
   "end": 43.07,
   "who": "AGENT",
   "text": "Welcome to today's quick update on Project Nimbus: Lumenlab's solar-powered parcel lockers in Pune."
  },
  {
   "t": 42.22,
   "end": 43.58,
   "who": "CALLER",
   "text": "ویٹ سوری."
  },
  {
   "t": 44.11,
   "end": 46.94,
   "who": "CALLER",
   "text": "हाउ मच बजट इज द टीम आस्किंग फॉर?"
  },
  {
   "t": 47.89,
   "end": 51.68,
   "who": "AGENT",
   "text": "The team is asking for eighteen lakh rupees. Shall I continue?"
  },
  {
   "t": 53.32,
   "end": 54.14,
   "who": "CALLER",
   "text": "Got it."
  },
  {
   "t": 54.73,
   "end": 56.06,
   "who": "CALLER",
   "text": "Please continue."
  },
  {
   "t": 57.82,
   "end": 70.61,
   "who": "AGENT",
   "text": "Each locker runs on a 400-watt solar panel and a two-kilowatt-hour battery, lasting three days without sunlight."
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hi. Can you make me a one minute podcast about Project Nimbus?",
   "interrupt": "False",
   "caller_start_s": "11.35",
   "caller_end_s": "16.09",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "2.14",
   "reply_duration_s": "2.28"
  },
  {
   "turn": "2",
   "caller_text": "Wait, sorry. How much budget is the team asking for?",
   "interrupt": "True",
   "caller_start_s": "42.45",
   "caller_end_s": "46.73",
   "agent_talking_at_caller_start": "True",
   "agent_stop_latency_s": "0.42",
   "first_audio_latency_s": "1.36",
   "reply_duration_s": "3.38"
  },
  {
   "turn": "3",
   "caller_text": "Got it. Please continue.",
   "interrupt": "False",
   "caller_start_s": "53.55",
   "caller_end_s": "55.87",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "2.16",
   "reply_duration_s": "12.3"
  },
  {
   "turn": "4",
   "caller_text": "Thanks, that's enough for today. Please stop.",
   "interrupt": "True",
   "caller_start_s": "70.33",
   "caller_end_s": "73.97",
   "agent_talking_at_caller_start": "True",
   "agent_stop_latency_s": "0.1",
   "first_audio_latency_s": "2.06",
   "reply_duration_s": "1.86"
  },
  {
   "turn": "5",
   "caller_text": "Bye!",
   "interrupt": "False",
   "caller_start_s": "80.63",
   "caller_end_s": "80.91",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.4",
   "reply_duration_s": "1.14"
  }
 ],
 "summary": {
  "script": "podcast",
  "tag": "E5",
  "turns": 5,
  "agent_cmd": "{python} scripts/media_agent.py --context experiments/E5/context --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 5,
  "latency_median_s": 2.06,
  "latency_p90_s": 2.152,
  "interruptions": 2,
  "barge_in_stop_median_s": 0.26,
  "barge_ins_handled": 2
 },
 "clip": "media/E5/podcast.mp3"
};
