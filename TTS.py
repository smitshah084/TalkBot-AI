from RealtimeTTS import TextToAudioStream, OpenAIEngine
from LLM import OpenAIRealtimeChat
from STT import STT
        
stt = STT()
_, full_transcript_stream = stt.start()

chat_client = OpenAIRealtimeChat(
    input_mode="stream",
    input_stream=full_transcript_stream,
    stt_instance=stt
)

class TTS:
    def __init__(self,stt_instance):
        self.buffer = []
        self.stt_instance = stt_instance
        self.stream = None
        self.is_speaking = False
        
        if self.stt_instance:
            self.stt_instance.register_event_handler("speech_started", self.on_speech_started)
            self.stt_instance.register_event_handler("speech_stopped",self.on_speech_stopped)
            
    def on_speech_started(self,time):
        if self.stream:
            self.stream.pause()
        self.is_speaking = True
    
    def on_speech_stopped(self,time):
        if self.stream:
            self.stream.resume()
        self.is_speaking = False
        
        
    def process_stream(self, input_stream):
        """
        Process input stream and yield buffered text
        """        
        for token in input_stream:
                # print(token)
                yield token
                
    def realtime_show(self,frag):
        '''
        Show what is said right now
        '''
        # print(frag)
        pass
            
    def run(self,chat_stream):
        buffered_stream = self.process_stream(chat_stream())

        engine = OpenAIEngine(model="tts-1", voice="nova")
        self.stream = TextToAudioStream(engine)  # Store stream reference
        self.stream.feed(buffered_stream)

        print("Synthesizing...")
        self.stream.play_async(
            on_sentence_synthesized=self.realtime_show,
            log_synthesized_text=False,
            minimum_sentence_length=2
        )

tts = TTS(stt_instance=stt)
tts.run(chat_client.run)