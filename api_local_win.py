import base64
import time
import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import phonenumbers
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from PIL import Image
import io

app = Flask(__name__)
CORS(app)  # Permitir CORS desde cualquier origen

# Carpetas separadas para mantener el orden
ORIGINALS_FOLDER = "downloads/originals"
ICONS_FOLDER = "downloads/icons"
LOG_FILE = "downloads/requests_log.json"

for folder in [ORIGINALS_FOLDER, ICONS_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Inicializar archivo de log si no existe
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'w') as f:
        json.dump({}, f)

def load_request_log():
    """Carga el registro de solicitudes desde el archivo JSON."""
    try:
        with open(LOG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error cargando log: {e}")
        return {}

def save_request_log(log_data):
    """Guarda el registro de solicitudes en el archivo JSON."""
    try:
        with open(LOG_FILE, 'w') as f:
            json.dump(log_data, f, indent=2)
    except Exception as e:
        print(f"Error guardando log: {e}")

def register_request(phone_key, status, message=""):
    """Registra una solicitud en el log con timestamp."""
    log = load_request_log()
    log[phone_key] = {
        "status": status,  # "success", "private", "error"
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "attempts": log.get(phone_key, {}).get("attempts", 0) + 1
    }
    save_request_log(log)

def check_request_history(phone_key):
    """Verifica si un número ya fue consultado anteriormente y su resultado."""
    log = load_request_log()
    return log.get(phone_key, None)

def create_optimized_driver(headless=True):
    """Crea un driver optimizado para Windows local."""
    chrome_options = Options()
    
    # Modo headless opcional (útil para desarrollo ver el navegador)
    if headless:
        chrome_options.add_argument("--headless=new")
    
    # Opciones para Windows
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # WebDriver Manager se encarga de descargar el chromedriver correcto automáticamente
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver

# Inicializar driver global (puedes cambiar headless=False para ver el navegador)
global_driver = create_optimized_driver(headless=True)

def process_and_save_image(src_base64, phone_number, country_dial_code):
    """Decodifica Base64 y guarda la imagen original."""
    try:
        base64_data = src_base64.split(",")[1]
        img_bytes = base64.b64decode(base64_data)
        
        file_path = os.path.join(ORIGINALS_FOLDER, f"{country_dial_code}{phone_number}.jpg")
        with open(file_path, 'wb') as f:
            f.write(img_bytes)
        return file_path
    except Exception as e:
        print(f"Error procesando imagen: {e}")
        return None

def create_icon(phone_number):
    """Crea una versión de 256x256 de una imagen existente."""
    original_path = os.path.join(ORIGINALS_FOLDER, f"{phone_number}.jpg")
    icon_path = os.path.join(ICONS_FOLDER, f"{phone_number}_icon.jpg")
    
    if os.path.exists(original_path):
        with Image.open(original_path) as img:
            # Redimensionar usando LANCZOS para alta calidad
            img = img.convert("RGB") # Asegurar compatibilidad con JPEG
            img = img.resize((256, 256), Image.Resampling.LANCZOS)
            img.save(icon_path, "JPEG", quality=90)
        return icon_path
    return None

def image_to_base64(file_path):
    """Convierte una imagen a base64 para respuesta JSON."""
    try:
        with open(file_path, 'rb') as img_file:
            img_bytes = img_file.read()
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')
            return f"data:image/jpeg;base64,{img_base64}"
    except Exception as e:
        print(f"Error convirtiendo imagen a base64: {e}")
        return None

def scrape_whatsapp_image(phone_number, country_dial_code):
    """Lógica de navegación Selenium."""
    driver = global_driver
    wait = WebDriverWait(driver, 15)
    phone_key = f"{country_dial_code}{phone_number}"

    try:
        driver.get("https://toolzin.com/tools/whatsapp-dp-downloader/")

        # Seleccionar País
        wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "iti__selected-flag"))).click()
        wait.until(EC.element_to_be_clickable((By.XPATH, f"//li[@data-dial-code='{country_dial_code}']"))).click()

        # Input y Submit
        driver.find_element(By.ID, "phone").send_keys(phone_number)
        driver.find_element(By.ID, "btn_submit").click()

        # Esperar contenido AJAX
        wait.until(lambda d: d.find_element(By.ID, "ajax_result").get_attribute("innerHTML").strip() != "")
        
        res_html = driver.find_element(By.ID, "ajax_result").get_attribute("innerHTML")

        if "DP is unavailable" in res_html or "☹️" in res_html:
            register_request(phone_key, "private", "Foto de perfil privada o no disponible")
            return "private"

        img_element = driver.find_element(By.CSS_SELECTOR, "#post_container_0 img.post-image")
        
        # Polling para el Base64
        for _ in range(20):
            src_data = img_element.get_attribute("src")
            if src_data and src_data.startswith("data:image"):
                result = process_and_save_image(src_data, phone_number, country_dial_code)
                if result:
                    register_request(phone_key, "success", "Imagen descargada exitosamente")
                return result
            time.sleep(0.5)

    except Exception as e:
        print(f"Error en Scraper: {e}")
        register_request(phone_key, "error", str(e))
        return "error"
    
    register_request(phone_key, "error", "No se pudo obtener la imagen Base64")
    return None

def separar_numero(numero_completo):
    try:
        # Es necesario que el número empiece con "+" para que detecte el país automáticamente
        if not numero_completo.startswith("+"):
            numero_completo = "+" + numero_completo
            
        # Parsear el número
        parsed_number = phonenumbers.parse(numero_completo, None)
        
        # Obtener las partes como STRINGS (importante para el resto del código)
        codigo_pais = str(parsed_number.country_code)  # Ejemplo: "51"
        numero_nacional = str(parsed_number.national_number)  # Ejemplo: "987654321"
        
        return codigo_pais, numero_nacional
    except Exception as e:
        print(f"Error al procesar número '{numero_completo}': {e}")
        return None, None


@app.route('/get_dp', methods=['GET'])
def api_get_dp():
    # pasar solo a un argumento 
    raw_number = request.args.get('number')
    
    if not raw_number:
        return jsonify({
            "status": "error", 
            "message": "Falta parámetro 'number' (formato: +51987654321 o 51987654321)",
            "phone_number": None,
            "image": None
        }), 400
    
    country, number = separar_numero(raw_number)

    is_icon = request.args.get('icon', 'false').lower() == 'true'

    if not number or not country:
        return jsonify({
            "status": "error", 
            "message": "Número inválido. Use formato internacional: +51987654321",
            "phone_number": raw_number,
            "image": None
        }), 400

    phone_key = f"{country}{number}"
    
    # --- PASO 1: VERIFICAR HISTORIAL DE SOLICITUDES ---
    history = check_request_history(phone_key)
    
    if history:
        # Si anteriormente fue privado o error, no reintentar
        if history["status"] in ["private", "error"]:
            print(f"⚠️ Número ya consultado previamente: {phone_key} - Estado: {history['status']}")
            return jsonify({
                "status": "negative" if history["status"] == "private" else "error",
                "message": history["message"],
                "phone_number": f"+{country}{number}",
                "image": None,
                "last_attempt": history["timestamp"],
                "attempts": history["attempts"]
            }), 404 if history["status"] == "private" else 500

    # --- PASO 2: VALIDAR SI YA EXISTE (Caché) ---
    original_file = os.path.join(ORIGINALS_FOLDER, f"{phone_key}.jpg")
    
    if os.path.exists(original_file):
        print(f"📦 Servido desde caché: {number}")
        # Actualizar registro como exitoso si existe el archivo
        register_request(phone_key, "success", "Servido desde caché")
        
        file_to_send = original_file
        if is_icon:
            icon_file = os.path.join(ICONS_FOLDER, f"{phone_key}_icon.jpg")
            if not os.path.exists(icon_file):
                create_icon(phone_key)
            file_to_send = icon_file
        
        # Convertir imagen a base64 y devolver JSON
        image_b64 = image_to_base64(file_to_send)
        if image_b64:
            return jsonify({
                "status": "success",
                "message": "Imagen encontrada en caché",
                "phone_number": f"+{country}{number}",
                "image": image_b64,
                "format": "icon" if is_icon else "original"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Error al codificar imagen",
                "phone_number": f"+{country}{number}",
                "image": None
            }), 500

    # --- PASO 3: SI NO EXISTE, REALIZAR SCRAPPING ---
    print(f"🔍 Iniciando scrapping para: +{country} {number}")
    result = scrape_whatsapp_image(number, country)

    if result == "private":
        return jsonify({
            "status": "negative",
            "message": "Foto de perfil privada o no disponible",
            "phone_number": f"+{country}{number}",
            "image": None
        }), 404
    elif result == "error" or result is None:
        return jsonify({
            "status": "error",
            "message": "Fallo en el proceso de scraping",
            "phone_number": f"+{country}{number}",
            "image": None
        }), 500
    else:
        # Si se pidió icono, generarlo tras el scrapping
        file_to_send = result
        if is_icon:
            icon_path = create_icon(phone_key)
            file_to_send = icon_path
        
        # Convertir imagen a base64 y devolver JSON
        image_b64 = image_to_base64(file_to_send)
        if image_b64:
            return jsonify({
                "status": "success",
                "message": "Imagen descargada exitosamente",
                "phone_number": f"+{country}{number}",
                "image": image_b64,
                "format": "icon" if is_icon else "original"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Error al codificar imagen",
                "phone_number": f"+{country}{number}",
                "image": None
            }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Endpoint para verificar el estado de la API."""
    return jsonify({
        "status": "ok",
        "message": "API funcionando correctamente",
        "version": "local_win_1.0"
    }), 200

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 WhatsApp DP Scraper API - Windows Local Edition")
    print("=" * 60)
    print("📍 Servidor corriendo en: http://localhost:5000")
    print("📖 Documentación: http://localhost:5000/health")
    print("\n💡 Ejemplo de uso:")
    print("   http://localhost:5000/get_dp?number=+51987654321")
    print("   http://localhost:5000/get_dp?number=51987654321&icon=true")
    print("\n⚙️  Modo headless: Activado (cambiar en línea 94 para ver navegador)")
    print("=" * 60)
    
    try:
        app.run(host='127.0.0.1', port=5000, debug=True, threaded=False)
    finally:
        print("\n🛑 Cerrando navegador...")
        global_driver.quit()
        print("✅ Navegador cerrado correctamente")
