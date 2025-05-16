Commited:
- session management with LLM
- stream output of LLM
- Interupt LLM's response genaration

On this Commit:
- rewrote whole STT from scracth

TO-DOs:
- write main which exposes websocket for web
- write simple index.html which records audio and desplayes incomming text
- integrate index and main
- rewrite LLM
- integrate LLM and main
- update index to interact with LLM
- rewrite TTS
- integrate TTS and main
- update index to stream audio output
- 

Idea:
1. PS: Stream LLM's input

        Challenge: To have continuous asynchronous conversation with llm where user can interupt and LLM can not
        
        SOl: let LLM start genarateing resposne after a enter is pressed. detect the completion of user input using VAD on audio before STT.

2. Genral Project data flow:
        twilio connects call
        audio stream from call as input to STT and VAD models
        text stream from STT and signal from VAD as input to LLM
        LLM streams text as input to TTS
        audio stream from TTS as outgoing voice to twilio

        
        