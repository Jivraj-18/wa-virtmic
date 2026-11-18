window.RUNS = window.RUNS || {};
window.RUNS["E2/synthesis_still"] = {
 "transcript": [
  {
   "t": 0.46,
   "end": 5.15,
   "who": "AGENT",
   "text": "Hello, this is the Kestrel K2 Program Team Assistant. How can I help you today?"
  },
  {
   "t": 6.73,
   "end": 9.5,
   "who": "CALLER",
   "text": "Hello, yes, I can hear you."
  },
  {
   "t": 10.21,
   "end": 12.98,
   "who": "AGENT",
   "text": "Great! Let me know what you need help with today."
  },
  {
   "t": 14.56,
   "end": 16.49,
   "who": "CALLER",
   "text": "I'm from the finance team."
  },
  {
   "t": 16.99,
   "end": 25.31,
   "who": "CALLER",
   "text": "Can you work out the total first-year cost for all the drones in the Kochi pilot on the fleet plan, including the extended warranty?"
  },
  {
   "t": 25.81,
   "end": 27.95,
   "who": "CALLER",
   "text": "Please check all the documents."
  },
  {
   "t": 29.5,
   "end": 32.09,
   "who": "AGENT",
   "text": "Give me a moment, I'm checking the documents."
  },
  {
   "t": 36.55,
   "end": 45.44,
   "who": "AGENT",
   "text": "Still checking, thanks for waiting. The total first-year cost for the Kochi Pilot is $82,500, including the extended warranty."
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hello, yes, I can hear you.",
   "interrupt": "False",
   "caller_start_s": "6.97",
   "caller_end_s": "9.31",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.12",
   "reply_duration_s": "2.34"
  },
  {
   "turn": "2",
   "caller_text": "I'm from the finance team. Can you work out the total first-year cost for all the drones in the Kochi pilot, on the Fleet plan, including the extended warranty? Please check all the documents.",
   "interrupt": "False",
   "caller_start_s": "14.77",
   "caller_end_s": "27.73",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.96",
   "reply_duration_s": "2.2"
  },
  {
   "turn": "3",
   "caller_text": "Great. And when does the pilot start?",
   "interrupt": "False",
   "caller_start_s": "67.23",
   "caller_end_s": "70.23",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.24",
   "reply_duration_s": "5.64"
  },
  {
   "turn": "4",
   "caller_text": "Thanks, that's all. Bye!",
   "interrupt": "False",
   "caller_start_s": "85.15",
   "caller_end_s": "87.59",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "0.02",
   "reply_duration_s": "2.28"
  }
 ],
 "summary": {
  "script": "synthesis_still",
  "tag": "E2",
  "turns": 4,
  "agent_cmd": "{python} scripts/tools.py agent --context experiments/E2/context --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 4,
  "latency_median_s": 1.18,
  "latency_p90_s": 1.744,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0,
  "e2": {
   "tool_turns": 2,
   "tool_calls": 3,
   "first_audio_median_s": 1.6,
   "answer_median_s": 7.41,
   "answer_max_s": 11.43,
   "correct": 2,
   "checked": 2,
   "rows": [
    {
     "turn": 2,
     "question": "I'm from the finance team. Can you work out the total first-year cost for all the drones in the Kochi pilot, on the Fleet plan, including the extended warranty? Please check all the documents.",
     "tools": "ask_agent",
     "tool_s": 7.9,
     "hold_source": "forced",
     "hold_text": "Give me a moment, I'm checking the documents. / Still checking, thanks for waiting.",
     "t_first_audio_s": 1.97,
     "t_answer_s": 11.43,
     "answer": "The total first-year cost for the Kochi pilot is $82,500, including the extended warranty.",
     "expected": "82500",
     "correct": true
    },
    {
     "turn": 3,
     "question": "Great. And when does the pilot start?",
     "tools": "search_knowledge+read_file",
     "tool_s": 0.01,
     "hold_source": "model",
     "hold_text": "Let me check that for you.",
     "t_first_audio_s": 1.23,
     "t_answer_s": 3.39,
     "answer": "The Kochi pilot start date is set to 2 December 2026.",
     "expected": "2 december",
     "correct": true
    }
   ]
  }
 },
 "clip": "media/E2/synthesis_still.mp3"
};
