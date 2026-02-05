from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import json

app = Flask(__name__)

def load_clients():
    with open("clients.json") as f:
        return json.load(f)

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    clients = load_clients()

    incoming_msg = request.values.get("Body", "").strip().lower()
    to_number = request.values.get("To")

    client = clients.get(to_number)

    response = MessagingResponse()
    msg = response.message()

    if not client:
        msg.body("❌ This WhatsApp number is not registered.")
        return str(response)

    shop = client["shop_name"]
    till = client["mpesa_till"]
    maps = client["maps_link"]

    if incoming_msg in ["hi", "hello"]:
        msg.body(
            f"Karibu {shop}! 👋\n\n"
            "Reply with:\n"
            "1️⃣ Menu\n"
            "2️⃣ Location\n"
            "3️⃣ Order"
        )

    elif incoming_msg == "2":
        msg.body(f"📍 {shop} Location:\n{maps}")

    elif incoming_msg == "1":
        msg.body(
            f"📋 {shop} Menu\n"
            "• Chips – KES 150\n"
            "• Chicken – KES 300\n\n"
            f"M-Pesa Till: *{till}*"
        )

    elif incoming_msg == "3":
        msg.body(
            f"🛒 Send your order.\n"
            f"Pay via M-Pesa Till: *{till}*"
        )

    else:
        msg.body("Reply with 1, 2 or 3.")

    return str(response)
