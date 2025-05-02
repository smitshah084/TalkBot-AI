import os
from twilio.rest import Client

account_sid = "AC9f5e03e8c3fef8e608b73f802cb73533"
auth_token = "a60110258ffb6f3168af20830389c839"
client = Client(account_sid, auth_token)

call = client.calls.create(
  url="https://35cc-2409-40c1-4017-7f96-19d2-eedc-9869-687e.ngrok-free.app/answer",
  to="+917990391454",
  from_="+13802071918"
)

print(call.sid)