# Download the helper library from https://www.twilio.com/docs/python/install
import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# Find your Account SID and Auth Token at twilio.com/console
# and set the environment variables. See http://twil.io/secure
account_sid = os.environ["TWILIO_ACCOUNT_SID2"]
auth_token = os.environ["TWILIO_AUTH_TOKEN2"]
client = Client(account_sid, auth_token)

call = client.calls.create(
    url="https://2b7ace35-09a5-4501-91bd-9497e0dd923a-00-nc15q7dam2tm.sisko.replit.dev/"+"incoming_call",
    to="+917990391454",
    from_="+13802071918",
)
# 19146354195
print(call.sid)

# print(account_sid,",",auth_token)
