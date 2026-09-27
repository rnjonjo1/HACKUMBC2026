"""
Scrapes the current True Grit's menu from DineOnCampus.

A fresh Chromium driver is created for every getMenu() call.
This avoids reusing a stale/Cloudflare-affected browser session.
"""

import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


CHROMIUM_BINARY = "/usr/bin/chromium"
CHROMEDRIVER_BINARY = "/usr/bin/chromedriver"

MENU_URL = (
    "https://dineoncampus.com/UMBC/"
    "whats-on-the-menu/true-grit-s/"
)


def _create_driver():
    """Create a brand-new Chromium instance."""

    options = webdriver.ChromeOptions()

    options.binary_location = CHROMIUM_BINARY

    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")

    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    options.add_argument(
        "--disable-blink-features=AutomationControlled"
    )

    options.add_argument("--lang=en-US")

    options.add_argument(
        "user-agent=Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    service = Service(CHROMEDRIVER_BINARY)

    return webdriver.Chrome(
        service=service,
        options=options,
    )


def _save_debug(driver):
    """Save the page if scraping fails."""

    try:
        driver.save_screenshot("menu_debug.png")
        print("[Menu] Saved menu_debug.png")
    except Exception as e:
        print(f"[Menu] Screenshot failed: {e}")

    try:
        with open(
            "menu_debug.html",
            "w",
            encoding="utf-8",
        ) as f:
            f.write(driver.page_source)

        print("[Menu] Saved menu_debug.html")

    except Exception as e:
        print(f"[Menu] HTML dump failed: {e}")


def _parse_table_rows(driver, rows):
    """Parse traditional table-based menu rows."""

    item_list = []

    for row in rows:

        try:
            cells = row.find_elements(
                By.TAG_NAME,
                "td",
            )

            if not cells:
                continue

            values = [
                cell.text.strip()
                for cell in cells
            ]

            if not any(values):
                continue

            item = []
            macrolist = []

            # ----------------------------------------------------------
            # Try to get nutrition information.
            # ----------------------------------------------------------

            try:
                button = cells[0].find_element(
                    By.CSS_SELECTOR,
                    "div button",
                )

                driver.execute_script(
                    "arguments[0].click();",
                    button,
                )

                time.sleep(0.25)

                macro_cells = driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class, "
                    "'flex') and "
                    "contains(@class, "
                    "'justify-between') and "
                    "contains(@class, 'py-1')]",
                )

                macros = []

                for macro_cell in macro_cells:
                    text = macro_cell.text.strip()

                    if text:
                        macros.append(text)

                if macros:
                    macrolist.append(macros)

                ActionChains(driver).send_keys(
                    Keys.ESCAPE
                ).perform()

            except Exception as e:
                print(
                    "[Menu] No nutrition button/data "
                    f"for item: {e}"
                )

            # ----------------------------------------------------------
            # Add normal cells.
            # ----------------------------------------------------------

            for value in values:
                item.append(value)

            # Ensure at least 4 normal fields.
            while len(item) < 4:
                item.append("")

            # Macros are field 5.
            item.append(macrolist)

            item_list.append(item)

        except Exception as e:
            print(
                f"[Menu] Couldn't parse row: {e}"
            )

    return item_list


def _deduplicate(items):
    """Remove duplicate menu rows."""

    result = []
    seen = set()

    for item in items:

        if not item:
            continue

        key = (
            str(item[0]),
            str(item[1]),
            str(item[2]),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def getMenu():
    """
    Scrape today's/current True Grit menu.

    A new browser is created for every call and closed afterward.
    """

    driver = None

    try:
        print()
        print("[Menu] Starting fresh browser...")
        print(f"[Menu] Loading: {MENU_URL}")

        driver = _create_driver()

        driver.get(MENU_URL)

        # Wait for the browser document to finish loading.
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script(
                "return document.readyState"
            ) in ("interactive", "complete")
        )

        # Give DineOnCampus JavaScript time to render.
        time.sleep(3)

        print(
            "[Menu] Current URL:",
            driver.current_url,
        )

        print(
            "[Menu] Title:",
            driver.title,
        )

        # --------------------------------------------------------------
        # Detect Cloudflare.
        # --------------------------------------------------------------

        title = driver.title.lower()

        if (
            "cloudflare" in title
            or "attention required" in title
        ):
            print(
                "[Menu] Cloudflare page detected."
            )

            _save_debug(driver)

            raise RuntimeError(
                "DineOnCampus returned a Cloudflare "
                "challenge instead of the menu."
            )

        # --------------------------------------------------------------
        # Look for normal table rows.
        # --------------------------------------------------------------

        try:

            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "tbody tr",
                    )
                )
            )

            rows = driver.find_elements(
                By.CSS_SELECTOR,
                "tbody tr",
            )

            print(
                f"[Menu] Found {len(rows)} table rows."
            )

            items = _parse_table_rows(
                driver,
                rows,
            )

            items = _deduplicate(items)

            print(
                f"[Menu] Parsed {len(items)} menu items."
            )

            if items:
                return items

        except Exception as e:

            print(
                "[Menu] No usable tbody rows: "
                f"{type(e).__name__}: {e}"
            )

        # --------------------------------------------------------------
        # Fallback selectors.
        # --------------------------------------------------------------

        selectors = [
            "[data-testid*='menu']",
            "[data-testid*='item']",
            "[class*='menu-item']",
            "[class*='MenuItem']",
            "[class*='food-item']",
            "[class*='FoodItem']",
            "[class*='menuItem']",
        ]

        for selector in selectors:

            elements = driver.find_elements(
                By.CSS_SELECTOR,
                selector,
            )

            if not elements:
                continue

            print(
                f"[Menu] Found {len(elements)} "
                f"elements using {selector}"
            )

            items = []

            for element in elements:

                try:
                    text = element.text.strip()

                    if not text:
                        continue

                    lines = [
                        " ".join(line.split())
                        for line in text.splitlines()
                        if line.strip()
                    ]

                    if len(lines) < 2:
                        continue

                    # Don't treat a giant page container as an item.
                    if len(text) > 1200:
                        continue

                    name = lines[0]
                    description = (
                        lines[1]
                        if len(lines) > 1
                        else ""
                    )

                    name_description = name

                    if description:
                        name_description += (
                            "\n" + description
                        )

                    calories = 0

                    for line in lines:

                        lower = line.lower()

                        if (
                            "calorie" in lower
                            or " cal" in lower
                        ):

                            digits = ""

                            for character in line:

                                if character.isdigit():
                                    digits += character

                                elif digits:
                                    break

                            if digits:
                                try:
                                    calories = int(digits)
                                except ValueError:
                                    pass

                    items.append(
                        [
                            name_description,
                            "",
                            str(calories),
                            "",
                            [],
                        ]
                    )

                except Exception:
                    continue

            items = _deduplicate(items)

            if items:
                print(
                    f"[Menu] Parsed {len(items)} "
                    "fallback items."
                )

                return items

        # --------------------------------------------------------------
        # Nothing worked.
        # --------------------------------------------------------------

        print(
            "[Menu] ERROR: No menu items found."
        )

        _save_debug(driver)

        raise RuntimeError(
            "Could not find True Grit menu items."
        )

    finally:

        # IMPORTANT:
        # Always close this browser.
        if driver is not None:

            try:
                driver.quit()
                print(
                    "[Menu] Browser closed."
                )
            except Exception:
                pass


if __name__ == "__main__":

    import json

    try:

        menu = getMenu()

        print()
        print("=" * 70)
        print("TODAY'S TRUE GRIT MENU")
        print("=" * 70)

        print(
            json.dumps(
                menu,
                indent=2,
            )
        )

    except Exception as e:

        print()
        print(
            "[Menu] FAILED:",
            type(e).__name__,
            str(e),
        )
