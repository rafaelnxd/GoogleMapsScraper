import csv
import os
import asyncio
from flask import Flask, render_template, request, send_file, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain.globals import set_debug
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv
import math

app = Flask(__name__)
load_dotenv()
set_debug(True)

# Configuração do Selenium
chrome_options = Options()
chrome_options.add_argument("--headless")
service = Service('chromedriver.exe')

# Configuração do LangChain
llm = ChatOpenAI(
    model="gpt-3.5-turbo",
    temperature=0.7,
    api_key=os.getenv("OPENAI_API_KEY")
)

def extract_items(driver, found_places):
    maps_data = []
    wait = WebDriverWait(driver, 10)
    try:
        items = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".Nv2PK")))
        for el in items:
            data = {}
            try:
                data["title"] = el.find_element(By.CSS_SELECTOR, ".qBF1Pd").text.strip()
                print(f"Cidade extraída: {data['title']}")
            except:
                data["title"] = "N/A"
            
            try:
                data["avg_rating"] = el.find_element(By.CSS_SELECTOR, ".MW4etd").text.strip()
            except:
                data["avg_rating"] = "N/A"
            
            try:
                data["reviews"] = el.find_element(By.CSS_SELECTOR, ".UY7F9").text.replace("(", "").replace(")", "").strip()
            except:
                data["reviews"] = "N/A"
            
            try:
                data["address"] = el.find_element(By.CSS_SELECTOR, ".W4Efsd:last-child >.W4Efsd:nth-of-type(1) > span:last-child").text.replace("·", "").strip()
            except:
                data["address"] = "N/A"
            
            try:
                data["website"] = el.find_element(By.CSS_SELECTOR, "a.lcr4fd").get_attribute("href")
            except:
                data["website"] = "N/A"
            
            try:
                data["category"] = el.find_element(By.CSS_SELECTOR, ".W4Efsd:last-child >.W4Efsd:nth-of-type(1) > span:first-child").text.replace("·", "").strip()
            except:
                data["category"] = "N/A"
            
            try:
                description = el.find_element(By.CSS_SELECTOR, ".W4Efsd:last-child >.W4Efsd:nth-of-type(2)").text.strip()
                phone_match = re.search(r'((\+?\d{1,2}[ -]?)?(\(?\d{3}\)?[ -]?\d{3,4}[ -]?\d{4}|\(?\d{2,3}\)?[ -]?\d{2,3}[ -]?\d{2,3}[ -]?\d{2,3}))', description)
                if phone_match:
                    data["phone_num"] = phone_match.group(0).strip()
                else:
                    data["phone_num"] = "N/A"
            except:
                data["phone_num"] = "N/A"

            place_key = (data["title"], data["phone_num"])
            if place_key in found_places:
                print(f"Duplicate in this iteration: {data['title']} - Skipping.")
                continue
            found_places.add(place_key)
            
            try:
                link = el.find_element(By.CSS_SELECTOR, "a.hfpxzc").get_attribute("href")
                data["link"] = link
                data["latitude"] = link.split("!8m2!3d")[1].split("!4d")[0]
                data["longitude"] = link.split("!4d")[1].split("!16s")[0]
                data["dataId"] = link.split("1s")[1].split("!8m")[0]
            except:
                data["link"] = "N/A"
                data["latitude"] = "N/A"
                data["longitude"] = "N/A"
                data["dataId"] = "N/A"
            
            maps_data.append(data)
    except Exception as e:
        print(f"Error extracting data: {e}")
    return maps_data

def scroll_page(driver, scroll_container, item_target_count, found_places):
    items = []
    previous_height = driver.execute_script(f"return document.querySelector('{scroll_container}').scrollHeight")
    
    while len(items) < item_target_count:
        new_items = extract_items(driver, found_places)
        if not new_items:
            break
        items.extend(new_items)
        
        # Scroll down
        driver.execute_script(f"document.querySelector('{scroll_container}').scrollTo(0, document.querySelector('{scroll_container}').scrollHeight)")
        
    
        start_time = time.time()
        while True:
            time.sleep(2)
            new_height = driver.execute_script(f"return document.querySelector('{scroll_container}').scrollHeight")
            if new_height > previous_height:
                previous_height = new_height
                break
            elif time.time() - start_time > 10:
                break
        
        if len(items) >= item_target_count:
            break
            
    return items[:item_target_count]



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

def update_csv_with_data(csv_file_path, new_data):
    existing_data = {}

    if os.path.exists(csv_file_path):
        with open(csv_file_path, mode="r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                existing_data[(row["title"], row["phone_num"])] = row

    with open(csv_file_path, mode="a", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["title", "avg_rating", "reviews", "address", "website", "category", "phone_num", "latitude", "longitude", "link", "dataId"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        if not existing_data:
            writer.writeheader()
        
        for data in new_data:
            key = (data["title"], data["phone_num"])
            if key in existing_data:
                print(f"Duplicado encontrado: {data['title']} - Dados existentes não serão atualizados.")
            else:
                print(f"Adicionando novo dado: {data['title']}")
                writer.writerow(data)
		

def get_maps_data(establishment_type, latitude, longitude, search_radius, result_count):
    start_time = time.time()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    zoom_level = radius_to_zoom(search_radius)
    url = f"https://www.google.com/maps/search/{establishment_type}/@{latitude},{longitude},{zoom_level}z"
    driver.get(url)
    time.sleep(5)


    found_places = set()

    data = scroll_page(driver, ".m6QErb[aria-label]", result_count, found_places)
    driver.quit()
    
    csv_file_path = f"{establishment_type.replace(' ', '_')}_maps_data.csv"
    
    update_csv_with_data(csv_file_path, data)
    
    end_time = time.time()
    duration = end_time - start_time
    file_size = os.path.getsize(csv_file_path)

    log_scraping_info(establishment_type, latitude, longitude, search_radius, result_count, duration, file_size)
    
    return csv_file_path


import numpy as np

def grid_search(establishment_type, min_latitude, max_latitude, min_longitude, max_longitude, search_radius, result_count):
    csv_file_path = f"{establishment_type.replace(' ', '_')}_maps_data.csv"
    lat_increment = (max_latitude - min_latitude) / 10
    long_increment = (max_longitude - min_longitude) / 10
    
    for lat in np.arange(min_latitude, max_latitude, lat_increment):
        for long in np.arange(min_longitude, max_longitude, long_increment):
            print(f"Searching at ({lat}, {long})")
            get_maps_data(establishment_type, lat, long, search_radius, result_count)

    
    return csv_file_path

modelo_mensagem = PromptTemplate(
    template="""

You are a marketing and data analysis expert at SyOS, a company that provides temperature and humidity sensors for supermarkets and pharmacies. Your task is to create a detailed profile that includes an overall assessment of the client, their potential needs, and a recommendation for action.

Use the following client information to create the profile:

- Name: {title}
- Category: {category}
- Average Rating: {avg_rating}
- Number of Reviews: {reviews}
- Address: {address}
- Website: {website}
- Phone Number: {phone_num}

The profile should include:
1. An overall assessment of the client (e.g., if they are a high-value potential client or a client who may need more engagement).
2. Identified needs and opportunities based on the provided information.
3. Specific action recommendations that SyOS can take to better engage the client (such as sending personalized emails, special offers, etc.).
4. Classification of the client as "hot", "warm", or "cold" based on the information and analysis performed.

The response should be clear, detailed, and useful for the SyOS marketing team to take targeted actions.
""",  
    input_variables=["title", "category", "avg_rating", "reviews", "address", "website", "phone_num"]
)

cadeia_mensagem = LLMChain(
    llm=llm,
    prompt=modelo_mensagem,
    output_parser=StrOutputParser()
)

modelo_email = PromptTemplate(
    template="""You are a marketing email writing expert at SyOS. Using the provided detailed client profile, create an engaging and persuasive email text. The email should introduce SyOS and explain how our temperature and humidity sensors can benefit the client. Personalize the email based on the profile information and provide a clear call to action.

Here is the client profile information:
{profile}

The email text should include:
1. A personalized greeting.
2. An introduction to SyOS and the value of our products.
3. A highlight of the client's specific needs and how SyOS can meet them.
4. A clear and direct call to action.

The text should be engaging and professional.""",  
    input_variables=["profile"]
)

cadeia_email = LLMChain(
    llm=llm,
    prompt=modelo_email,
    output_parser=StrOutputParser()
)

async def generate_emails(input_csv_path):
    output_csv_file_path = "emails_personalizados.csv"
    
    with open(input_csv_path, mode="r", encoding="utf-8") as csvfile, \
         open(output_csv_file_path, mode="w", newline='', encoding="utf-8") as outfile:
        
        reader = csv.DictReader(csvfile)
        fieldnames = ['title', 'email_text']
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            cliente_info = {
                "title": row["title"],
                "category": row["category"],
                "avg_rating": row["avg_rating"],
                "reviews": row["reviews"],
                "address": row["address"],
                "website": row["website"],
                "phone_num": row["phone_num"],
            }
            
            perfil_cliente = cadeia_mensagem.run(cliente_info)
            texto_email = cadeia_email.run({"profile": perfil_cliente})
            
            writer.writerow({'title': row['title'], 'email_text': texto_email})
    
    return output_csv_file_path

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        print("Received data:", request.form)
        if request.is_json:
            data = request.json
        else:
            data = request.form
        
        establishment_type = data.get('establishment_type')
        min_latitude = float(data.get('min_latitude'))
        max_latitude = float(data.get('max_latitude'))
        min_longitude = float(data.get('min_longitude'))
        max_longitude = float(data.get('max_longitude'))
        search_radius = int(data.get('search_radius'))
        result_count = int(data.get('result_count', 50))  
        
        print(f"Parsed data: type={establishment_type}, min_lat={min_latitude}, max_lat={max_latitude}, min_long={min_longitude}, max_long={max_longitude}, radius={search_radius}, count={result_count}")
        
        if not all([establishment_type, min_latitude, max_latitude, min_longitude, max_longitude, search_radius]):
            return jsonify({"error": "Missing required fields"}), 400
        
        try:
            csv_file_path = grid_search(establishment_type, min_latitude, max_latitude, min_longitude, max_longitude, search_radius, result_count)
            return jsonify({"success": True, "csv_file": csv_file_path})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return render_template('index.html')

@app.route('/download/<filename>')
def download_file(filename):
    return send_file(filename, as_attachment=True)

@app.route('/generate_emails', methods=['POST'])
def generate_emails_route():
    input_csv_path = request.json['csv_file']
    output_csv_path = asyncio.run(generate_emails(input_csv_path))
    return jsonify({"success": True, "emails_csv": output_csv_path})

if __name__ == '__main__':
    app.run(debug=True)