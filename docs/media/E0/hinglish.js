window.RUNS = window.RUNS || {};
window.RUNS["E0/hinglish"] = {
 "transcript": [
  {
   "t": 1.78,
   "end": 5.9,
   "who": "AGENT",
   "text": "Hello, this is your AI assistant on a test call. Can you hear me clearly?"
  },
  {
   "t": 7.57,
   "end": 9.5,
   "who": "CALLER",
   "text": "हाँ आवाज आ रही है।"
  },
  {
   "t": 10.21,
   "end": 13.97,
   "who": "AGENT",
   "text": "Great, I'm glad you can hear me. How can I assist you today?"
  },
  {
   "t": 15.58,
   "end": 16.76,
   "who": "CALLER",
   "text": "آپ کون ہو?"
  },
  {
   "t": 17.32,
   "end": 19.85,
   "who": "CALLER",
   "text": "क्या आप हिंदी में बात कर सकते हो?"
  },
  {
   "t": 20.56,
   "end": 25.22,
   "who": "AGENT",
   "text": "ज़रूर, मैं हिंदी में बात कर सकता हूँ। बताइए, क्या मदद चाहिए?"
  },
  {
   "t": 26.86,
   "end": 29.24,
   "who": "CALLER",
   "text": "अच्छा, मुझे कल दिल्ली जाना है।"
  },
  {
   "t": 30.01,
   "end": 30.83,
   "who": "AGENT",
   "text": "بالكل."
  },
  {
   "t": 30.34,
   "end": 32.84,
   "who": "CALLER",
   "text": "वेधर कैसा रहता है नवंबर में?"
  },
  {
   "t": 33.64,
   "end": 40.82,
   "who": "AGENT",
   "text": "नवंबर में दिल्ली का मौसम आम तौर पर सुहावना रहता है। सुबहें ठंडी और दिन हल्के गर्म होते हैं।"
  },
  {
   "t": 42.43,
   "end": 44.09,
   "who": "CALLER",
   "text": "ٹھیک ہے."
  },
  {
   "t": 44.71,
   "end": 45.38,
   "who": "CALLER",
   "text": "Bye"
  },
  {
   "t": 46.21,
   "end": 48.74,
   "who": "AGENT",
   "text": "ٹھیک ہے، پھر ملتے ہیں, الوداع۔"
  }
 ],
 "metrics": [
  {
   "turn": "1",
   "caller_text": "Haan, awaaz aa rahi hai.",
   "interrupt": "False",
   "caller_start_s": "7.8",
   "caller_end_s": "9.28",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.14",
   "reply_duration_s": "3.34"
  },
  {
   "turn": "2",
   "caller_text": "Aap kaun ho? Kya aap Hindi mein baat kar sakte ho?",
   "interrupt": "False",
   "caller_start_s": "15.78",
   "caller_end_s": "19.64",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.14",
   "reply_duration_s": "4.24"
  },
  {
   "turn": "3",
   "caller_text": "Accha, mujhe kal Delhi jaana hai. Weather kaisa rehta hai November mein?",
   "interrupt": "False",
   "caller_start_s": "27.04",
   "caller_end_s": "32.64",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.2",
   "reply_duration_s": "6.78"
  },
  {
   "turn": "4",
   "caller_text": "Theek hai, thank you. Bye!",
   "interrupt": "False",
   "caller_start_s": "42.64",
   "caller_end_s": "45.18",
   "agent_talking_at_caller_start": "False",
   "agent_stop_latency_s": "",
   "first_audio_latency_s": "1.24",
   "reply_duration_s": "2.12"
  }
 ],
 "summary": {
  "script": "hinglish",
  "tag": "E0",
  "turns": 4,
  "agent_cmd": "{python} scripts/realtime_agent.py --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}",
  "replied_turns": 4,
  "latency_median_s": 1.17,
  "latency_p90_s": 1.228,
  "interruptions": 0,
  "barge_in_stop_median_s": null,
  "barge_ins_handled": 0
 },
 "clip": "media/E0/hinglish.mp3"
};
