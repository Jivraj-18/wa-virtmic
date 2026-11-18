window.RUNS = window.RUNS || {};
window.RUNS["E5/media_controls"] = {
 "transcript": [
  {
   "t": 0.85,
   "end": 8.78,
   "who": "AGENT",
   "text": "Hi, this is Pocket Radio. I can play the latest team update or some focus music, or make you a short podcast. What would you like?"
  },
  {
   "t": 10.39,
   "end": 11.06,
   "who": "CALLER",
   "text": "Hoi."
  },
  {
   "t": 11.53,
   "end": 13.85,
   "who": "CALLER",
   "text": "Can you play the latest team update?"
  },
  {
   "t": 15.49,
   "end": 25.7,
   "who": "AGENT",
   "text": "Here's the latest team update, week 46."
  },
  {
   "t": 24.76,
   "end": 26.99,
   "who": "CALLER",
   "text": "Sorry, one quick question."
  },
  {
   "t": 27.49,
   "end": 30.2,
   "who": "CALLER",
   "text": "What time is demo day on Friday?"
  },
  {
   "t": 31.27,
   "end": 34.94,
   "who": "AGENT",
   "text": "Demo day on Friday is at 4 p.m. Shall I continue?"
  },
  {
   "t": 36.52,
   "end": 37.94,
   "who": "CALLER",
   "text": "Ok, thanks."
  },
  {
   "t": 38.44,
   "end": 39.8,
   "who": "CALLER",
   "text": "کنٹینیو پلیز۔"
  },
  {
   "t": 39.37,
   "end": 40.25,
   "who": "AGENT",
   "text": "Here we go."
  },
  {
   "t": 41.41,
   "end": 48.47,
   "who": "AGENT",
   "text": "Sure, resuming now."
  },
  {
   "t": 47.62,
   "end": 49.64,
   "who": "CALLER",
   "text": "Can you skip to the next one?"
  },
  {
   "t": 50.92,
   "end": 58.01,
   "who": "AGENT",
   "text": "Here's Focus Tones."
  },
  {
   "t": 57.16,
   "end": 58.88,
   "who": "CALLER",
   "text": "अ बिट लाउडर प्लीज."
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hi! Can you play the latest team update?",
   "interrupt": "False",
   "caller_start_s": "10.6",
   "caller_end_s": "13.64",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "2.04",
   "reply_duration_s": "9.28"
  },
  {
   "turn": "2",
   "caller_text": "Sorry, one quick question. What time is demo day on Friday?",
   "interrupt": "True",
   "caller_start_s": "24.96",
   "caller_end_s": "29.98",
   "agent_talking_at_caller_start": "True",
   "agent_stop_latency_s": "0.54",
   "first_audio_latency_s": "1.48",
   "reply_duration_s": "3.28"
  },
  {
   "turn": "3",
   "caller_text": "Okay, thanks. Continue please.",
   "interrupt": "False",
   "caller_start_s": "36.72",
   "caller_end_s": "39.58",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "0.02",
   "reply_duration_s": "0.44"
  },
  {
   "turn": "4",
   "caller_text": "Can you skip to the next one?",
   "interrupt": "True",
   "caller_start_s": "47.82",
   "caller_end_s": "49.46",
   "agent_talking_at_caller_start": "True",
   "agent_stop_latency_s": "0.46",
   "first_audio_latency_s": "1.68",
   "reply_duration_s": "6.26"
  },
  {
   "turn": "5",
   "caller_text": "A bit louder please.",
   "interrupt": "True",
   "caller_start_s": "57.4",
   "caller_end_s": "58.66",
   "agent_talking_at_caller_start": "True",
   "agent_stop_latency_s": "0.42",
   "first_audio_latency_s": "1.98",
   "reply_duration_s": "1.48"
  },
  {
   "turn": "6",
   "caller_text": "Okay, you can stop the music now.",
   "interrupt": "True",
   "caller_start_s": "66.88",
   "caller_end_s": "69.06",
   "agent_talking_at_caller_start": "True",
   "agent_stop_latency_s": "0.4",
   "first_audio_latency_s": "1.86",
   "reply_duration_s": "1.84"
  },
  {
   "turn": "7",
   "caller_text": "Thanks, that's all. Bye!",
   "interrupt": "False",
   "caller_start_s": "74.8",
   "caller_end_s": "77.22",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.22",
   "reply_duration_s": "1.3"
  }
 ],
 "summary": {
  "script": "media_controls",
  "tag": "E5",
  "turns": 7,
  "agent_cmd": "{python} scripts/media_agent.py --context experiments/E5/context --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 7,
  "latency_median_s": 1.68,
  "latency_p90_s": 2.004,
  "interruptions": 4,
  "barge_in_stop_median_s": 0.44,
  "barge_ins_handled": 4
 },
 "clip": "media/E5/media_controls.mp3"
};
