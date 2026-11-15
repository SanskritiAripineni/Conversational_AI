"""Cart, prices and checkout state shared by typed chat and the phone call."""

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

GREETING = "Welcome to 334 Food Now. What would you like to order?"
FREE_OVER = 5000
DELIVERY_FEE = 499


def money(cents):
    return f"${cents / 100:.2f}"


def load_menus(path):
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict) and "restaurants" in data:
        data = data["restaurants"]
    if isinstance(data, list):
        data = {restaurant["name"]: restaurant["items"] for restaurant in data}

    menus = {}
    for restaurant, menu in data.items():
        if isinstance(menu, dict) and "items" in menu:
            menu = menu["items"]
        if isinstance(menu, dict):
            menu = [
                {"name": name, **(item if isinstance(item, dict) else {"price": item})}
                for name, item in menu.items()
            ]
        menus[restaurant] = {item["name"]: item for item in menu}
    if not menus or not all(menus.values()):
        raise ValueError("Menu must contain restaurants with menu items")
    return menus


def price_cents(item):
    return int((Decimal(str(item["price"])) * 100).quantize(Decimal("1"), ROUND_HALF_UP))


@dataclass
class Order:
    menus: dict
    phone: str = ""
    cart: dict = field(default_factory=dict)
    transcript: list = field(default_factory=list)
    name: str = ""
    address: str = ""
    stage: str = "cart"
    order_id: str = field(default_factory=lambda: uuid4().hex[:8].upper())
    ordering_history: list = field(default_factory=list)
    preview_only: bool = False

    def say(self, text):
        self.transcript.append({"assistant": text})
        return text

    def totals(self):
        subtotal = sum(
            line["quantity"] * line["unit_price_cents"]
            for lines in self.cart.values() for line in lines
        )
        tax = int((Decimal(subtotal) * Decimal("0.0825")).quantize(
            Decimal("1"), ROUND_HALF_UP
        ))
        delivery = 0 if subtotal > FREE_OVER else DELIVERY_FEE
        return {
            "subtotal_cents": subtotal,
            "tax_cents": tax,
            "delivery_cents": delivery,
            "total_cents": subtotal + tax + delivery,
        }

    def delivery_summary(self):
        totals = self.totals()
        subtotal = totals["subtotal_cents"]
        if totals["delivery_cents"] == 0:
            return f"Food is {money(subtotal)} and delivery is free."
        needed = FREE_OVER + 1 - subtotal
        options = sorted(
            (price_cents(item), name, restaurant)
            for restaurant, menu in self.menus.items() for name, item in menu.items()
            if price_cents(item) >= needed
        )
        message = (
            f"Food is {money(subtotal)}. Delivery is ${DELIVERY_FEE / 100:.2f}, "
            f"or free if you add at least {money(needed)}."
        )
        if options:
            price, name, restaurant = options[0]
            message += f" {name} from {restaurant} for {money(price)} would get you there."
        return message

    def add_items(self, items):
        added = []
        for item in items:
            if not isinstance(item, dict):
                continue
            restaurant = item.get("restaurant")
            name = item.get("name")
            quantity = item.get("quantity")
            if not isinstance(restaurant, str) or not isinstance(name, str):
                continue
            menu_item = self.menus.get(restaurant, {}).get(name)
            if menu_item is None or type(quantity) is not int or not 1 <= quantity <= 20:
                continue
            notes = item.get("notes")
            notes = notes[:100] if isinstance(notes, str) else ""
            line = {
                "name": name, "quantity": quantity,
                "unit_price_cents": price_cents(menu_item), "notes": notes,
            }
            self.cart.setdefault(restaurant, []).append(line)
            added.append(self.describe(line))
        return added

    @staticmethod
    def describe(line):
        suffix = f", {line['notes']}" if line["notes"] else ""
        return f"{line['quantity']} {line['name']}{suffix}"

    def readback(self):
        details = ". ".join(
            f"From {restaurant}, " + "; ".join(self.describe(line) for line in lines)
            for restaurant, lines in self.cart.items()
        )
        confirmation = (
            "Confirm this demo order? No text will be sent. " if self.preview_only else
            f"Send the confirmation to the number ending in {' '.join(self.phone[-4:])}? "
        )
        return (
            f"{self.name}, here is your order. {details}. Deliver to {self.address}. "
            f"Total including tax and delivery is {money(self.totals()['total_cents'])}. "
            f"{confirmation}"
            "Say yes to confirm, or no to go back."
        )

    def advance(self, speech, interpret):
        speech = speech.strip()
        if not speech:
            return self.say("I didn't catch that. Please repeat.")
        self.transcript.append({"customer": speech})
        choice = " ".join(re.findall(r"[a-z]+", speech.lower()))

        if self.stage == "confirmed":
            return self.say("Your order is already confirmed.")
        if self.stage == "confirm":
            if choice in {
                "yes", "yes please", "yes confirm", "yes that s correct",
                "yes that is correct", "yeah", "yep", "correct", "that s correct",
                "yep that s right", "yeah that s right", "yes that s right",
            }:
                self.stage = "confirmed"
                return self.say(f"Order {self.order_id} is confirmed. Thank you!")
            if choice in {"no", "nope", "go back", "no go back"}:
                self.stage = "cart"
                return self.say("Okay. Anything to add? Say checkout when you're ready.")
            return self.say("Please say yes to confirm or no to go back.")
        if self.stage == "name":
            self.name = speech
            self.stage = "address"
            return self.say("What is your delivery address?")
        if self.stage == "address":
            self.address = speech
            self.stage = "confirm"
            return self.say(self.readback())
        if choice in {
            "checkout", "check out", "done", "that s all", "that is all",
            "i m ready to check out", "i m ready to checkout", "that s it",
            "check out please", "checkout please", "that s everything",
            "i m ready to pay", "ready to check out", "ready to checkout",
        }:
            if not self.cart:
                return self.say("Your cart is empty. What would you like to order?")
            self.stage = "name"
            return self.say("What name should I put on the order?")

        turn = interpret(self.menus, self.cart, speech, self.ordering_history)
        added = self.add_items(turn["items"])
        answer = turn.get("menu_answer")
        replies = [answer[:350]] if isinstance(answer, str) and answer else []
        if added:
            replies.append("Added " + "; ".join(added) + ".")
        if len(added) != len(turn["items"]):
            replies.append("I couldn't match part of that request. Could you repeat the item?")
        if self.cart:
            replies.append(self.delivery_summary())
            replies.append("Anything else? Say checkout when you're ready.")
        reply = " ".join(replies) or "What would you like to order?"
        self.ordering_history.append({"caller": speech, "assistant": reply})
        return self.say(reply)

    def confirmation_text(self):
        return (
            f"334-FOOD-NOW: Order #{self.order_id} confirmed. "
            f"Total: {money(self.totals()['total_cents'])}."
        )

    def save(self, root=Path("artifacts")):
        folder = root / self.order_id
        folder.mkdir(parents=True, exist_ok=True)
        totals = self.totals()
        order = {
            "order_id": self.order_id, "name": self.name, "phone": self.phone,
            "address": self.address, "restaurants": self.cart, "totals": totals,
        }
        group = [
            f"Demo only — simulated payment for order #{self.order_id}",
            "To: customer, " + ", ".join(self.cart) + ", and driver",
            f"Customer: {self.name} ({self.phone})", f"Deliver to: {self.address}",
        ]
        for restaurant, lines in self.cart.items():
            group.append(f"{restaurant}: " + "; ".join(map(self.describe, lines)))
        group.append(f"Total: {money(totals['total_cents'])}. Restaurants: reply READY when packed.")
        files = {
            "order.json": json.dumps(order, indent=2),
            "transcript.json": json.dumps(self.transcript, indent=2),
            "confirmation_sms.txt": self.confirmation_text(),
            "pay_link_preview.txt": (
                f"334-FOOD-NOW: Your total is {money(totals['total_cents'])}. "
                "Pay here: [test payment link]"
            ),
            "group_text_preview.txt": "\n".join(group),
        }
        for name, content in files.items():
            (folder / name).write_text(content + "\n")
        return folder
