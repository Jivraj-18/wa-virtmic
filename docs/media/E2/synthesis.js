window.RUNS = window.RUNS || {};
window.RUNS["E2/synthesis"] = {
 "transcript": [
  {
   "t": 0.43,
   "end": 5.36,
   "who": "AGENT",
   "text": "Hello, this is the Kestrel K2 Program Team Assistant. How can I support you today?"
  },
  {
   "t": 6.97,
   "end": 9.71,
   "who": "CALLER",
   "text": "Hello, yes, I can hear you."
  },
  {
   "t": 10.51,
   "end": 15.38,
   "who": "AGENT",
   "text": "Great, I can hear you too. What do you need help with regarding the K2 program?"
  },
  {
   "t": 16.96,
   "end": 18.89,
   "who": "CALLER",
   "text": "I'm from the finance team."
  },
  {
   "t": 19.39,
   "end": 27.74,
   "who": "CALLER",
   "text": "Can you work out the total first-year cost for all the drones in the Kochi pilot on the fleet plan, including the extended warranty?"
  },
  {
   "t": 28.24,
   "end": 30.35,
   "who": "CALLER",
   "text": "Please check all the documents."
  },
  {
   "t": 32.08,
   "end": 34.79,
   "who": "AGENT",
   "text": "Give me a moment. I'm checking the documents."
  },
  {
   "t": 38.56,
   "end": 46.22,
   "who": "AGENT",
   "text": "The total first year cost for all drones in the Kochi Pilot, including extended warranty, is $82,500."
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Hello, yes, I can hear you.",
   "interrupt": "False",
   "caller_start_s": "7.16",
   "caller_end_s": "9.5",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.22",
   "reply_duration_s": "4.44"
  },
  {
   "turn": "2",
   "caller_text": "I'm from the finance team. Can you work out the total first-year cost for all the drones in the Kochi pilot, on the Fleet plan, including the extended warranty? Please check all the documents.",
   "interrupt": "False",
   "caller_start_s": "17.16",
   "caller_end_s": "30.12",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "2.16",
   "reply_duration_s": "2.3"
  },
  {
   "turn": "3",
   "caller_text": "Great. And when does the pilot start?",
   "interrupt": "False",
   "caller_start_s": "68.06",
   "caller_end_s": "71.08",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.22",
   "reply_duration_s": "5.16"
  },
  {
   "turn": "4",
   "caller_text": "Thanks, that's all. Bye!",
   "interrupt": "False",
   "caller_start_s": "85.54",
   "caller_end_s": "87.96",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.14",
   "reply_duration_s": "1.5"
  }
 ],
 "summary": {
  "script": "synthesis",
  "tag": "E2",
  "turns": 4,
  "agent_cmd": "{python} scripts/tools.py agent --context experiments/E2/context --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 4,
  "latency_median_s": 1.22,
  "latency_p90_s": 1.878,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0,
  "e2": {
   "tool_turns": 2,
   "tool_calls": 2,
   "first_audio_median_s": 1.69,
   "answer_median_s": 5.86,
   "answer_max_s": 8.66,
   "correct": 2,
   "checked": 2,
   "rows": [
    {
     "turn": 2,
     "question": "I'm from the finance team. Can you work out the total first-year cost for all the drones in the Kochi pilot, on the Fleet plan, including the extended warranty? Please check all the documents.",
     "tools": "ask_agent",
     "tool_s": 6.57,
     "hold_source": "forced",
     "hold_text": "Give me a moment, I'm checking the documents.",
     "t_first_audio_s": 2.16,
     "t_answer_s": 8.66,
     "answer": "The total first-year cost for all drones in the Kochi pilot, including extended warranty, is $82,500.",
     "expected": "82500",
     "correct": true
    },
    {
     "turn": 3,
     "question": "Great. And when does the pilot start?",
     "tools": "search_knowledge",
     "tool_s": 0.02,
     "hold_source": "model",
     "hold_text": "Let me check that for you.",
     "t_first_audio_s": 1.22,
     "t_answer_s": 3.06,
     "answer": "The Kochi pilot is set to start on 2 December 2026.",
     "expected": "2 december",
     "correct": true
    }
   ]
  }
 },
 "clip": "media/E2/synthesis.mp3"
};
