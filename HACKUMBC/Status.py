import os
import time
import json
import pickle
import atexit
from pathlib import Path
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service

import Menu


# ============================================================================
# LOGIN
# ============================================================================

USERNAME = "KL27697"
PASSWORD = "Muthoni@1245"

LOGIN_URL = (
    "https://my.umbc.edu/login/umbc"
    "?url=https%3A%2F%2Fmy.umbc.edu%2Fwelcome"
)

TARGET_URL = (
    "https://my.umbc.edu/go/retriever-card"
)


# ============================================================================
# SELECTORS
# ============================================================================

USERNAME_FIELD_SELECTOR = (
    By.ID,
    "username",
)

PASSWORD_FIELD_SELECTOR = (
    By.ID,
    "password",
)

UP_BUTTON_SELECTOR = (
    By.ID,
    "submitButton",
)

SUBMIT_BUTTON_SELECTOR = (
    By.XPATH,
    "/html/body/div[1]/div/div/div[1]/div[3]/button",
)

SMS_INPUT_SELECTOR = (
    By.ID,
    "passcode-input",
)

SUBMIT_SMS_SELECTOR = (
    By.XPATH,
    "/html/body/div[1]/div/div/div[1]/div[3]/div[1]/form/div[4]/button",
)

NEXT_SELECTOR = (
    By.XPATH,
    '//*[@id="pwl-prompt-root"]/div/div/div[1]/div[3]/button',
)

VALUE_SELECTOR = (
    By.XPATH,
    "/html/body/div[2]/div/div[2]/div/div[1]/div[2]/div/table/tbody/tr[1]",
)


# ============================================================================
# CHROME
# ============================================================================

CHROMIUM_BINARY = "/usr/bin/chromium"
CHROMEDRIVER_BINARY = "/usr/bin/chromedriver"


# ============================================================================
# FILES
# ============================================================================

COOKIE_FILE = Path("session_cookies.pkl")
LAST_VALUE_FILE = Path("last_value.json")


# ============================================================================
# POLLING
# ============================================================================

POLL_INTERVAL_SECONDS = 60


# ============================================================================
# BACKEND
# ============================================================================

CALORIE_TRACKER_URL = (
    "http://localhost:5000/api/swipe"
)


# ============================================================================
# DRIVER
# ============================================================================

def build_driver(headless=True):

    options = webdriver.ChromeOptions()

    options.binary_location = CHROMIUM_BINARY

    if headless:
        options.add_argument("--headless=new")

    options.add_argument(
        "--window-size=1280,900"
    )

    options.add_argument("--no-sandbox")
    options.add_argument(
        "--disable-dev-shm-usage"
    )

    service = Service(
        CHROMEDRIVER_BINARY,
        log_output="chromedriver.log",
    )

    return webdriver.Chrome(
        service=service,
        options=options,
    )


# ============================================================================
# COOKIES
# ============================================================================

def save_cookies(driver):

    with open(
        COOKIE_FILE,
        "wb",
    ) as f:

        pickle.dump(
            driver.get_cookies(),
            f,
        )


def load_cookies(driver):

    if not COOKIE_FILE.exists():
        return False

    driver.get(TARGET_URL)

    with open(
        COOKIE_FILE,
        "rb",
    ) as f:

        cookies = pickle.load(f)

    for cookie in cookies:

        cookie.pop(
            "sameSite",
            None,
        )

        try:
            driver.add_cookie(cookie)
        except Exception:
            pass

    return True


# ============================================================================
# LOGIN CHECK
# ============================================================================

def is_logged_in(driver):

    driver.get(TARGET_URL)

    try:

        WebDriverWait(
            driver,
            5,
        ).until(
            EC.presence_of_element_located(
                VALUE_SELECTOR
            )
        )

        return True

    except Exception:

        return False


# ============================================================================
# LOGIN
# ============================================================================

def login(driver):

    print("[Status] Logging into UMBC...")

    driver.get(LOGIN_URL)

    WebDriverWait(
        driver,
        15,
    ).until(
        EC.presence_of_element_located(
            USERNAME_FIELD_SELECTOR
        )
    )

    driver.find_element(
        *USERNAME_FIELD_SELECTOR
    ).send_keys(USERNAME)

    driver.find_element(
        *PASSWORD_FIELD_SELECTOR
    ).send_keys(PASSWORD)

    driver.find_element(
        *UP_BUTTON_SELECTOR
    ).click()

    WebDriverWait(
        driver,
        15,
    ).until(
        EC.element_to_be_clickable(
            SUBMIT_BUTTON_SELECTOR
        )
    ).click()

    WebDriverWait(
        driver,
        15,
    ).until(
        EC.visibility_of_element_located(
            SMS_INPUT_SELECTOR
        )
    ).send_keys(
        input("INPUT SMS CODE ")
    )

    element = WebDriverWait(
        driver,
        15,
    ).until(
        EC.element_to_be_clickable(
            SUBMIT_SMS_SELECTOR
        )
    )

    driver.execute_script(
        "arguments[0].click();",
        element,
    )

    WebDriverWait(
        driver,
        15,
    ).until(
        EC.element_to_be_clickable(
            NEXT_SELECTOR
        )
    ).click()

    WebDriverWait(
        driver,
        60,
    ).until(
        EC.url_changes(LOGIN_URL)
    )

    save_cookies(driver)

    print("[Status] Login successful.")


# ============================================================================
# CARD VALUE
# ============================================================================

def get_current_value(driver):

    driver.get(TARGET_URL)

    el = WebDriverWait(
        driver,
        15,
    ).until(
        EC.presence_of_element_located(
            VALUE_SELECTOR
        )
    )

    return el.text.strip()


# ============================================================================
# MACROS
# ============================================================================

def parse_macros(macro_strings):

    macros = {}

    for entry in macro_strings:

        if "\n" in entry:

            label, value = entry.split(
                "\n",
                1,
            )

        else:

            label = entry
            value = ""

        macros[
            label.strip()
        ] = value.strip()

    return macros


# ============================================================================
# MENU ROW
# ============================================================================

def parse_row(row):

    name_desc = row[0]

    if "\n" in name_desc:

        name, description = (
            name_desc.split(
                "\n",
                1,
            )
        )

    else:

        name = name_desc
        description = ""

    macro_strings = []

    if len(row) > 4 and row[4]:

        macro_strings = row[4][0]

    calories = 0

    try:

        calories = int(
            row[2].strip()
        )

    except (
        ValueError,
        AttributeError,
        IndexError,
    ):

        calories = 0

    return {
        "name": name.strip(),
        "description": description.strip(),
        "serving_size": (
            row[1].strip()
            if len(row) > 1
            else ""
        ),
        "calories": calories,
        "macros": parse_macros(
            macro_strings
        ),
    }


# ============================================================================
# NOTIFY
# ============================================================================

def notify(message):

    if "TG" not in message:
        return

    print()
    print(
        "EXECUTE PROGRAM TRUE GRITS DETECTED"
    )

    # --------------------------------------------------------------
    # Scrape menu.
    # --------------------------------------------------------------

    try:

        raw_rows = Menu.getMenu()

        items = [
            parse_row(row)
            for row in raw_rows
        ]

        print(
            f"[notify] Scraped "
            f"{len(items)} menu items."
        )

    except Exception as e:

        print(
            "[notify] Menu scraping failed:"
        )

        print(
            f"  {type(e).__name__}: {e}"
        )

        print(
            "[notify] Continuing to poll."
        )

        return

    # --------------------------------------------------------------
    # Send to Flask backend.
    # --------------------------------------------------------------

    try:

        response = requests.post(
            CALORIE_TRACKER_URL,
            json={
                "items": items
            },
            timeout=10,
        )

        print(
            "[notify] Backend response:",
            response.status_code,
        )

        response.raise_for_status()

        print(
            "[notify] Meal sent successfully."
        )

    except requests.exceptions.RequestException as e:

        print(
            "[notify] Backend request failed:"
        )

        print(
            f"  {e}"
        )


# ============================================================================
# LAST VALUE
# ============================================================================

def load_last_value():

    if LAST_VALUE_FILE.exists():

        try:

            return json.loads(
                LAST_VALUE_FILE.read_text()
            ).get("value")

        except Exception as e:

            print(
                "[Status] Couldn't read last value:",
                e,
            )

    return None


def save_last_value(value):

    LAST_VALUE_FILE.write_text(
        json.dumps(
            {
                "value": value
            }
        )
    )


# ============================================================================
# MAIN
# ============================================================================

def main():

    if not USERNAME or not PASSWORD:

        raise SystemExit(
            "Set UMBC username/password."
        )

    driver = build_driver(
        headless=False
    )

    atexit.register(
        driver.quit
    )

    try:

        # ----------------------------------------------------------
        # Initial authentication.
        # ----------------------------------------------------------

        if (
            not load_cookies(driver)
            or not is_logged_in(driver)
        ):

            login(driver)

            WebDriverWait(
                driver,
                10,
            ).until(
                EC.url_to_be(
                    "https://my.umbc.edu/"
                )
            )

            save_cookies(driver)

        print()
        print(
            "[Status] Starting polling..."
        )

        # ----------------------------------------------------------
        # Poll forever.
        # ----------------------------------------------------------

        while True:

            try:

                current = get_current_value(
                    driver
                )

                print(
                    f"[Status] Current value: "
                    f"{current!r}"
                )

            except Exception as e:

                print(
                    "[Status] Card check failed:"
                )

                print(
                    f"  {type(e).__name__}: {e}"
                )

                try:

                    print(
                        "[Status] Re-authenticating..."
                    )

                    login(driver)

                    WebDriverWait(
                        driver,
                        10,
                    ).until(
                        EC.url_to_be(
                            "https://my.umbc.edu/"
                        )
                    )

                    save_cookies(driver)

                    current = get_current_value(
                        driver
                    )

                except Exception as retry_error:

                    print(
                        "[Status] Retry failed:"
                    )

                    print(
                        f"  {type(retry_error).__name__}: "
                        f"{retry_error}"
                    )

                    time.sleep(
                        POLL_INTERVAL_SECONDS
                    )

                    continue

            # ------------------------------------------------------
            # Detect change.
            # ------------------------------------------------------

            last = load_last_value()

            if last is not None:

                if current != last:

                    print(
                        "[Status] VALUE CHANGED:"
                    )

                    print(
                        f"  Old: {last!r}"
                    )

                    print(
                        f"  New: {current!r}"
                    )

                    notify(
                        f"Value changed: "
                        f"{last!r} -> {current!r}"
                    )

            else:

                print(
                    "[Status] First value recorded."
                )

            save_last_value(current)

            # ------------------------------------------------------
            # Wait.
            # ------------------------------------------------------

            print(
                f"[Status] Sleeping "
                f"{POLL_INTERVAL_SECONDS}s..."
            )

            time.sleep(
                POLL_INTERVAL_SECONDS
            )

    finally:

        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
