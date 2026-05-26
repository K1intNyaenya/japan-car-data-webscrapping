from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import csv
import time
import os

# configurations
CHROMEDRIVER_PATH = "/usr/bin/chromedriver"
BASE_URL          = "https://www.japanesecartrade.com/zenmobilityjapan/stock-list.html"
OUTPUT_FILE       = "car_data.csv"
FAILED_PAGES_FILE = "failed_pages.txt"
SLEEP_BETWEEN_PAGES  = 1.5   # seconds between pages
RESTART_EVERY_PAGES  = 100   # restart browser every N pages to free memory

FIELDNAMES = [
    "ref_id", "name", "chassis_code", "year", "price_usd", "price_jpy",
    "mileage_km", "engine_cc", "fuel", "transmission", "steering",
    "vehicle_type", "options", "has_sunroof", "has_leather", "has_navigation",
    "has_alloy_wheels", "has_4wd", "has_airbag", "has_abs", "has_camera",
    "location", "date_listed", "detail_url"
]

# driver setup
def create_driver():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = Service(executable_path=CHROMEDRIVER_PATH)
    return webdriver.Chrome(service=service, options=chrome_options)


# navigation logic - go to specific page and wait for it to load
def go_to_page(driver, wait, page_number):
    """Navigate to a specific page number (0-indexed in redirectPage)."""
    if page_number == 0:
        driver.get(BASE_URL)
    else:
        driver.execute_script(f"redirectPage('{page_number}');")
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "stock_list_first")))
    time.sleep(1)


def get_total_pages(driver):
    """Read total record count from the page and calculate pages."""
    try:
        total = int(driver.find_element(By.CLASS_NAME, "ttlNowRecords").text.replace(",", ""))
        pages = (total // 10) + (1 if total % 10 > 0 else 0)
        print(f"Total records: {total} → {pages} pages")
        return pages
    except:
        print("Could not read total pages, defaulting to 1308")
        return 1308


# scrapping logic 
def scrape_page(driver):
    """Scrape all car listings on the current page."""
    cars = []
    listings = driver.find_elements(By.CLASS_NAME, "stock_list_first")

    for listing in listings:
        try:
            ref_id = re.search(r'JCT(\d+)', listing.get_attribute("class"))
            ref_id = ref_id.group(1) if ref_id else ""

            head       = listing.find_element(By.CSS_SELECTOR, "h2.list_head a")
            name       = head.text.strip()
            detail_url = head.get_attribute("href")

            chassis_text = listing.find_element(By.CSS_SELECTOR, "h2.list_head a span").text.strip()
            year_match   = re.search(r'\((\d{4})\)', chassis_text)
            year         = year_match.group(1) if year_match else ""
            chassis_code = chassis_text.replace(f"({year})", "").strip()

            def safe_get(selector, attr=None):
                try:
                    el = listing.find_element(By.CSS_SELECTOR, selector)
                    return el.get_attribute(attr) if attr else el.text.strip()
                except:
                    return ""

            price_usd = safe_get(f"strong.price{ref_id}")
            price_jpy = safe_get(f"input#P{ref_id}", attr="value")

            specs        = listing.find_elements(By.CSS_SELECTOR, "ul.list_info li")
            spec_text    = [re.sub(r'\s+', ' ', s.text.strip()) for s in specs]
            mileage      = re.sub(r'[^\d]', '', spec_text[0]) if len(spec_text) > 0 else ""
            engine_cc    = re.sub(r'[^\d]', '', spec_text[1]) if len(spec_text) > 1 else ""
            fuel         = spec_text[2] if len(spec_text) > 2 else ""
            transmission = spec_text[3] if len(spec_text) > 3 else ""
            steering     = spec_text[4] if len(spec_text) > 4 else ""
            veh_type     = spec_text[5] if len(spec_text) > 5 else ""

            options_text = safe_get(".list_acc").replace("Options:", "").strip()
            location     = re.sub(r'\s+', ' ', safe_get(".freight_amount"))
            date_listed  = safe_get("div.list_update label span")

            t = listing.text.lower()
            o = options_text.lower()

            cars.append({
                "ref_id":           ref_id,
                "name":             name,
                "chassis_code":     chassis_code,
                "year":             year,
                "price_usd":        price_usd,
                "price_jpy":        price_jpy,
                "mileage_km":       mileage,
                "engine_cc":        engine_cc,
                "fuel":             fuel,
                "transmission":     transmission,
                "steering":         steering,
                "vehicle_type":     veh_type,
                "options":          options_text,
                "has_sunroof":      1 if "sun roof"    in o else 0,
                "has_leather":      1 if "leather"     in o else 0,
                "has_navigation":   1 if "navigation"  in o else 0,
                "has_alloy_wheels": 1 if "alloy"       in o else 0,
                "has_4wd":          1 if "4wd"         in t else 0,
                "has_airbag":       1 if "airbag"      in t else 0,
                "has_abs":          1 if "abs"         in t else 0,
                "has_camera":       1 if "camera"      in t else 0,
                "location":         location,
                "date_listed":      date_listed,
                "detail_url":       detail_url,
            })

        except Exception as e:
            print(f"  [!] Skipped listing: {e}")

    return cars


# resume logic - check existing CSV to determine which page to start from
def get_start_page():
    """If CSV already exists, count rows to figure out which page to resume from."""
    if not os.path.exists(OUTPUT_FILE):
        return 0, False  # start fresh

    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        rows = sum(1 for _ in f) - 1  # subtract header

    if rows <= 0:
        return 0, False

    start_page = rows // 10  # 10 cars per page
    print(f"Found {rows} existing records → resuming from page {start_page + 1}")
    return start_page, True  # return page index and append=True flag


# main
def main():
    start_page, append_mode = get_start_page()

    driver = create_driver()
    wait   = WebDriverWait(driver, 15)
    driver.get(BASE_URL)
    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "stock_list_first")))

    total_pages  = get_total_pages(driver)
    failed_pages = []
    total_scraped = 0

    # Open CSV in append or write mode depending on resume state
    file_mode = "a" if append_mode else "w"
    csv_file  = open(OUTPUT_FILE, file_mode, newline="", encoding="utf-8")
    writer    = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
    if not append_mode:
        writer.writeheader()

    # Navigate to start page if resuming
    if start_page > 0:
        print(f"Navigating to page {start_page + 1}...")
        go_to_page(driver, wait, start_page)

    for page in range(start_page, total_pages):
        try:
            print(f"Scraping page {page + 1} of {total_pages}...")

            if page != start_page:
                go_to_page(driver, wait, page)

            page_cars = scrape_page(driver)
            writer.writerows(page_cars)
            csv_file.flush()
            total_scraped += len(page_cars)

            print(f"  -> {len(page_cars)} cars | Total new: {total_scraped}")
            time.sleep(SLEEP_BETWEEN_PAGES)

            # Restart browser every N pages to free memory
            if (page + 1) % RESTART_EVERY_PAGES == 0:
                print("  Restarting browser to free memory...")
                driver.quit()
                driver = create_driver()
                wait   = WebDriverWait(driver, 15)
                driver.get(BASE_URL)
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "stock_list_first")))
                go_to_page(driver, wait, page + 1)

        except Exception as e:
            print(f"  [!] Failed on page {page + 1}: {e}")
            failed_pages.append(page + 1)
            # Try to recover
            try:
                driver.get(BASE_URL)
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "stock_list_first")))
                go_to_page(driver, wait, page)
                time.sleep(3)
            except:
                pass
            continue

    csv_file.close()
    driver.quit()

    print(f"\nDone! {total_scraped} new records saved to {OUTPUT_FILE}")

    if failed_pages:
        with open(FAILED_PAGES_FILE, "w") as f:
            f.write("\n".join(map(str, failed_pages)))
        print(f"Failed pages saved to {FAILED_PAGES_FILE}: {failed_pages}")


if __name__ == "__main__":
    main()