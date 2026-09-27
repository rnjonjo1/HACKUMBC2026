url='https://dineoncampus.com/UMBC/whats-on-the-menu/true-grit-s/2026-09-26/'

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

CHROMIUM_BINARY = "/usr/bin/chromium"
CHROMEDRIVER_BINARY = "/usr/bin/chromedriver"

options = webdriver.ChromeOptions()
options.binary_location = CHROMIUM_BINARY
options.add_argument("--headless=new")


service = Service(CHROMEDRIVER_BINARY)
driver = webdriver.Chrome(service=service, options=options)

driver.get(url)

input("Press Enter to close...")
driver.quit()