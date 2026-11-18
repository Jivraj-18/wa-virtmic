window.RUNS = window.RUNS || {};
window.RUNS["E2/synthesis_fallback"] = {
 "transcript": [
  {
   "t": 9.73,
   "end": 14.48,
   "who": "AGENT",
   "text": "Hello, this is the Kestrel K2 Program team assistant. How can I support you today?"
  },
  {
   "t": 16.09,
   "end": 18.83,
   "who": "CALLER",
   "text": "Hello, yes, I can hear you."
  },
  {
   "t": 19.78,
   "end": 25.13,
   "who": "AGENT",
   "text": "Great, I'm glad you can hear me. What information do you need about the Kestrel K2 project?"
  },
  {
   "t": 26.71,
   "end": 28.61,
   "who": "CALLER",
   "text": "I'm from the finance team."
  },
  {
   "t": 29.14,
   "end": 37.46,
   "who": "CALLER",
   "text": "Can you work out the total first-year cost for all the drones in the Kochi pilot on the fleet plan, including the extended warranty?"
  },
  {
   "t": 37.96,
   "end": 40.07,
   "who": "CALLER",
   "text": "Please check all the documents."
  },
  {
   "t": 41.05,
   "end": 42.23,
   "who": "AGENT",
   "text": "Let me check that."
  },
  {
   "t": 45.28,
   "end": 51.41,
   "who": "AGENT",
   "text": "The total first-year cost for the Kochi Pilot, including the extended warranty, is $82,500."
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hello, yes, I can hear you.",
   "interrupt": "False",
   "caller_start_s": "16.29",
   "caller_end_s": "18.65",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.34",
   "reply_duration_s": "4.94"
  },
  {
   "turn": "2",
   "caller_text": "I'm from the finance team. Can you work out the total first-year cost for all the drones in the Kochi pilot, on the Fleet plan, including the extended warranty? Please check all the documents.",
   "interrupt": "False",
   "caller_start_s": "26.91",
   "caller_end_s": "39.87",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.4",
   "reply_duration_s": "0.74"
  },
  {
   "turn": "3",
   "caller_text": "Great. And when does the pilot start?",
   "interrupt": "False",
   "caller_start_s": "73.27",
   "caller_end_s": "76.25",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.62",
   "reply_duration_s": "5.8"
  },
  {
   "turn": "4",
   "caller_text": "Thanks, that's all. Bye!",
   "interrupt": "False",
   "caller_start_s": "91.67",
   "caller_end_s": "94.15",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.3",
   "reply_duration_s": "1.18"
  }
 ],
 "summary": {
  "script": "synthesis_fallback",
  "tag": "E2",
  "turns": 4,
  "agent_cmd": "{python} scripts/tools.py agent --context experiments/E2/context --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 4,
  "latency_median_s": 1.37,
  "latency_p90_s": 1.554,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0,
  "e2": {
   "tool_turns": 2,
   "tool_calls": 2,
   "first_audio_median_s": 1.51,
   "answer_median_s": 4.7,
   "answer_max_s": 5.61,
   "correct": 2,
   "checked": 2,
   "rows": [
    {
     "turn": 2,
     "question": "I'm from the finance team. Can you work out the total first-year cost for all the drones in the Kochi pilot, on the Fleet plan, including the extended warranty? Please check all the documents.",
     "tools": "ask_agent",
     "tool_s": 2.53,
     "hold_source": "model",
     "hold_text": "Let me check that.",
     "t_first_audio_s": 1.39,
     "t_answer_s": 5.61,
     "answer": "The total first-year cost for the Kochi pilot, including the extended warranty, is $82,500.",
     "expected": "82500",
     "correct": true
    },
    {
     "turn": 3,
     "question": "Great. And when does the pilot start?",
     "tools": "search_knowledge",
     "tool_s": 0.03,
     "hold_source": "model",
     "hold_text": "Let me check that for you.",
     "t_first_audio_s": 1.63,
     "t_answer_s": 3.79,
     "answer": "The Kochi pilot start date is set to 2 December 2026.",
     "expected": "2 december",
     "correct": true
    }
   ]
  }
 },
 "clip": "media/E2/synthesis_fallback.mp3"
};
