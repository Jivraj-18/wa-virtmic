window.RUNS = window.RUNS || {};
window.RUNS["E1/g5_release"] = {
 "transcript": [
  {
   "t": 0.52,
   "end": 6.38,
   "who": "AGENT",
   "text": "Hi, you've reached Alex's AI assistant. Alex can't take your call right now. How can I help?"
  },
  {
   "t": 8.05,
   "end": 10.94,
   "who": "CALLER",
   "text": "Hello, I'm calling about the G5 project."
  },
  {
   "t": 11.53,
   "end": 13.43,
   "who": "CALLER",
   "text": "When is G5 releasing?"
  },
  {
   "t": 14.71,
   "end": 19.43,
   "who": "AGENT",
   "text": "The G5 public release is on Tuesday 15th December 2026."
  },
  {
   "t": 21.04,
   "end": 23.42,
   "who": "CALLER",
   "text": "And is there a beta I can try before that?"
  },
  {
   "t": 24.43,
   "end": 29.9,
   "who": "AGENT",
   "text": "Yes, the beta for pilot customers is already live since 2 November 2026."
  },
  {
   "t": 31.51,
   "end": 34.31,
   "who": "CALLER",
   "text": "What is the price of G5 for 50 users?"
  },
  {
   "t": 35.29,
   "end": 40.52,
   "who": "AGENT",
   "text": "I don't have pricing details. I can pass that question to Alex. Would you like to leave a message?"
  },
  {
   "t": 42.1,
   "end": 43.04,
   "who": "CALLER",
   "text": "Got it."
  },
  {
   "t": 43.66,
   "end": 44.54,
   "who": "CALLER",
   "text": "Thank you."
  },
  {
   "t": 45.55,
   "end": 49.43,
   "who": "AGENT",
   "text": "You're welcome. Just let me know if you'd like me to share anything with Alex."
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hello, I'm calling about the G5 project. When is G5 releasing?",
   "interrupt": "False",
   "caller_start_s": "8.25",
   "caller_end_s": "13.25",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.66",
   "reply_duration_s": "4.32"
  },
  {
   "turn": "2",
   "caller_text": "And is there a beta I can try before that?",
   "interrupt": "False",
   "caller_start_s": "21.27",
   "caller_end_s": "23.21",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.42",
   "reply_duration_s": "5.06"
  },
  {
   "turn": "3",
   "caller_text": "What is the price of G5 for fifty users?",
   "interrupt": "False",
   "caller_start_s": "31.73",
   "caller_end_s": "34.13",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.38",
   "reply_duration_s": "4.8"
  },
  {
   "turn": "4",
   "caller_text": "Got it. Thank you.",
   "interrupt": "False",
   "caller_start_s": "42.33",
   "caller_end_s": "44.37",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.4",
   "reply_duration_s": "3.46"
  }
 ],
 "summary": {
  "script": "g5_release",
  "tag": "E1",
  "turns": 4,
  "agent_cmd": "{python} scripts/callcenter.py agent --context callcenter.example --in-device {in_device} --out-device {out_device} --transcript {transcript} --seconds {seconds}",
  "replied_turns": 4,
  "latency_median_s": 1.41,
  "latency_p90_s": 1.588,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0
 },
 "clip": "media/E1/g5_release.mp3"
};
