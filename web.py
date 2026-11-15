"""Local presentation UI. Rehearsal never calls an external service or sends SMS."""

import re
import secrets
from collections import OrderedDict

from flask import Flask, abort, jsonify, render_template, request

from gemini import interpret
from ordering import FREE_OVER, Order, price_cents

WELCOME = (
    "Hey, welcome to 334 Food Now! Craving a little of everything? "
    "Order across our restaurants in one conversation. What sounds good?"
)


def rehearse(menus, cart, speech, history=()):
    """Small, deliberately limited menu matcher for a key-free presentation."""
    text = speech.lower()
    items = []
    matches = []
    for restaurant, menu in menus.items():
        for name, item in menu.items():
            alias = re.sub(r"\s*\(.*?\)", "", name.lower())
            # Tolerate plural menu names and the sample script's "biryanis".
            pattern = r"\b" + r"\s+".join(
                re.escape(word.rstrip("s")) + r"s?" for word in alias.split()
            ) + r"\b"
            match = re.search(pattern, text)
            if not match:
                short = alias.split()[-1].rstrip("s")
                if sum(short in n.lower() for m in menus.values() for n in m) == 1:
                    match = re.search(r"\b" + re.escape(short) + r"s?\b", text)
            if match:
                matches.append((match.start(), restaurant, name, match, item))
    browsing = bool(re.search(r"\b(menu|have|recommend|vegetarian|veggie options|price|cost|what)\b", text))
    ordering = bool(re.search(r"\b(add|order|get|want|take|i ll|i'd like)\b", text))
    if matches and (ordering or not browsing):
        numbers = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        for _, restaurant, name, match, item in sorted(matches, key=lambda row: row[0]):
            quantity_match = re.search(r"(\d+|a|an|one|two|three|four|five)\s+$", text[:match.start()])
            value = quantity_match.group(1) if quantity_match else "one"
            quantity = int(value) if value.isdecimal() else numbers[value]
            notes = "mild" if "mild" in text and "biryani" in name.lower() else ""
            if notes and quantity > 1 and re.search(r"one mild", text):
                items.append(dict(restaurant=restaurant, name=name, quantity=1, notes=notes))
                quantity -= 1
                notes = ""
            items.append(dict(restaurant=restaurant, name=name, quantity=quantity, notes=notes))
        return {"items": items, "menu_answer": ""}
    if re.search(r"\b(delivery|total|subtotal)\b", text) and cart:
        return {"items": [], "menu_answer": ""}
    selected = [(r, n, i) for r, menu in menus.items() for n, i in menu.items()]
    cuisine = [r for r in menus if r.lower() in text]
    if cuisine:
        selected = [row for row in selected if row[0] in cuisine]
    if "vegetarian" in text or "veggie" in text:
        selected = [row for row in selected if "veg" in row[2].get("tags", [])]
    if matches and browsing:
        selected = [(r, n, i) for _, r, n, _, i in matches]
    if browsing or cuisine:
        answer = "; ".join(f"{n} from {r} (${price_cents(i) / 100:.2f})" for r, n, i in selected)
        return {"items": [], "menu_answer": answer or "No matching options are listed in this menu."}
    return {"items": [], "menu_answer": "In rehearsal mode, use a dish name or tap Add on the menu. Try ‘two chicken biryanis and a penne Alfredo’."}


def create_web_app(menus, live=False):
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(32)
    app.config.update(MAX_CONTENT_LENGTH=16 * 1024)
    sessions = OrderedDict()

    def current():
        sid = request.cookies.get("food_session")
        if sid not in sessions:
            abort(409, "Session expired. Reload the page to start a new order.")
        sessions.move_to_end(sid)
        return sessions[sid]

    def state(order):
        return dict(
            cart=order.cart, totals=order.totals(), stage=order.stage,
            transcript=order.transcript, order_id=order.order_id,
            confirmation=order.confirmation_text() if order.stage == "confirmed" else None,
            mode="Gemini live" if live else "Rehearsal", free_over=FREE_OVER,
        )

    @app.before_request
    def protect_mutations():
        if request.method == "POST":
            order, token = current()
            if not secrets.compare_digest(request.headers.get("X-Demo-Token", ""), token):
                abort(403)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        return response

    @app.errorhandler(409)
    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(413)
    def api_error(error):
        return jsonify(error=error.description), error.code

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/session")
    def session_state():
        sid = request.cookies.get("food_session")
        if sid not in sessions:
            sid = secrets.token_hex(24)
            order = Order(menus, "+14695550123", preview_only=True)
            order.say(WELCOME)
            sessions[sid] = (order, secrets.token_hex(24))
            while len(sessions) > 128:
                sessions.popitem(last=False)
        order, token = sessions[sid]
        sessions.move_to_end(sid)
        response = jsonify(**state(order), menus=menus, token=token)
        response.set_cookie("food_session", sid, httponly=True, samesite="Strict")
        return response

    @app.post("/api/message")
    def message():
        order, _ = current()
        data = request.get_json(silent=True)
        speech = data.get("message") if isinstance(data, dict) else None
        if not isinstance(speech, str) or not speech.strip() or len(speech) > 1000:
            abort(400, "Enter a message between 1 and 1,000 characters.")
        previous = order.stage
        try:
            order.advance(speech, interpret if live else rehearse)
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            order.say("I couldn't reach the menu assistant. Please try again, or use Add on the menu.")
        if previous != "confirmed" and order.stage == "confirmed":
            try:
                order.save()
            except OSError:
                app.logger.warning("Could not save local demo artifacts")
        return jsonify(state(order))

    @app.post("/api/cart")
    def cart():
        order, _ = current()
        if order.stage != "cart":
            abort(409, "Finish checkout or go back before changing your order.")
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            abort(400, "Choose a menu item.")
        restaurant, name = data.get("restaurant"), data.get("name")
        if not isinstance(restaurant, str) or not isinstance(name, str) or name not in menus.get(restaurant, {}):
            abort(400, "That dish isn't on the menu.")
        if data.get("action") == "remove":
            lines = order.cart.get(restaurant, [])
            order.cart[restaurant] = [line for line in lines if line["name"] != name]
            if not order.cart[restaurant]:
                order.cart.pop(restaurant)
            order.say(f"Removed {name} from your order.")
        else:
            order.add_items([dict(restaurant=restaurant, name=name, quantity=1)])
            order.say(f"Added {name}. {order.delivery_summary()}")
        return jsonify(state(order))

    @app.post("/api/reset")
    def reset():
        _, token = current()
        order = Order(menus, "+14695550123", preview_only=True)
        order.say(WELCOME)
        sessions[request.cookies["food_session"]] = (order, token)
        return jsonify(state(order))

    return app
