window.RUNS = window.RUNS || {};
window.RUNS["E1/availability"] = {
 "transcript": [
  {
   "t": 12.76,
   "end": 18.59,
   "who": "AGENT",
   "text": "Hi, you've reached Alex's AI assistant. Alex can't take your call right now. How can I help?"
  },
  {
   "t": 20.23,
   "end": 22.04,
   "who": "CALLER",
   "text": "हाय, दिस इज रवी."
  },
  {
   "t": 22.51,
   "end": 24.83,
   "who": "CALLER",
   "text": "Is Alex available right now?"
  },
  {
   "t": 25.96,
   "end": 31.46,
   "who": "AGENT",
   "text": "Alex is in meetings this morning and might not be available. Would you like to leave a message or a callback time?"
  },
  {
   "t": 33.04,
   "end": 33.86,
   "who": "CALLER",
   "text": "Ok."
  },
  {
   "t": 34.3,
   "end": 37.16,
   "who": "CALLER",
   "text": "When can I expect a call back from him?"
  },
  {
   "t": 38.05,
   "end": 41.81,
   "who": "AGENT",
   "text": "Alex will be free after 6 p.m. today. Does that work for you?"
  },
  {
   "t": 43.42,
   "end": 46.22,
   "who": "CALLER",
   "text": "Can you tell me where he is traveling to?"
  },
  {
   "t": 47.44,
   "end": 52.4,
   "who": "AGENT",
   "text": "I'm sorry, I can't share details about Alex's travel. Would you like to leave a message for him?"
  },
  {
   "t": 54.07,
   "end": 55.52,
   "who": "CALLER",
   "text": "Fine thanks."
  },
  {
   "t": 55.99,
   "end": 56.69,
   "who": "CALLER",
   "text": "Bai."
  },
  {
   "t": 57.61,
   "end": 61.28,
   "who": "AGENT",
   "text": "Alright Ravi, I'll let Alex know you called. Have a great day!"
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hi, this is Ravi. Is Alex available right now?",
   "interrupt": "False",
   "caller_start_s": "20.44",
   "caller_end_s": "24.62",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.56",
   "reply_duration_s": "5.06"
  },
  {
   "turn": "2",
   "caller_text": "Okay. When can I expect a call back from him?",
   "interrupt": "False",
   "caller_start_s": "33.22",
   "caller_end_s": "36.96",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.3",
   "reply_duration_s": "3.34"
  },
  {
   "turn": "3",
   "caller_text": "Can you tell me where he is travelling to?",
   "interrupt": "False",
   "caller_start_s": "43.6",
   "caller_end_s": "46.0",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.66",
   "reply_duration_s": "4.54"
  },
  {
   "turn": "4",
   "caller_text": "Fine, thanks. Bye.",
   "interrupt": "False",
   "caller_start_s": "54.26",
   "caller_end_s": "56.46",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.36",
   "reply_duration_s": "3.26"
  }
 ],
 "summary": {
  "script": "availability",
  "tag": "E1",
  "turns": 4,
  "agent_cmd": "{python} scripts/callcenter.py agent --context callcenter.example --in-device {in_device} --out-device {out_device} --transcript {transcript} --seconds {seconds}",
  "replied_turns": 4,
  "latency_median_s": 1.46,
  "latency_p90_s": 1.63,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0
 },
 "clip": "media/E1/availability.mp3"
};
