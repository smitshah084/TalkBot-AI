from STT import SpeechToText
from LLM import ChatSystem
import time
import signal
import sys

def main():
    # Initialize the chat system
    chat = ChatSystem()
    
    # Initialize STT with callback to chat system
    stt = SpeechToText(on_transcription=chat.handle_voice_input)
    
    # Start both systems
    if not stt.start():
        print("Failed to start STT system")
        return
    
    chat_threads = chat.start()
    
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        print("\nShutting down...")
        stt.stop()
        chat.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    print("System ready! You can now speak or type.")
    print("Press Ctrl+C to exit")
    
    # Keep main thread alive
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()
