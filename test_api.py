import base64
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def save_base64_image(base64_str, filename):
    try:
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]
        img_data = base64.b64decode(base64_str)
        with open(filename, 'wb') as f:
            f.write(img_data)
        print(f"✅ Imagen guardada: {filename}")
        return True
    except Exception as e:
        print(f"❌ Error al procesar Base64: {e}")
        return False

def download_whatsapp_dp(phone_number, country_dial_code):
    chrome_options = Options()
    # Mantenemos AutomationControlled desactivado para evitar bloqueos
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 25)

    try:
        driver.get("https://toolzin.com/tools/whatsapp-dp-downloader/")

        # 1. Selector de País
        print(f"🌍 Seleccionando código: +{country_dial_code}")
        wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "iti__selected-flag"))).click()
        wait.until(EC.element_to_be_clickable((By.XPATH, f"//li[@data-dial-code='{country_dial_code}']"))).click()

        # 2. Número y Envío
        driver.find_element(By.ID, "phone").send_keys(phone_number)
        driver.find_element(By.ID, "btn_submit").click()
        print("⏳ Solicitud enviada. Esperando respuesta del servidor...")

        # 3. Esperar a que el contenedor AJAX tenga ALGO de texto o hijos
        # Esto evita el error de "No se pudo identificar" al leer muy rápido
        wait.until(lambda d: d.find_element(By.ID, "ajax_result").get_attribute("innerHTML").strip() != "")

        # 4. Capturar el contenedor de resultados
        result_div = driver.find_element(By.ID, "ajax_result")
        res_html = result_div.get_attribute("innerHTML")

        # --- LÓGICA DE DETECCIÓN MEJORADA ---
        
        # Caso A: No disponible / Privado
        if "DP is unavailable" in res_html or "☹️" in res_html:
            print(f"☹️ {phone_number}: La imagen no es pública o el número no existe.")
            return

        # Caso B: Éxito (Buscamos la imagen)
        try:
            # Esperamos a que la imagen sea visible específicamente
            img_selector = "#post_container_0 img.post-image"
            img_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, img_selector)))
            
            print("🔍 Contenedor de imagen hallado. Esperando conversión a Base64...")
            
            # Polling para el SRC real
            src_final = ""
            for _ in range(15):
                src_data = img_element.get_attribute("src")
                if src_data and src_data.startswith("data:image"):
                    src_final = src_data
                    break
                time.sleep(1)

            if src_final:
                save_base64_image(src_final, f"{phone_number}.jpg")
            else:
                print(f"❌ {phone_number}: Se agotó el tiempo esperando la imagen real.")
                
        except Exception:
            print(f"❌ {phone_number}: No se encontró la imagen en el resultado (posible cambio de estructura).")

    except Exception as e:
        print(f"❌ Error de sistema: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    # Prueba con el número que te dio error de "No disponible"
    download_whatsapp_dp("922795406", "51")