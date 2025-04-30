Commited:
- session management with LLM
- stream output of LLM

On this Commit:
- Interupt LLM's response genaration

TO-DOs:
- Stream LLM's input

Idea:
1. PS: Stream LLM's input

        Challenge: To have continuous asynchronous conversation with llm where user can interupt and LLM can not
        
        SOl: let LLM start genarateing resposne after a enter is pressed. detect the completion of user input using VAD on audio before STT.

        
        