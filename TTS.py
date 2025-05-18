from RealtimeTTS import TextToAudioStream, OpenAIEngine
from LLM import OpenAIRealtimeChat
from STT import STT

def dummy_generator():
    yield "Hey guys! "
    yield "These here are "
    yield "realtime spoken words "
    yield "based on openai "
    yield "tts text synthesis."

        
stt = STT()

# Start STT and get the full transcript stream
_, full_transcript_stream = stt.start()

# Create and run the chat client with the stream
chat_client = OpenAIRealtimeChat(
    input_mode="stream",
    input_stream=full_transcript_stream,
    stt_instance=stt
)

engine = OpenAIEngine(model="tts-1", voice="nova")
stream = TextToAudioStream(engine)

stream.feed(chat_client.run())

print("Synthesizing...")
stream.play()