window.RUNS = window.RUNS || {};
window.RUNS["E0/basic_qa"] = {
 "transcript": [
  {
   "t": 2.74,
   "end": 7.22,
   "who": "AGENT",
   "text": "Hello there! I'm your AI assistant on a test call, can you hear me clearly?"
  },
  {
   "t": 8.83,
   "end": 9.5,
   "who": "CALLER",
   "text": "はい。"
  },
  {
   "t": 9.94,
   "end": 12.56,
   "who": "CALLER",
   "text": "Yes, I can hear you clearly."
  },
  {
   "t": 13.39,
   "end": 15.92,
   "who": "AGENT",
   "text": "Great, let me know what you want to do next."
  },
  {
   "t": 17.47,
   "end": 19.61,
   "who": "CALLER",
   "text": "What is the capital of Japan?"
  },
  {
   "t": 20.74,
   "end": 22.88,
   "who": "AGENT",
   "text": "The capital of Japan is Tokyo."
  },
  {
   "t": 24.46,
   "end": 26.99,
   "who": "CALLER",
   "text": "And roughly how many people live there?"
  },
  {
   "t": 28.09,
   "end": 35.48,
   "who": "AGENT",
   "text": "Tokyo has roughly around 14 million people in the city itself, and over 37 million in the greater metropolitan area."
  },
  {
   "t": 37.03,
   "end": 38.54,
   "who": "CALLER",
   "text": "Great, thank you."
  },
  {
   "t": 39.01,
   "end": 39.68,
   "who": "CALLER",
   "text": "Bye."
  },
  {
   "t": 40.57,
   "end": 42.35,
   "who": "AGENT",
   "text": "Bye for now, take care."
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hi! Yes, I can hear you clearly.",
   "interrupt": "False",
   "caller_start_s": "9.05",
   "caller_end_s": "12.37",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.22",
   "reply_duration_s": "2.14"
  },
  {
   "turn": "2",
   "caller_text": "What is the capital of Japan?",
   "interrupt": "False",
   "caller_start_s": "17.69",
   "caller_end_s": "19.45",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.5",
   "reply_duration_s": "1.74"
  },
  {
   "turn": "3",
   "caller_text": "And roughly how many people live there?",
   "interrupt": "False",
   "caller_start_s": "24.67",
   "caller_end_s": "26.83",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.46",
   "reply_duration_s": "6.98"
  },
  {
   "turn": "4",
   "caller_text": "Great, thank you. Bye!",
   "interrupt": "False",
   "caller_start_s": "37.27",
   "caller_end_s": "39.49",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.3",
   "reply_duration_s": "1.38"
  }
 ],
 "summary": {
  "script": "basic_qa",
  "tag": "E0",
  "turns": 4,
  "agent_cmd": "{python} scripts/realtime_agent.py --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 4,
  "latency_median_s": 1.38,
  "latency_p90_s": 1.488,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0
 },
 "clip": "media/E0/basic_qa.mp3"
};
