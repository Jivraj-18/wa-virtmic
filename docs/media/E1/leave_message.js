window.RUNS = window.RUNS || {};
window.RUNS["E1/leave_message"] = {
 "transcript": [
  {
   "t": 0.4,
   "end": 6.47,
   "who": "AGENT",
   "text": "Hi, you've reached Alex's AI assistant. Alex can't take your call right now. How can I help?"
  },
  {
   "t": 8.14,
   "end": 9.98,
   "who": "CALLER",
   "text": "Hi, is Alex there?"
  },
  {
   "t": 10.99,
   "end": 17.24,
   "who": "AGENT",
   "text": "Alex isn't available at the moment. I can take a message or help with any questions about the G5 project."
  },
  {
   "t": 18.91,
   "end": 20.93,
   "who": "CALLER",
   "text": "Can I leave a message for him?"
  },
  {
   "t": 22.3,
   "end": 26.39,
   "who": "AGENT",
   "text": "Of course. Could you tell me your name and the message you'd like to leave for Alex?"
  },
  {
   "t": 28.3,
   "end": 30.68,
   "who": "CALLER",
   "text": "This is Priya from the sales team."
  },
  {
   "t": 31.27,
   "end": 36.08,
   "who": "CALLER",
   "text": "Our pilot customer wants beta access to G5 for two more people."
  },
  {
   "t": 36.67,
   "end": 40.1,
   "who": "CALLER",
   "text": "Please ask Alex to call me back tomorrow morning."
  },
  {
   "t": 41.17,
   "end": 51.44,
   "who": "AGENT",
   "text": "So your message is, \"Priya from the sales team says a pilot customer wants beta access to G5 for two more people, and please call her back tomorrow morning.\" I'll make sure Alex gets that."
  },
  {
   "t": 53.14,
   "end": 54.92,
   "who": "CALLER",
   "text": "Yes, that's right."
  },
  {
   "t": 55.54,
   "end": 56.9,
   "who": "CALLER",
   "text": "Thanks, bye."
  },
  {
   "t": 58.12,
   "end": 61.64,
   "who": "AGENT",
   "text": "Thanks Priya, I'll pass your message to Alex. Have a great day!"
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hi, is Alex there?",
   "interrupt": "False",
   "caller_start_s": "8.34",
   "caller_end_s": "9.78",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.42",
   "reply_duration_s": "5.82"
  },
  {
   "turn": "2",
   "caller_text": "Can I leave a message for him?",
   "interrupt": "False",
   "caller_start_s": "19.1",
   "caller_end_s": "20.74",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.78",
   "reply_duration_s": "3.68"
  },
  {
   "turn": "3",
   "caller_text": "This is Priya from the sales team. Our pilot customer wants beta access to G5 for two more people. Please ask Alex to call me back tomorrow morning.",
   "interrupt": "False",
   "caller_start_s": "28.48",
   "caller_end_s": "39.9",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.48",
   "reply_duration_s": "9.88"
  },
  {
   "turn": "4",
   "caller_text": "Yes, that's right. Thanks, bye.",
   "interrupt": "False",
   "caller_start_s": "53.32",
   "caller_end_s": "56.7",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.62",
   "reply_duration_s": "3.1"
  }
 ],
 "summary": {
  "script": "leave_message",
  "tag": "E1",
  "turns": 4,
  "agent_cmd": "{python} scripts/callcenter.py agent --context callcenter.example --in-device {in_device} --out-device {out_device} --transcript {transcript} --seconds {seconds}",
  "replied_turns": 4,
  "latency_median_s": 1.55,
  "latency_p90_s": 1.732,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0
 },
 "clip": "media/E1/leave_message.mp3"
};
