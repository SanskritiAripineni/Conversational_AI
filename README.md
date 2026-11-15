# 334 Food Now

### Many menus. One conversation.

A conversational ordering prototype that brings Indian, Italian, and Mexican dishes into one cart. The browser demo pairs a food concierge with a browsable menu, a live receipt, free-delivery progress, and guided checkout. The original terminal and Twilio phone demos are included.

**Python 3.13 · Flask · Gemini · Twilio**

## Start the browser demo

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run from the project folder:

```sh
uv venv --python 3.13
uv pip install -r requirements.txt
.venv/bin/python app.py web
```

Open **http://127.0.0.1:5055**. No API key is required for **Rehearsal** mode. Use the suggestion buttons or add dishes directly from the menu. Rehearsal uses a limited local menu matcher; it is not a live AI conversation. All browser checkouts are simulations, and the browser demo never sends SMS or takes payments.

The interface adapts to smaller screens and supports keyboard navigation, reduced motion, menu filters, cart removal, order reset, and a downloadable demo receipt.

## A two-minute presentation

1. Click **Try the sample order**. It adds two chicken biryanis (one mild) and a penne Alfredo. Food subtotal: **$44.97**. Another **$5.04** in food unlocks free delivery.
2. Click **Add chicken tacos**. Food subtotal becomes **$56.94**, delivery is free, and the final total including 8.25% tax is **$61.64**.
3. Click **Review & check out**. Use the buttons for fictional customer **Alex Morgan** and **123 Demo Lane, Sample City**.
4. Click **Confirm demo order**, then **Download demo receipt**.
5. Use **Start fresh** to reset for the next presentation.

Delivery is $4.99 on food subtotals of $50.00 or less; it is free **over** $50.00. Prices and totals come from Python, not the language model.

## Enable live Gemini conversation

```sh
cp .env.example .env
```

Create your own API key in [Google AI Studio](https://aistudio.google.com/api-keys) and set `GEMINI_API_KEY` in the local `.env`. Then run:

```sh
.venv/bin/python app.py web --live
```

The badge changes to **Gemini live**. Menu data, the cart, and conversational ordering history are sent to Google's Gemini API to interpret menu questions and ordering requests. Checkout details are handled locally by the order state machine. Keep `.env` local; it is ignored by Git. Never paste credentials into the browser chat or commit them.

The sample menu is included. A local `menus.json` overrides it; alternatively set `MENU_FILE` to another menu path. `GEMINI_MODEL` defaults to `gemini-2.5-flash` and can be adjusted for your account.

## Verification and project notes

```sh
.venv/bin/python -m unittest discover -s tests -v
```

`web.py` contains the browser API and rehearsal matcher; `templates/` and `static/` contain the interface. `tests/test_demo.py` covers checkout, pricing, isolated sessions, request validation, and voice authentication.

This is a local prototype. Sessions and active calls live in one process and reset on restart; browser sessions are capped at 128. There is no real restaurant dispatch, payment processing, or delivery tracking. Keep the browser demo local rather than exposing it through your phone tunnel.

## Original terminal and phone adapters

A voice ordering prototype. One customer can order from several restaurants in one call and receive a plain-text confirmation.

| File | Job |
| --- | --- |
| `ordering.py` | Menu validation, carts, prices, checkout and submission artifacts |
| `gemini.py` | Converts natural language into menu answers and proposed cart additions |
| `app.py` | Typed demo and inbound Twilio speech webhook |
| `sms.py` | Optional Textbelt confirmation to the configured test phone |

## Run the typed demo

```sh
uv venv --python 3.13
uv pip install -r requirements.txt
cp .env.example .env
```

Set `GEMINI_API_KEY` in `.env`. Add the event's `menus.json` to the repo root. A small sample menu from the brief is used if the event file is absent.

```sh
.venv/bin/python app.py chat
```

## Run the phone demo

1. Start your HTTPS tunnel to port 5055, for example `cloudflared tunnel --url http://127.0.0.1:5055`.
2. Set `PUBLIC_BASE_URL` to the tunnel origin, `TWILIO_AUTH_TOKEN` to the number's account auth token, and `DEMO_SMS_TO` to your verified phone in E.164 format.
3. Optionally set `TEXTBELT_KEY` for real sends. Leave it blank to rehearse with previews.
4. Run `.venv/bin/python app.py`. In the Twilio console set the inbound Voice webhook to **HTTP POST** at `PUBLIC_BASE_URL/voice`.
5. Call your Twilio number from the configured phone. Use a fictional name and address for submissions.

## Demo script

1. “Two chicken biryanis, one mild, and a penne Alfredo. Is delivery free?” Food subtotal is **$44.97**, so **$5.04** more qualifies.
2. “Add chicken tacos.” Food subtotal is **$56.94** and total with free delivery is **$61.64**.
3. Say “checkout,” give a demo name and address, listen to the readback, and say “yes.”
4. Check the confirmation text or preview. The corresponding `artifacts/<order-id>/` folder contains the transcript, order JSON, confirmation and the required test pay-link and simulated group texts. Use demo details and redact the phone before sharing.

The prototype stores active calls in one process. Restarting the server clears active calls. The only live message is the order confirmation sent to the configured test phone.
