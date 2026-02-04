from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

SHOP_NAME = "Daniel Shop"
MPESA_TILL = "123456"
GOOGLE_MAPS_LINK = "https://maps.google.com/?q=-1.286389,36.817223"

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    incoming_msg = request.values.get("Body", "").strip().lower()
    response = MessagingResponse()
    msg = response.message()

    if incoming_msg in ["hi", "hello", "hey"]:
        msg.body(
            f"Karibu {SHOP_NAME}! 👋\n\n"
            "Reply with:\n"
            "1️⃣ Menu\n"
            "2️⃣ Location\n"
            "3️⃣ Order"
        )

    elif incoming_msg == "1":
        msg.body(
            "📋 *Menu*\n"
            "• Chips – KES 150\n"
            "• Chicken – KES 300\n"
            "• Soda – KES 50\n\n"
            f"Pay via M-Pesa Till: *{MPESA_TILL}*"
        )

    elif incoming_msg == "2":
        msg.body(
            "📍 *Our Location*\n"
            f"Click here to open Google Maps:\n{GOOGLE_MAPS_LINK}"
        )

    elif incoming_msg == "3":
        msg.body(
            "🛒 *How to Order*\n"
            "Send your order like this:\n"
            "Example: Chips + Chicken\n\n"
            f"Pay via M-Pesa Till: *{MPESA_TILL}*"
        )

    else:
        msg.body(
            "❓ Sorry, I didn't understand.\n\n"
            "Reply with:\n"
            "1️⃣ Menu\n"
            "2️⃣ Location\n"
            "3️⃣ Order"
        )

    return str(response)

if __name__ == "__main__":
    app.run()
