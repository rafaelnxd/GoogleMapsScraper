import csv
import os
import time
import math
import numpy as np
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from tqdm import tqdm
import re
from multiprocessing import Pool

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.3")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--renderer=blink")
chrome_options.add_argument("--disable-cookies")
service = Service('chromedriver.exe')

prefs = {
    "profile.managed_default_content_settings.images": 2
}
chrome_options.add_experimental_option("prefs", prefs)


def calculate_increments(min_lat, max_lat, min_lon, max_lon, target_points=100, min_increment=0.001, max_increment=0.3):
    # Calculate the size of the area
    lat_range = max_lat - min_lat
    lon_range = max_lon - min_lon
    
    # Calculate the increment that would give us exactly the target number of points
    lat_increment = math.sqrt((lat_range * lon_range) / target_points)
    lon_increment = lat_increment
    
    # Adjust for Earth's curvature (longitude distances vary with latitude)
    average_lat = (min_lat + max_lat) / 2
    lon_increment = lat_increment / math.cos(math.radians(average_lat))
    
    # Ensure the increments are within the specified bounds
    lat_increment = max(min(lat_increment, max_increment), min_increment)
    lon_increment = max(min(lon_increment, max_increment), min_increment)
    
    return lat_increment, lon_increment

def extract_items(driver, found_places):
    maps_data = []
    wait = WebDriverWait(driver, 10)

    try:
        items = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".Nv2PK")))
        
        for el in items:
            data = extract_item_data(el)
            
            place_key = (data["title"], data["phone_num"])
            if place_key in found_places:
                print(f"Duplicate in this iteration: {data['title']} - Skipping.")
                continue
            
            found_places.add(place_key)
            maps_data.append(data)
    
    except Exception as e:
        print(f"Error extracting data: {e}")
    
    return maps_data

def extract_item_data(el):
    data = {
        "title": safe_find(el, ".qBF1Pd"),
        "avg_rating": safe_find(el, ".MW4etd"),
        "reviews": safe_find(el, ".UY7F9", process=lambda x: x.replace("(", "").replace(")", "")),
        "address": safe_find(el, ".W4Efsd:last-child >.W4Efsd:nth-of-type(1) > span:last-child", process=lambda x: x.replace("·", "")),
        "website": safe_find(el, "a.lcr4fd", attribute="href"),
        "category": safe_find(el, ".W4Efsd:last-child >.W4Efsd:nth-of-type(1) > span:first-child", process=lambda x: x.replace("·", "")),
        "phone_num": extract_phone_number(el),
    }
    
    if data["title"] != "N/A":
        print(f"Cidade extraída: {data['title']}")
    
    link_data = extract_link_data(el)
    data.update(link_data)
    
    return data

def safe_find(el, selector, attribute=None, process=None):
    try:
        found = el.find_element(By.CSS_SELECTOR, selector)
        value = found.get_attribute(attribute) if attribute else found.text
        return process(value.strip()) if process else value.strip()
    except:
        return "N/A"

def extract_phone_number(el):
    try:
        description = el.find_element(By.CSS_SELECTOR, ".W4Efsd:last-child >.W4Efsd:nth-of-type(2)").text.strip()
        phone_match = re.search(r'((\+?\d{1,2}[ -]?)?(\(?\d{3}\)?[ -]?\d{3,4}[ -]?\d{4}|\(?\d{2,3}\)?[ -]?\d{2,3}[ -]?\d{2,3}[ -]?\d{2,3}))', description)
        return phone_match.group(0).strip() if phone_match else "N/A"
    except:
        return "N/A"

def extract_link_data(el):
    try:
        link = el.find_element(By.CSS_SELECTOR, "a.hfpxzc").get_attribute("href")
        latitude, longitude = link.split("!8m2!3d")[1].split("!4d")
        data_id = link.split("1s")[1].split("!8m")[0]
        return {
            "link": link,
            "latitude": latitude,
            "longitude": longitude.split("!16s")[0],
            "dataId": data_id
        }
    except:
        return {
            "link": "N/A",
            "latitude": "N/A",
            "longitude": "N/A",
            "dataId": "N/A"
        }

def scroll_page(driver, scroll_container, item_target_count, found_places):
    """
    Scrolls a page until a target number of items are found.

    Args:
        driver (webdriver): The Selenium webdriver instance.
        scroll_container (str): The CSS selector for the scroll container.
        item_target_count (int): The target number of items to find.
        found_places (list): A list to store the found items.

    Returns:
        list: The list of found items.
    """

    items = []
    previous_height = driver.execute_script(f"return document.querySelector('{scroll_container}').scrollHeight")
    timeout = 10  # seconds

    while len(items) < item_target_count:
        new_items = extract_items(driver, found_places)
        if not new_items:
            break

        # Only extend the list if we haven't reached the target count yet
        items.extend(new_items[:item_target_count - len(items)])

        # Scroll down
        driver.execute_script(f"document.querySelector('{scroll_container}').scrollTo(0, document.querySelector('{scroll_container}').scrollHeight)")

        # Wait until scroll completes and new elements are loaded
        start_time = time.time()
        while True:
            time.sleep(2)
            new_height = driver.execute_script(f"return document.querySelector('{scroll_container}').scrollHeight")
            if new_height > previous_height:
                previous_height = new_height
                break
            elif time.time() - start_time > timeout:
                break

        # Check if we've reached the target count
        if len(items) >= item_target_count:
            break

    return items

def radius_to_zoom(radius_meters):
    earth_circumference = 40075017
    pixels_per_tile = 256
    zoom_level = math.log2((earth_circumference * math.cos(0)) / (radius_meters * pixels_per_tile))
    return max(min(int(zoom_level), 21), 0)

def log_scraping_info(establishment_type, latitude, longitude, search_radius, result_count, duration, file_size):
    log_file_path = "scraping_log.csv"
    log_exists = os.path.exists(log_file_path)

    with open(log_file_path, mode="a", newline="", encoding="utf-8") as logfile:
        fieldnames = ["timestamp", "establishment_type", "latitude", "longitude", "search_radius", "result_count", "duration_seconds", "file_size_kb"]
        writer = csv.DictWriter(logfile, fieldnames=fieldnames)

        if not log_exists:
            writer.writeheader()

        writer.writerow({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "establishment_type": establishment_type,
            "latitude": latitude,
            "longitude": longitude,
            "search_radius": search_radius,
            "result_count": result_count,
            "duration_seconds": duration,
            "file_size_kb": file_size / 1024
        })

def update_csv_with_data(csv_file_path, new_data, establishment_type):
    existing_data = {}

    if os.path.exists(csv_file_path):
        with open(csv_file_path, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                existing_data[(row["title"], row["phone_num"], row["establishment_type"])] = row

    with open(csv_file_path, mode="a", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["establishment_type", "title", "avg_rating", "reviews", "address", "website", "category", "phone_num", "latitude", "longitude", "link", "dataId"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        if not existing_data:
            writer.writeheader()
        
        for data in new_data:
            key = (data["title"], data["phone_num"], establishment_type)
            if key in existing_data:
                print(f"Duplicado encontrado: {data['title']} ({establishment_type}) - Dados existentes não serão atualizados.")
            else:
                print(f"Adicionando novo dado: {data['title']} ({establishment_type})")
                data["establishment_type"] = establishment_type
                writer.writerow(data)

def get_maps_data(establishment_type, latitude, longitude, search_radius, result_count):
    start_time = time.time()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    zoom_level = radius_to_zoom(search_radius)
    url = f"https://www.google.com/maps/search/{establishment_type}/@{latitude},{longitude},{zoom_level}z"
    print(f"Fetching data from: {url}")
    driver.get(url)
    time.sleep(5)

    # Set to keep track of found places in the current scraping session
    found_places = set()

    data = scroll_page(driver, ".m6QErb[aria-label]", result_count, found_places)
    driver.quit()
    
    csv_file_path = "combined_maps_data.csv"
    
    update_csv_with_data(csv_file_path, data, establishment_type)  # Pass establishment_type here
    
    end_time = time.time()
    duration = end_time - start_time
    file_size = os.path.getsize(csv_file_path)

    log_scraping_info(establishment_type, latitude, longitude, search_radius, result_count, duration, file_size)
    
    return csv_file_path

def process_grid_point(args):
    step, establishment_type, lat, lon, search_radius, result_count = args
    print(f"Step {step + 1}: Processing grid point at latitude {lat}, longitude {lon}")
    return get_maps_data(establishment_type, lat, lon, search_radius, result_count)

def grid_search(establishment_types, min_latitude, max_latitude, min_longitude, max_longitude, search_radius, result_count):
    csv_file_path = "combined_maps_data.csv"
    
    lat_increment, long_increment = calculate_increments(min_latitude, max_latitude, min_longitude, max_longitude)
    
    print(f"Latitude increment: {lat_increment}")
    print(f"Longitude increment: {long_increment}")
    
    grid_points = [(lat, lon) for lat in np.arange(min_latitude, max_latitude, lat_increment) 
                             for lon in np.arange(min_longitude, max_longitude, long_increment)]
    

    args_list = [(i, establishment_type, lat, lon, search_radius, result_count) 
                 for i, (lat, lon) in enumerate(grid_points)
                 for establishment_type in establishment_types]
    

    with Pool(processes=3) as pool:

        results = list(tqdm(pool.imap(process_grid_point, args_list), 
                            total=len(args_list), desc="Processing Grid Cells"))

    return results

if __name__ == "__main__":
    establishment_types = ["supermercado", "mercado", "hipermercado"]
    min_latitude = -23.5505
    max_latitude = -23.4977
    min_longitude = -46.6476
    max_longitude = -46.6063
    search_radius = 5  
    result_count = 30
    
    grid_search(establishment_types, min_latitude, max_latitude, min_longitude, max_longitude, search_radius, result_count)