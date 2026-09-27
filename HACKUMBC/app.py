"""
Calorie Tracker Backend

Flow:
  1. swipe_detector.py notices a True Grit swipe.
  2. It scrapes today's menu and POSTs it to /api/swipe.
  3. This server stores the menu and sends a push notification.
  4. You open the installed web app and log what you actually ate.
  5. The app tracks calories and macros for the current meal.

Run this on the SAME machine as swipe_detector.py.

Important:
  - VAPID private key: private_key.pem
  - VAPID public key: public_key.txt
  - Push subscriptions: subscriptions.json
  - Flask debug/reloader is intentionally disabled.
"""

import base64
import json
import os
import re
import threading

from flask import Flask, jsonify, request, send_from_directory
from pywebpush import webpush, WebPushException


# ============================================================================
# APP SETUP
# ============================================================================

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="",
)

HERE = os.path.dirname(os.path.abspath(__file__))

PRIVATE_KEY_PATH = os.path.join(HERE, "private_key.pem")
PUBLIC_KEY_PATH = os.path.join(HERE, "public_key.txt")
SUBSCRIPTIONS_PATH = os.path.join(HERE, "subscriptions.json")


# ============================================================================
# VAPID CONFIGURATION
# ============================================================================

VAPID_PRIVATE_KEY = PRIVATE_KEY_PATH

VAPID_PUBLIC_KEY = ""

if os.path.exists(PUBLIC_KEY_PATH):
    try:
        with open(PUBLIC_KEY_PATH, "r", encoding="utf-8") as f:
            VAPID_PUBLIC_KEY = f.read().strip()
    except Exception as e:
        print(
            f"[vapid] Failed to read public key: "
            f"{type(e).__name__}: {e}"
        )

# IMPORTANT:
# Replace this with a real email address you control.
VAPID_CLAIMS = {
    "sub": "mailto:rmn016bcps@gmail.com"
}


# ============================================================================
# STATE
# ============================================================================

lock = threading.Lock()

state = {
    "menu": [],
    "selected": {},
    "subscriptions": [],

    # Incremented every time a new menu is received.
    # The frontend can use this to detect a new swipe/menu.
    "menu_version": 0,
}


# ============================================================================
# SUBSCRIPTION PERSISTENCE
# ============================================================================

def load_subscriptions():
    """Load saved push subscriptions from disk."""

    if not os.path.exists(SUBSCRIPTIONS_PATH):
        print("[subscriptions] No saved subscriptions found.")
        return []

    try:
        with open(SUBSCRIPTIONS_PATH, "r", encoding="utf-8") as f:
            subscriptions = json.load(f)

        if not isinstance(subscriptions, list):
            print("[subscriptions] File did not contain a list.")
            return []

        print(
            f"[subscriptions] Loaded "
            f"{len(subscriptions)} saved subscription(s)."
        )

        return subscriptions

    except Exception as e:
        print(
            f"[subscriptions] Failed to load subscriptions: "
            f"{type(e).__name__}: {e}"
        )
        return []


def save_subscriptions():
    """Persist current push subscriptions to disk."""

    try:
        with lock:
            subscriptions = list(state["subscriptions"])

        temporary_path = SUBSCRIPTIONS_PATH + ".tmp"

        with open(temporary_path, "w", encoding="utf-8") as f:
            json.dump(
                subscriptions,
                f,
                indent=2,
            )

        os.replace(
            temporary_path,
            SUBSCRIPTIONS_PATH,
        )

        print(
            f"[subscriptions] Saved "
            f"{len(subscriptions)} subscription(s)."
        )

    except Exception as e:
        print(
            f"[subscriptions] Failed to save subscriptions: "
            f"{type(e).__name__}: {e}"
        )


# Load subscriptions when the application starts.
state["subscriptions"] = load_subscriptions()


# ============================================================================
# CACHE CONTROL
# ============================================================================

def no_cache(response):
    """
    Prevent browsers/PWAs from caching API responses.

    This is particularly important for /api/menu because the menu
    can change when swipe_detector.py sends a new swipe.
    """

    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, max-age=0"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


# ============================================================================
# CALORIE / MACRO CALCULATIONS
# ============================================================================

def session_total():
    """Return total calories currently selected."""

    total = 0

    for item in state["menu"]:
        name = item.get("name")
        quantity = state["selected"].get(name, 0)

        try:
            calories = float(item.get("calories", 0) or 0)
        except (TypeError, ValueError):
            calories = 0

        total += calories * quantity

    return total


def _leading_number(value):
    """
    Extract the first numeric value.

    Examples:
        "14 g"              -> 14.0
        "120 mg"            -> 120.0
        "1.5 g"             -> 1.5
        "less than 1 gram"  -> None
        "-"                 -> None
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # Look for the first number anywhere in the string.
    match = re.search(
        r"-?\d+(?:\.\d+)?",
        value,
    )

    if not match:
        return None

    try:
        return float(match.group(0))
    except ValueError:
        return None


def session_macro_totals():
    """Return totals for all selected macros."""

    totals = {}

    for item in state["menu"]:
        name = item.get("name")
        quantity = state["selected"].get(name, 0)

        if not quantity:
            continue

        macros = item.get("macros", {})

        if not isinstance(macros, dict):
            continue

        for label, value in macros.items():
            number = _leading_number(value)

            if number is None:
                continue

            totals[label] = (
                totals.get(label, 0)
                + number * quantity
            )

    return totals


# ============================================================================
# FRONTEND
# ============================================================================

@app.route("/")
def index():
    return send_from_directory(
        app.static_folder,
        "index.html",
    )


# ============================================================================
# VAPID PUBLIC KEY
# ============================================================================

@app.route("/vapid-public-key")
def vapid_public_key():
    """
    Return the VAPID public key in the format expected by
    PushManager.subscribe().
    """

    if not VAPID_PUBLIC_KEY:
        return jsonify({
            "ok": False,
            "error": "VAPID public key is not configured",
        }), 500

    try:
        # public_key.txt is expected to contain the public key
        # as hexadecimal bytes.
        public_key_bytes = bytes.fromhex(VAPID_PUBLIC_KEY)

        public_key_b64 = base64.urlsafe_b64encode(
            public_key_bytes
        ).rstrip(b"=").decode("ascii")

    except ValueError:
        # If the file already contains a URL-safe base64 key,
        # return it directly.
        public_key_b64 = VAPID_PUBLIC_KEY

    response = jsonify({
        "key": public_key_b64
    })

    return no_cache(response)


# ============================================================================
# HEALTH / DEBUG
# ============================================================================

@app.route("/api/health")
def health():
    """Simple endpoint for checking backend status."""

    with lock:
        subscription_count = len(state["subscriptions"])
        menu_count = len(state["menu"])
        menu_version = state["menu_version"]

    response = jsonify({
        "ok": True,
        "vapid_private_key_loaded": bool(VAPID_PRIVATE_KEY),
        "vapid_public_key_loaded": bool(VAPID_PUBLIC_KEY),
        "subscription_count": subscription_count,
        "menu_item_count": menu_count,
        "menu_version": menu_version,
    })

    return no_cache(response)


# ============================================================================
# SWIPE
# ============================================================================

@app.route("/api/swipe", methods=["POST"])
def swipe_used():
    """
    Called by swipe_detector.py.

    Expected JSON:

    {
        "items": [
            {
                "name": "...",
                "description": "...",
                "serving_size": "...",
                "calories": 500,
                "macros": {
                    "Protein (g)": "30 g"
                }
            }
        ]
    }
    """

    try:
        payload = request.get_json(force=True) or {}

    except Exception as e:
        print(
            f"[swipe] Invalid JSON: "
            f"{type(e).__name__}: {e}"
        )

        return jsonify({
            "ok": False,
            "error": "Invalid JSON",
        }), 400

    if not isinstance(payload, dict):
        return jsonify({
            "ok": False,
            "error": "Request body must be an object",
        }), 400

    items = payload.get("items", [])

    if not isinstance(items, list):
        return jsonify({
            "ok": False,
            "error": "'items' must be a list",
        }), 400

    # Clean up menu items.
    cleaned_items = []

    for item in items:

        if not isinstance(item, dict):
            print("[swipe] Ignoring non-object menu item.")
            continue

        item = dict(item)

        # Every item should have a macros dictionary.
        macros = item.get("macros")

        if not isinstance(macros, dict):
            item["macros"] = {}

        # Make sure name exists.
        if not item.get("name"):
            print("[swipe] Ignoring item with no name.")
            continue

        # Make sure calories has a usable value.
        calories = item.get("calories", 0)

        try:
            item["calories"] = float(calories or 0)
        except (TypeError, ValueError):
            item["calories"] = 0

        cleaned_items.append(item)

    print()
    print("=" * 60)
    print("[swipe] NEW MEAL RECEIVED")
    print("=" * 60)

    for item in cleaned_items:
        print(
            f"[swipe] {item.get('name')} - "
            f"{item.get('calories', 0)} calories"
        )

    print(
        f"[swipe] Received "
        f"{len(cleaned_items)} menu item(s)."
    )

    # Update the current menu.
    with lock:
        state["menu"] = cleaned_items
        state["selected"] = {}

        state["menu_version"] += 1

        menu_version = state["menu_version"]

    print(
        f"[swipe] Menu updated. "
        f"Version: {menu_version}"
    )

    print("=" * 60)
    print()

    # Notify the phone.
    _notify_all(
        "Meal swipe used",
        "Tap to log what you're eating.",
    )

    response = jsonify({
        "ok": True,
        "item_count": len(cleaned_items),
        "menu_version": menu_version,
    })

    return no_cache(response)


# ============================================================================
# MENU
# ============================================================================

@app.route("/api/menu")
def get_menu():
    """
    Return the current meal menu.

    Cache is explicitly disabled so the installed web app
    always receives the latest menu.
    """

    with lock:
        response_data = {
            "menu": state["menu"],
            "selected": state["selected"],
            "menu_version": state["menu_version"],
        }

    response = jsonify(response_data)

    return no_cache(response)


# ============================================================================
# SELECT ITEM
# ============================================================================

@app.route("/api/select", methods=["POST"])
def select_item():
    """
    Expected JSON:

    {
        "name": "Chicken",
        "quantity": 2
    }

    quantity <= 0 removes the item.
    """

    try:
        payload = request.get_json(force=True) or {}

    except Exception:
        return jsonify({
            "ok": False,
            "error": "Invalid JSON",
        }), 400

    if not isinstance(payload, dict):
        return jsonify({
            "ok": False,
            "error": "Request body must be an object",
        }), 400

    name = payload.get("name")

    if not name:
        return jsonify({
            "ok": False,
            "error": "Missing item name",
        }), 400

    try:
        quantity = int(payload.get("quantity", 0))

    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "Quantity must be an integer",
        }), 400

    quantity = max(0, quantity)

    with lock:

        if quantity > 0:
            state["selected"][name] = quantity

        else:
            state["selected"].pop(name, None)

        total = session_total()
        macro_totals = session_macro_totals()

    response = jsonify({
        "ok": True,
        "total_calories": total,
        "macro_totals": macro_totals,
    })

    return no_cache(response)


# ============================================================================
# SESSION
# ============================================================================

@app.route("/api/session")
def get_session():
    """Return the complete current meal session."""

    with lock:
        response_data = {
            "menu": state["menu"],
            "selected": state["selected"],
            "total_calories": session_total(),
            "macro_totals": session_macro_totals(),
            "menu_version": state["menu_version"],
        }

    response = jsonify(response_data)

    return no_cache(response)


# ============================================================================
# RESET
# ============================================================================

@app.route("/api/reset", methods=["POST"])
def reset_session():
    """Clear the current meal without saving a summary."""

    with lock:
        state["selected"] = {}

    print("[session] Session reset.")

    return jsonify({
        "ok": True,
    })


# ============================================================================
# END MEAL
# ============================================================================

@app.route("/api/end-meal", methods=["POST"])
def end_meal():
    """
    Finalize the current meal.

    Returns a summary and then clears the current session.
    """

    with lock:

        items = []

        for item in state["menu"]:

            name = item.get("name")
            quantity = state["selected"].get(name, 0)

            if quantity:

                try:
                    calories = float(
                        item.get("calories", 0) or 0
                    )

                except (TypeError, ValueError):
                    calories = 0

                items.append({
                    "name": name,
                    "quantity": quantity,
                    "calories": calories * quantity,
                })

        summary = {
            "items": items,
            "total_calories": session_total(),
            "macro_totals": session_macro_totals(),
        }

        state["menu"] = []
        state["selected"] = {}

        # Increment so the frontend knows the meal was cleared.
        state["menu_version"] += 1

    print(
        f"[session] Meal ended: "
        f"{summary['total_calories']} calories."
    )

    response = jsonify(summary)

    return no_cache(response)


# ============================================================================
# PUSH SUBSCRIPTION
# ============================================================================

@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    """Register a browser/device for push notifications."""

    try:
        sub = request.get_json(force=True)

    except Exception:
        return jsonify({
            "ok": False,
            "error": "Invalid JSON",
        }), 400

    if not isinstance(sub, dict):
        return jsonify({
            "ok": False,
            "error": "Subscription must be an object",
        }), 400

    endpoint = sub.get("endpoint")

    if not endpoint:
        print(
            "[subscribe] Rejected subscription: "
            "missing endpoint."
        )

        return jsonify({
            "ok": False,
            "error": "Missing push endpoint",
        }), 400

    print("[subscribe] Received push subscription.")
    print(f"[subscribe] Endpoint: {endpoint}")

    with lock:

        # Compare subscriptions by endpoint instead of requiring
        # the entire JSON object to be identical.
        existing_index = None

        for index, existing in enumerate(
            state["subscriptions"]
        ):
            if existing.get("endpoint") == endpoint:
                existing_index = index
                break

        if existing_index is None:

            state["subscriptions"].append(sub)

            added = True

        else:

            # Replace the old subscription with the current one.
            # Browser keys can change while the endpoint remains
            # the same.
            state["subscriptions"][existing_index] = sub

            added = False

        count = len(state["subscriptions"])

    if added:

        print(
            f"[subscribe] Added subscription. "
            f"Total: {count}"
        )

    else:

        print(
            f"[subscribe] Updated/existing subscription. "
            f"Total: {count}"
        )

    save_subscriptions()

    return jsonify({
        "ok": True,
        "subscription_count": count,
        "already_registered": not added,
    })


# ============================================================================
# TEST PUSH
# ============================================================================

@app.route("/api/test-push", methods=["POST"])
def test_push():
    """Send a test push notification to all registered devices."""

    print("[test-push] Sending test notification.")

    _notify_all(
        "True Grit Test",
        "Your mobile notifications are working!",
    )

    return jsonify({
        "ok": True,
    })


# ============================================================================
# PUSH NOTIFICATIONS
# ============================================================================

def _notify_all(title, body):
    """
    Send a push notification to every registered browser.

    Dead subscriptions are automatically removed.
    """

    print()
    print("=" * 60)
    print("[notify] PUSH NOTIFICATION")
    print("=" * 60)

    if not VAPID_PRIVATE_KEY:
        print(
            "[notify] ERROR: VAPID private key is not loaded."
        )

        print(
            f"[notify] Expected file: "
            f"{PRIVATE_KEY_PATH}"
        )

        print(
            f"[notify] Would have sent: "
            f"{title} / {body}"
        )

        print("=" * 60)

        return

    if not os.path.exists(VAPID_PRIVATE_KEY):
        print(
            f"[notify] ERROR: Private key file does not exist: "
            f"{VAPID_PRIVATE_KEY}"
        )

        print("=" * 60)

        return

    if not VAPID_PUBLIC_KEY:
        print(
            "[notify] WARNING: "
            "VAPID public key is not loaded."
        )

    if not VAPID_CLAIMS.get("sub"):
        print(
            "[notify] ERROR: VAPID subject is missing."
        )

        return

    with lock:
        subscriptions = list(
            state["subscriptions"]
        )

    print(
        f"[notify] Sending to "
        f"{len(subscriptions)} subscription(s)."
    )

    if not subscriptions:

        print(
            "[notify] NO SUBSCRIPTIONS REGISTERED."
        )

        print(
            "[notify] Open the web app and "
            "allow notifications."
        )

        print("=" * 60)

        return

    dead = []

    for index, sub in enumerate(
        subscriptions,
        start=1,
    ):

        endpoint = sub.get(
            "endpoint",
            "MISSING",
        )

        print()
        print(
            f"[notify] Sending push "
            f"#{index}/{len(subscriptions)}"
        )

        print(
            f"[notify] Endpoint: {endpoint}"
        )

        try:

            response = webpush(
                subscription_info=sub,

                data=json.dumps({
                    "title": title,
                    "body": body,
                }),

                vapid_private_key=VAPID_PRIVATE_KEY,

                vapid_claims=dict(
                    VAPID_CLAIMS
                ),
            )

            print(
                f"[notify] Push #{index} SUCCESS."
            )

            if response is not None:

                print(
                    f"[notify] Response: "
                    f"{response}"
                )

        except WebPushException as ex:

            print()
            print(
                f"[notify] Push #{index} FAILED."
            )

            print(
                f"[notify] Error: {ex}"
            )

            response = getattr(
                ex,
                "response",
                None,
            )

            if response is not None:

                print(
                    f"[notify] HTTP status: "
                    f"{getattr(response, 'status_code', 'unknown')}"
                )

                try:

                    print(
                        f"[notify] Response body: "
                        f"{response.text}"
                    )

                except Exception:
                    pass

            status_code = getattr(
                response,
                "status_code",
                None,
            )

            # 404 and 410 normally indicate that the
            # subscription no longer exists.
            if status_code in (404, 410):

                print(
                    "[notify] "
                    "Subscription is expired/dead."
                )

                dead.append(sub)

        except Exception as ex:

            print()
            print(
                f"[notify] Push #{index} "
                f"unexpected error:"
            )

            print(
                f"[notify] "
                f"{type(ex).__name__}: {ex}"
            )

    # Remove expired subscriptions.
    if dead:

        with lock:

            state["subscriptions"] = [
                sub
                for sub in state["subscriptions"]
                if sub not in dead
            ]

        print(
            f"[notify] Removed "
            f"{len(dead)} dead subscription(s)."
        )

        save_subscriptions()

    print("=" * 60)
    print("[notify] DONE")
    print("=" * 60)
    print()


# ============================================================================
# STARTUP STATUS
# ============================================================================

def print_startup_status():
    """Print useful configuration information."""

    print()
    print("=" * 60)
    print("CALORIE TRACKER BACKEND")
    print("=" * 60)

    print(
        f"Private VAPID key: "
        f"{'LOADED' if os.path.exists(VAPID_PRIVATE_KEY) else 'MISSING'}"
    )

    print(
        f"Public VAPID key:  "
        f"{'LOADED' if VAPID_PUBLIC_KEY else 'MISSING'}"
    )

    print(
        f"VAPID subject:     "
        f"{VAPID_CLAIMS.get('sub', 'MISSING')}"
    )

    print(
        f"Subscriptions:     "
        f"{len(state['subscriptions'])}"
    )

    print(
        f"Subscription file: "
        f"{SUBSCRIPTIONS_PATH}"
    )

    print(
        f"Static folder:     "
        f"{app.static_folder}"
    )

    print(
        f"Current menu:      "
        f"{len(state['menu'])} item(s)"
    )

    print(
        f"Menu version:      "
        f"{state['menu_version']}"
    )

    print()
    print("Server:")
    print("  http://127.0.0.1:5000")
    print("  http://0.0.0.0:5000")
    print()
    print("Debug/reloader: DISABLED")
    print("=" * 60)
    print()


# ============================================================================
# START SERVER
# ============================================================================

if __name__ == "__main__":

    print_startup_status()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
    )
