# Meal Calorie Tracker

Notifies you on iOS when a meal swipe is used, then lets you check off what
you ate from the current menu and shows a running calorie total for that
meal.

## How it fits together

```
your swipe-detector  ──▶  swipe_integration_example.py  ──▶  POST /api/swipe
      (existing)                (you fill this in)              │
                                                                  ▼
your menu-scraper                                          app.py (Flask)
      (existing)  ──▶ called from the integration script ──▶ stores menu,
                                                            pushes notification
                                                                  │
                                                                  ▼
                                                        installed web app on
                                                        your phone (checklist +
                                                        live calorie total)
```

Nothing about your two existing programs needs to change — you're only
adding a small step that calls the Flask server after a swipe fires.

## 1. Install dependencies

```bash
cd calorie-tracker
python -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Generate push notification keys (one-time)

```bash
python generate_vapid_keys.py
```

This writes `private_key.pem` and `public_key.txt` in this folder — `app.py`
picks them up automatically. Don't commit `private_key.pem` anywhere public.

## 3. Run the backend

```bash
python app.py
```

This starts the server at `http://localhost:5000`. Leave this running.

## 4. Wire in your existing scripts

Open `swipe_integration_example.py` and fill in the two functions marked
`NotImplementedError`:
- `swipe_was_detected()` — your existing detection logic
- `get_current_menu_items()` — your existing scraper, reshaped into the
  `{name, description, serving_size, calories}` dict format shown in the
  file

Then run it alongside `app.py`:

```bash
python swipe_integration_example.py
```

## 5. Get an HTTPS URL so your iPhone can reach it

iOS requires a real HTTPS address for push notifications to work in an
installed web app — `localhost` only works on the same machine, and your
phone is a different device. The easiest way to bridge this without buying
a domain/cert is a tunnel:

**Option A — Cloudflare Tunnel (free, no signup for quick tunnels):**
```bash
cloudflared tunnel --url http://localhost:5000
```
It prints an `https://xxxx.trycloudflare.com` URL — that's what you open
on your phone. This URL changes each time you restart the tunnel.

**Option B — ngrok:**
```bash
ngrok http 5000
```
Also prints an `https://...ngrok-free.app` URL.

Either way, keep this tunnel running alongside `app.py`.

## 6. Install it on your iPhone

1. Open the `https://...` tunnel URL in **Safari** (must be Safari, not
   Chrome, for install-to-home-screen to work on iOS).
2. Tap the Share icon → **Add to Home Screen**.
3. Open the app from your home screen icon (not from Safari) — this is
   required for push notifications to work at all on iOS.
4. Tap **Enable notifications** inside the app and accept the permission
   prompt.

Requires iOS 16.4 or later.

## 7. Test it end-to-end

With `app.py`, the tunnel, and your integration script all running, trigger
a swipe (or manually test with curl):

```bash
curl -X POST http://localhost:5000/api/swipe \
  -H "Content-Type: application/json" \
  -d '{"items": [{"name": "Grilled Chicken", "description": "with herbs", "serving_size": "4 oz", "calories": 190}]}'
```

You should get a push notification on your phone; opening the app shows the
item ready to check off.

## Notes

- The session is intentionally *not* saved across days — "Reset session"
  or a new swipe both start fresh, matching a per-meal calorie count rather
  than a running diary.
- Everything is in-memory in `app.py` (a Python dict) — restarting the
  server clears the current session and any push subscriptions, so you'll
  need to tap "Enable notifications" again after a restart.
- If you'd rather this survive machine restarts long-term, the next step
  would be swapping the in-memory `state` dict in `app.py` for a small
  SQLite file — say the word if you want that added.
