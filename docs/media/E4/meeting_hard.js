window.RUNS = window.RUNS || {};
window.RUNS["E4/meeting_hard"] = {
 "transcript": [
  {
   "t": 1.63,
   "end": 2.81,
   "who": "CALLER",
   "text": "Morning all"
  },
  {
   "t": 3.4,
   "end": 7.46,
   "who": "CALLER",
   "text": "Agenda today is the database migration and the rollout plan for Friday."
  },
  {
   "t": 12.88,
   "end": 16.88,
   "who": "CALLER",
   "text": "Maria, can you share your screen with the migration checklist?"
  },
  {
   "t": 22.33,
   "end": 24.02,
   "who": "CALLER",
   "text": "Sure, sharing now."
  },
  {
   "t": 24.58,
   "end": 28.28,
   "who": "CALLER",
   "text": "Steps one to four are done, step five is the data backfill."
  },
  {
   "t": 33.79,
   "end": 37.7,
   "who": "CALLER",
   "text": "What do you all think, is the backfill safe to run during business hours?"
  },
  {
   "t": 43.21,
   "end": 48.47,
   "who": "CALLER",
   "text": "Maya's summary from last week said the backfill locks the Orders table for a few minutes."
  },
  {
   "t": 53.41,
   "end": 58.79,
   "who": "CALLER",
   "text": "Okay Maya, quick one, how long would a rollback take if the backfill fails?"
  },
  {
   "t": 60.25,
   "end": 72.23,
   "who": "AGENT",
   "text": "Based on what I know, a rollback could take around the same time as the changes made so far, maybe a few minutes if the backfill is partway. But it depends on the volume of data changed; larger sets can cause longer rollbacks."
  },
  {
   "t": 73.9,
   "end": 74.75,
   "who": "CALLER",
   "text": "Right."
  },
  {
   "t": 75.34,
   "end": 78.68,
   "who": "CALLER",
   "text": "Ravi, what do you think, can we run it at night instead?"
  },
  {
   "t": 84.13,
   "end": 85.43,
   "who": "CALLER",
   "text": "Night is fine."
  },
  {
   "t": 85.99,
   "end": 90.89,
   "who": "CALLER",
   "text": "I think Maya and the on-call team should get the runbook before Friday."
  },
  {
   "t": 96.34,
   "end": 101.45,
   "who": "CALLER",
   "text": "Maya, can you walk us through a step-by-step rollout plan for Friday, with all the checkpoints?"
  },
  {
   "t": 102.91,
   "end": 106.43,
   "who": "AGENT",
   "text": "Sure, let's outline the rollout plan step by step."
  },
  {
   "t": 106.18,
   "end": 113.33,
   "who": "CALLER",
   "text": "Wait, wait. Ravi, sorry, quick question for you. Is the staging copy of the database ready?"
  },
  {
   "t": 118.27,
   "end": 121.55,
   "who": "CALLER",
   "text": "Yes, staging was refreshed this morning."
  },
  {
   "t": 127.09,
   "end": 130.64,
   "who": "CALLER",
   "text": "Can you ask Maya to send the checklist to everyone after the call?"
  },
  {
   "t": 136.12,
   "end": 139.4,
   "who": "CALLER",
   "text": "What would you recommend as the go or no-go signal, Maya?"
  },
  {
   "t": 140.92,
   "end": 157.04,
   "who": "AGENT",
   "text": "A good go or no-go signal could be successful completion of the data backfill on the staging environment, with no critical errors, and confirmation from the team that performance and order processing remain stable. Once we tick those boxes, we can safely proceed."
  },
  {
   "t": 158.74,
   "end": 159.5,
   "who": "CALLER",
   "text": "Good"
  },
  {
   "t": 160.06,
   "end": 161.51,
   "who": "CALLER",
   "text": "Let's wrap up there."
  },
  {
   "t": 162.19,
   "end": 163.43,
   "who": "CALLER",
   "text": "Thanks everyone!"
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Morning all. Agenda today is the database migration and the rollout plan for Friday.",
   "interrupt": "False",
   "caller_start_s": "1.82",
   "caller_end_s": "7.24",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  },
  {
   "turn": "2",
   "caller_text": "Maria, can you share your screen with the migration checklist?",
   "interrupt": "False",
   "caller_start_s": "13.08",
   "caller_end_s": "16.66",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  },
  {
   "turn": "3",
   "caller_text": "Sure, sharing now. Steps one to four are done, step five is the data backfill.",
   "interrupt": "False",
   "caller_start_s": "22.52",
   "caller_end_s": "28.08",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  },
  {
   "turn": "4",
   "caller_text": "What do you all think, is the backfill safe to run during business hours?",
   "interrupt": "False",
   "caller_start_s": "34.0",
   "caller_end_s": "37.5",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  },
  {
   "turn": "5",
   "caller_text": "Maya's summary from last week said the backfill locks the orders table for a few minutes.",
   "interrupt": "False",
   "caller_start_s": "43.42",
   "caller_end_s": "48.28",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  },
  {
   "turn": "6",
   "caller_text": "Okay, Maya, quick one: how long would a rollback take if the backfill fails?",
   "interrupt": "False",
   "caller_start_s": "53.62",
   "caller_end_s": "58.6",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.86",
   "reply_duration_s": "11.58"
  },
  {
   "turn": "7",
   "caller_text": "Right. Ravi, what do you think, can we run it at night instead?",
   "interrupt": "False",
   "caller_start_s": "74.1",
   "caller_end_s": "78.48",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  },
  {
   "turn": "8",
   "caller_text": "Night is fine. I think Maya and the on-call team should get the runbook before Friday.",
   "interrupt": "False",
   "caller_start_s": "84.32",
   "caller_end_s": "90.68",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  },
  {
   "turn": "9",
   "caller_text": "Maya, can you walk us through a step by step rollout plan for Friday, with all the checkpoints?",
   "interrupt": "False",
   "caller_start_s": "96.54",
   "caller_end_s": "101.26",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.86",
   "reply_duration_s": "3.1"
  },
  {
   "turn": "10",
   "caller_text": "Wait, wait. Ravi, sorry, quick question for you: is the staging copy of the database ready?",
   "interrupt": "True",
   "caller_start_s": "106.38",
   "caller_end_s": "113.14",
   "agent_talking_at_caller_start": "True",
   "agent_stop_latency_s": "0.0",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  },
  {
   "turn": "11",
   "caller_text": "Yes, staging was refreshed this morning.",
   "interrupt": "False",
   "caller_start_s": "118.46",
   "caller_end_s": "121.34",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  },
  {
   "turn": "12",
   "caller_text": "Can you ask Maya to send the checklist to everyone after the call?",
   "interrupt": "False",
   "caller_start_s": "127.28",
   "caller_end_s": "130.42",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  },
  {
   "turn": "13",
   "caller_text": "What would you recommend as the go or no-go signal, Maya?",
   "interrupt": "False",
   "caller_start_s": "136.32",
   "caller_end_s": "139.2",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.92",
   "reply_duration_s": "15.74"
  },
  {
   "turn": "14",
   "caller_text": "Good. Let's wrap up there. Thanks everyone.",
   "interrupt": "False",
   "caller_start_s": "158.92",
   "caller_end_s": "163.24",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "",
   "reply_duration_s": ""
  }
 ],
 "summary": {
  "script": "meeting_hard",
  "tag": "E4",
  "turns": 14,
  "agent_cmd": "{python} -u -m scripts.meet.maya agent --in-device {in_device} --out-device {out_device} --transcript {transcript} --seconds {seconds} --suggest-first 30 --suggest-interval 45 --suggest-check 5",
  "replied_turns": 3,
  "latency_median_s": 1.86,
  "latency_p90_s": 1.908,
  "interruptions": 1,
  "barge_in_stop_median_s": 0.0,
  "barge_ins_handled": 1,
  "addressed_lines": 3,
  "addressed_turns": [
   6,
   9,
   13
  ],
  "addressed_answered": 3,
  "not_addressed_lines": 11,
  "false_triggers": 0,
  "false_trigger_turns": [],
  "false_trigger_rate": 0.0,
  "addressed_latency_median_s": 1.86,
  "addressed_latency_max_s": 1.92,
  "addressed_latencies_s": [
   1.86,
   1.86,
   1.92
  ],
  "barge_in_stop_s": 0.0,
  "early_triggers": 2,
  "chat_suggestions": [
   "Maybe consider running the backfill on a small dataset first to monitor impact before full execution.",
   "Maybe schedule a short monitoring window right after the backfill starts to quickly catch any issues.",
   "Maybe confirm a rollback test on staging before Friday to ensure rollback time estimates are accurate.",
   "Maybe set a specific time to review staging backfill results together before Friday’s rollout."
  ],
  "barge_in_events": [
   "local_vad"
  ]
 },
 "clip": "media/E4/meeting_hard.mp3"
};
