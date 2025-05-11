from fastapi import APIRouter, Response
from twilio.twiml.voice_response import VoiceResponse

router = APIRouter()

@router.get("/answer")
def read_root():
        resp = VoiceResponse()
        resp.say("Thank you for calling! Have a great day.", voice='Polly.Amy')
        return Response(content=str(resp), media_type="application/xml")