"""
This is a TEMPLATE, not a drop-in file — wire in your own two working
programs where marked below. It shows the shape the backend expects,
nothing more.

Your swipe-detector already knows how to tell when a swipe was used.
Your menu-scraper already knows how to return items/descriptions/serving
sizes/calories. This script just needs to:

  1. Run your swipe-detection loop (as it already does).
  2. When a swipe fires, call your menu-scraper.
  3. Reshape its output into the {name, description, serving_size, calories}
     dict shape below.
  4. POST that list to the Flask server's /api/swipe endpoint.

Run this alongside app.py, on the same machine.
"""

import time
import requests

BACKEND_URL = "http://localhost:5000/api/swipe"


def get_current_menu_items():
    """
    Replace this with a call into your existing menu-scraper program.
    It must return a list of dicts shaped like:

        [
            {
                "name": "Grilled Chicken Breast",
                "description": "Herb-marinated, grilled",
                "serving_size": "4 oz",
                "calories": 190,
            },
            ...
        ]

    If your scraper currently returns raw scraped strings (like the
    item_list of lists from your earlier scraping code), map each row
    into this dict shape here, e.g.:

        raw_rows = your_existing_scrape_function()
        return [
            {
                "name": row[0],
                "description": row[1],
                "serving_size": row[2],
                "calories": int(row[3].split()[0]),  # e.g. "210 cal" -> 210
            }
            for row in raw_rows
        ]
    """
    raise NotImplementedError("Plug in your existing menu-scraper here")


def swipe_was_detected():
    """
    Replace this with your existing swipe-detection logic. Return True
    exactly once per swipe (don't fire repeatedly for the same swipe —
    debounce inside your own detector as it already does).
    """
    raise NotImplementedError("Plug in your existing swipe-detector here")


def main():
    print("Watching for swipes... (Ctrl+C to stop)")
    while True:
        if swipe_was_detected():
            print("Swipe detected — pulling current menu...")
            items = get_current_menu_items()
            resp = requests.post(BACKEND_URL, json={"items": items})
            print(f"Sent to backend: {resp.status_code} {resp.json()}")
        time.sleep(1)


if __name__ == "__main__":
    main()
