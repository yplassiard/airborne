from airborne.audio.tts.pyttsx_provider import PyTTSXProvider

tts = PyTTSXProvider()
tts.initialize({"rate": 200, "volume": 1.0})
print("TTS initialized")
tts.speak("Test message", interrupt=True)
print("Speak called")
import time

time.sleep(3)
print("Done")
