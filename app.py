"""Local typed demo and Twilio inbound-call adapter."""

import os
import re
import sys
from hmac import compare_digest
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, abort, request
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

from gemini import interpret
from ordering import GREETING, Order, load_menus
from sms import send_confirmation

load_dotenv()


def create_app(menus):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    base_url = os.environ["PUBLIC_BASE_URL"].rstrip("/")
    if not base_url.startswith("https://"):
        raise ValueError("PUBLIC_BASE_URL must start with https://")
    validator = RequestValidator(os.environ["TWILIO_AUTH_TOKEN"])
    demo_phone = os.environ["DEMO_SMS_TO"].strip()
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", demo_phone):
        raise ValueError("DEMO_SMS_TO must be in E.164 format, such as +14695550123")
    speech_hints = ",".join(["checkout", "yes", "no"] + [
        name[:100] for menu in menus.values() for name in menu
    ][:100])
    orders = {}
    trial_key = os.getenv("TWILIO_TRIAL_WEBHOOK_KEY", "")

    @app.post("/voice")
    @app.post("/voice/<int:turn>")
    @app.post("/trial/<key>")
    @app.post("/trial/<key>/<int:turn>")
    def voice(turn=0, key=None):
        signature = request.headers.get("X-Twilio-Signature", "")
        public_url = base_url + request.path
        if request.query_string:
            public_url += "?" + request.query_string.decode("ascii")
        trial_auth = (
            key is not None and trial_key and key.isascii()
            and compare_digest(key, trial_key)
        )
        if not trial_auth and not validator.validate(public_url, request.form, signature):
            app.logger.warning(
                "Twilio signature rejected for %s (signature present: %s, query fields: %s)",
                "trial route" if key else request.path, bool(signature), ",".join(request.args),
            )
            abort(403)
        phone = request.form.get("From")
        call_sid = request.form.get("CallSid", "")
        if phone != demo_phone or not re.fullmatch(r"CA[0-9a-fA-F]{32}", call_sid):
            app.logger.warning(
                "Trial callback metadata: caller matched=%s, valid CallSid=%s, form fields=%s",
                phone == demo_phone, bool(re.fullmatch(r"CA[0-9a-fA-F]{32}", call_sid)),
                ",".join(request.form),
            )
            abort(403)
        if call_sid not in orders:
            if turn:
                abort(404)
            orders[call_sid] = (Order(menus, phone), {})
        order, responses = orders[call_sid]
        if turn in responses:
            return Response(responses[turn], mimetype="application/xml")
        if turn != len(responses):
            abort(409)

        response = VoiceResponse()
        if turn == 0:
            reply = order.say(GREETING)
        else:
            speech = request.form.get("SpeechResult", "")
            reply = advance(order, speech)
        if order.stage == "confirmed":
            sent = send_confirmation(order.phone, order.confirmation_text())
            reply += (" Look for your confirmation text."
                      if sent else " The confirmation is available in the demo preview.")
            order.transcript[-1]["assistant"] = reply
            try:
                folder = order.save()
                app.logger.info("Saved order artifacts to %s", folder)
            except OSError:
                app.logger.error("Could not write artifacts for %s", order.order_id)
            response.say(reply)
            response.hangup()
        else:
            gather = Gather(
                input="speech",
                action=f"{base_url}{'/trial/' + trial_key if trial_auth else '/voice'}/{turn + 1}",
                method="POST",
                speech_timeout="auto", timeout=5, action_on_empty_result=True,
                hints=speech_hints,
            )
            gather.say(reply)
            response.append(gather)
        responses[turn] = str(response)
        app.logger.info("Voice turn %d handled, stage=%s", turn, order.stage)
        return Response(responses[turn], mimetype="application/xml")

    return app


def advance(order, speech):
    try:
        return order.advance(speech, interpret)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        print(f"Could not interpret turn ({type(error).__name__}).", file=sys.stderr)
        return order.say("Sorry, I couldn't look up the menu. Please try that again.")


def run_chat(menus):
    print("Typed demo. Use demo customer details. SMS is previewed.")
    order = Order(menus, "+14695550123")
    print(order.say(GREETING))
    while order.stage != "confirmed":
        try:
            speech = input("> ")
        except (EOFError, KeyboardInterrupt):
            return
        print(advance(order, speech))
    print(order.confirmation_text())
    print(f"Saved submission artifacts to {order.save()}")


if __name__ == "__main__":
    if "--live" in sys.argv[1:] or sys.argv[1:] in ([], ["chat"]):
        if not os.getenv("GEMINI_API_KEY"):
            sys.exit("Set GEMINI_API_KEY in .env first, or run: python app.py web")
    sample = "menus.sample.json"
    default_menu = "menus.json" if Path("menus.json").exists() else sample
    menu_path = os.getenv("MENU_FILE", default_menu)
    print(f"Loading menu from {menu_path}")
    menus = load_menus(menu_path)
    if sys.argv[1:] in (["web"], ["web", "--live"]):
        from web import create_web_app

        port = int(os.getenv("PORT", "5055"))
        create_web_app(menus, live="--live" in sys.argv).run(
            host="127.0.0.1", port=port, threaded=False
        )
    elif sys.argv[1:] == ["chat"]:
        run_chat(menus)
    elif not sys.argv[1:]:
        import logging

        # Werkzeug access logs include the private trial callback URL.
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        port = int(os.getenv("PORT", "5055"))
        create_app(menus).run(host="127.0.0.1", port=port, threaded=False)
    else:
        sys.exit("Usage: python app.py [chat | web [--live]]")
