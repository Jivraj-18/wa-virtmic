window.RUNS = window.RUNS || {};
window.RUNS["E6/basic_qa"] = {
 "transcript": [
  {
   "t": 1.51,
   "end": 6.02,
   "who": "AGENT",
   "text": "Hello, I'm your AI assistant on a test call. Can you hear me clearly?"
  },
  {
   "t": 7.63,
   "end": 11.36,
   "who": "CALLER",
   "text": "Hi. Yes, I can hear you clearly."
  },
  {
   "t": 12.34,
   "end": 15.71,
   "who": "AGENT",
   "text": "Great! Glad you can hear me. How can I help you today?"
  },
  {
   "t": 17.32,
   "end": 19.46,
   "who": "CALLER",
   "text": "What is the capital of Japan?"
  },
  {
   "t": 20.47,
   "end": 22.82,
   "who": "AGENT",
   "text": "The capital of Japan is Tokyo."
  },
  {
   "t": 24.37,
   "end": 26.93,
   "who": "CALLER",
   "text": "And roughly how many people live there?"
  },
  {
   "t": 27.85,
   "end": 35.27,
   "who": "AGENT",
   "text": "Tokyo has roughly around 14 million people in the city itself, and over 37 million in the greater metropolitan area."
  },
  {
   "t": 36.91,
   "end": 38.42,
   "who": "CALLER",
   "text": "Great, thank you."
  },
  {
   "t": 38.86,
   "end": 39.56,
   "who": "CALLER",
   "text": "Bye"
  },
  {
   "t": 40.45,
   "end": 42.35,
   "who": "AGENT",
   "text": "Take care, talk to you soon."
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hi! Yes, I can hear you clearly.",
   "interrupt": "False",
   "caller_start_s": "7.84",
   "caller_end_s": "11.14",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.4",
   "reply_duration_s": "2.98"
  },
  {
   "turn": "2",
   "caller_text": "What is the capital of Japan?",
   "interrupt": "False",
   "caller_start_s": "17.52",
   "caller_end_s": "19.3",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.36",
   "reply_duration_s": "1.94"
  },
  {
   "turn": "3",
   "caller_text": "And roughly how many people live there?",
   "interrupt": "False",
   "caller_start_s": "24.6",
   "caller_end_s": "26.72",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.34",
   "reply_duration_s": "7.02"
  },
  {
   "turn": "4",
   "caller_text": "Great, thank you. Bye!",
   "interrupt": "False",
   "caller_start_s": "37.1",
   "caller_end_s": "39.38",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.28",
   "reply_duration_s": "1.48"
  }
 ],
 "summary": {
  "script": "basic_qa",
  "tag": "E6",
  "turns": 4,
  "agent_cmd": "{python} scripts/realtime_agent.py --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 4,
  "latency_median_s": 1.35,
  "latency_p90_s": 1.388,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0
 },
 "clip": "media/E6/basic_qa.mp3"
};
