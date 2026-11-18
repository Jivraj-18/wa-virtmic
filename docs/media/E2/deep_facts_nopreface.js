window.RUNS = window.RUNS || {};
window.RUNS["E2/deep_facts_nopreface"] = {
 "transcript": [
  {
   "t": 0.73,
   "end": 5.15,
   "who": "AGENT",
   "text": "Hello, you've reached the Kestrel K2 program team. How can I assist you today?"
  },
  {
   "t": 6.79,
   "end": 9.11,
   "who": "CALLER",
   "text": "Hi, yes I can hear you."
  },
  {
   "t": 10.45,
   "end": 13.52,
   "who": "AGENT",
   "text": "Great! How can I help you with the K2 project today?"
  },
  {
   "t": 15.13,
   "end": 18.5,
   "who": "CALLER",
   "text": "When is the firmware freeze for the TestRail K2?"
  },
  {
   "t": 21.49,
   "end": 27.53,
   "who": "AGENT",
   "text": "The firmware freeze for the Kestrel K2 release fw3.2 is 9 February 2027."
  },
  {
   "t": 35.23,
   "end": 36.05,
   "who": "CALLER",
   "text": "OK"
  },
  {
   "t": 36.55,
   "end": 40.04,
   "who": "CALLER",
   "text": "How much does the fleet plan cost per drone per year?"
  },
  {
   "t": 42.55,
   "end": 46.58,
   "who": "AGENT",
   "text": "The fleet plan costs $2,340 per drone per year."
  },
  {
   "t": 54.22,
   "end": 58.52,
   "who": "CALLER",
   "text": "Who has to file the noise certification paperwork and by when?"
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hi, yes I can hear you.",
   "interrupt": "False",
   "caller_start_s": "6.98",
   "caller_end_s": "8.88",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.76",
   "reply_duration_s": "2.68"
  },
  {
   "turn": "2",
   "caller_text": "When is the firmware freeze for the Kestrel K2?",
   "interrupt": "False",
   "caller_start_s": "15.3",
   "caller_end_s": "18.28",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "3.4",
   "reply_duration_s": "5.66"
  },
  {
   "turn": "3",
   "caller_text": "Okay. How much does the Fleet plan cost per drone per year?",
   "interrupt": "False",
   "caller_start_s": "35.4",
   "caller_end_s": "39.82",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "2.94",
   "reply_duration_s": "3.6"
  },
  {
   "turn": "4",
   "caller_text": "Who has to file the noise certification paperwork, and by when?",
   "interrupt": "False",
   "caller_start_s": "54.42",
   "caller_end_s": "58.32",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "2.8",
   "reply_duration_s": "4.04"
  },
  {
   "turn": "5",
   "caller_text": "And how long is the standard warranty?",
   "interrupt": "False",
   "caller_start_s": "73.18",
   "caller_end_s": "75.46",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "2.2",
   "reply_duration_s": "4.02"
  },
  {
   "turn": "6",
   "caller_text": "Perfect, thanks. Bye!",
   "interrupt": "False",
   "caller_start_s": "89.66",
   "caller_end_s": "91.98",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.28",
   "reply_duration_s": "1.54"
  }
 ],
 "summary": {
  "script": "deep_facts_nopreface",
  "tag": "E2",
  "turns": 6,
  "agent_cmd": "{python} scripts/tools.py agent --no-preface --context experiments/E2/context --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 6,
  "latency_median_s": 2.5,
  "latency_p90_s": 3.17,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0,
  "e2": {
   "tool_turns": 4,
   "tool_calls": 7,
   "first_audio_median_s": 2.87,
   "answer_median_s": 2.87,
   "answer_max_s": 3.4,
   "correct": 4,
   "checked": 4,
   "rows": [
    {
     "turn": 2,
     "question": "When is the firmware freeze for the Kestrel K2?",
     "tools": "search_knowledge+read_file",
     "tool_s": 0.18,
     "hold_source": "none",
     "hold_text": "",
     "t_first_audio_s": 3.4,
     "t_answer_s": 3.4,
     "answer": "The firmware freeze for the Kestrel K2 release FW 3.2 is 9 February 2027.",
     "expected": "9 february 2027",
     "correct": true
    },
    {
     "turn": 3,
     "question": "Okay. How much does the Fleet plan cost per drone per year?",
     "tools": "search_knowledge+read_file",
     "tool_s": 0.02,
     "hold_source": "none",
     "hold_text": "",
     "t_first_audio_s": 2.94,
     "t_answer_s": 2.94,
     "answer": "The Fleet plan costs $2,340 per drone per year.",
     "expected": "2340",
     "correct": true
    },
    {
     "turn": 4,
     "question": "Who has to file the noise certification paperwork, and by when?",
     "tools": "search_knowledge+read_file",
     "tool_s": 0.03,
     "hold_source": "none",
     "hold_text": "",
     "t_first_audio_s": 2.8,
     "t_answer_s": 2.8,
     "answer": "Ravi Menon has to file the noise certification paperwork by 20 November.",
     "expected": "ravi menon; 20 november",
     "correct": true
    },
    {
     "turn": 5,
     "question": "And how long is the standard warranty?",
     "tools": "search_knowledge",
     "tool_s": 0.01,
     "hold_source": "none",
     "hold_text": "",
     "t_first_audio_s": 2.2,
     "t_answer_s": 2.2,
     "answer": "The standard warranty is 18 months from delivery, included in every plan.",
     "expected": "18 months",
     "correct": true
    }
   ]
  }
 },
 "clip": "media/E2/deep_facts_nopreface.mp3"
};
