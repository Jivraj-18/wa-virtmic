window.RUNS = window.RUNS || {};
window.RUNS["E2/deep_facts"] = {
 "transcript": [
  {
   "t": 0.52,
   "end": 5.51,
   "who": "AGENT",
   "text": "Hello, this is the Kestrel K2 Program Team Assistant. How can I support you today?"
  },
  {
   "t": 7.09,
   "end": 9.41,
   "who": "CALLER",
   "text": "Hi, yes I can hear you."
  },
  {
   "t": 10.3,
   "end": 14.99,
   "who": "AGENT",
   "text": "Great, I can hear you too. What would you like to know about the Kestrel K2 program?"
  },
  {
   "t": 16.57,
   "end": 19.91,
   "who": "CALLER",
   "text": "When is the firmware freeze for the Kestrel K2?"
  },
  {
   "t": 20.83,
   "end": 22.01,
   "who": "AGENT",
   "text": "Let me check that."
  },
  {
   "t": 23.47,
   "end": 29.78,
   "who": "AGENT",
   "text": "The firmware freeze for the Kestrel K2 release FW3.2 is 9 February 2027."
  },
  {
   "t": 37.33,
   "end": 38.15,
   "who": "CALLER",
   "text": "Ok."
  },
  {
   "t": 38.65,
   "end": 42.14,
   "who": "CALLER",
   "text": "How much does the fleet plan cost per drone per year?"
  },
  {
   "t": 43.24,
   "end": 50.36,
   "who": "AGENT",
   "text": "Let me check the fleet plan cost per drone for you. The fleet plan costs $2,340 per drone per year."
  },
  {
   "t": 57.97,
   "end": 62.27,
   "who": "CALLER",
   "text": "Who has to file the noise certification paperwork and by when?"
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hi, yes I can hear you.",
   "interrupt": "False",
   "caller_start_s": "7.34",
   "caller_end_s": "9.22",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.3",
   "reply_duration_s": "4.26"
  },
  {
   "turn": "2",
   "caller_text": "When is the firmware freeze for the Kestrel K2?",
   "interrupt": "False",
   "caller_start_s": "16.78",
   "caller_end_s": "19.72",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.32",
   "reply_duration_s": "0.78"
  },
  {
   "turn": "3",
   "caller_text": "Okay. How much does the Fleet plan cost per drone per year?",
   "interrupt": "False",
   "caller_start_s": "37.54",
   "caller_end_s": "41.96",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.5",
   "reply_duration_s": "6.7"
  },
  {
   "turn": "4",
   "caller_text": "Who has to file the noise certification paperwork, and by when?",
   "interrupt": "False",
   "caller_start_s": "58.2",
   "caller_end_s": "62.1",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.32",
   "reply_duration_s": "6.94"
  },
  {
   "turn": "5",
   "caller_text": "And how long is the standard warranty?",
   "interrupt": "False",
   "caller_start_s": "78.44",
   "caller_end_s": "80.74",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.36",
   "reply_duration_s": "7.06"
  },
  {
   "turn": "6",
   "caller_text": "Perfect, thanks. Bye!",
   "interrupt": "False",
   "caller_start_s": "97.24",
   "caller_end_s": "99.52",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.26",
   "reply_duration_s": "2.84"
  }
 ],
 "summary": {
  "script": "deep_facts",
  "tag": "E2",
  "turns": 6,
  "agent_cmd": "{python} scripts/tools.py agent --context experiments/E2/context --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 6,
  "latency_median_s": 1.32,
  "latency_p90_s": 1.43,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0,
  "e2": {
   "tool_turns": 4,
   "tool_calls": 5,
   "first_audio_median_s": 1.34,
   "answer_median_s": 4.04,
   "answer_max_s": 4.4,
   "correct": 4,
   "checked": 4,
   "rows": [
    {
     "turn": 2,
     "question": "When is the firmware freeze for the Kestrel K2?",
     "tools": "search_knowledge",
     "tool_s": 0.02,
     "hold_source": "model",
     "hold_text": "Let me check that.",
     "t_first_audio_s": 1.32,
     "t_answer_s": 3.96,
     "answer": "The firmware freeze for the Kestrel K2 release FW 3.2 is 9 February 2027.",
     "expected": "9 february 2027",
     "correct": true
    },
    {
     "turn": 3,
     "question": "Okay. How much does the Fleet plan cost per drone per year?",
     "tools": "search_knowledge+read_file",
     "tool_s": 0.02,
     "hold_source": "model",
     "hold_text": "Let me check the fleet plan cost per drone for you.",
     "t_first_audio_s": 1.5,
     "t_answer_s": 4.13,
     "answer": "The Fleet plan costs $2,340 per drone per year.",
     "expected": "2340",
     "correct": true
    },
    {
     "turn": 4,
     "question": "Who has to file the noise certification paperwork, and by when?",
     "tools": "search_knowledge",
     "tool_s": 0.01,
     "hold_source": "model",
     "hold_text": "Let me find that information for you.",
     "t_first_audio_s": 1.3,
     "t_answer_s": 3.08,
     "answer": "Ravi Menon has to file the noise certification paperwork with the city authority by 20 November.",
     "expected": "ravi menon; 20 november",
     "correct": true
    },
    {
     "turn": 5,
     "question": "And how long is the standard warranty?",
     "tools": "search_knowledge",
     "tool_s": 0.03,
     "hold_source": "model",
     "hold_text": "Let me check the standard warranty length for you.",
     "t_first_audio_s": 1.36,
     "t_answer_s": 4.4,
     "answer": "The standard warranty is 18 months from delivery, included in every plan.",
     "expected": "18 months",
     "correct": true
    }
   ]
  }
 },
 "clip": "media/E2/deep_facts.mp3"
};
