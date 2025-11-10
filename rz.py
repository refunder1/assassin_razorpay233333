import os
import time
import json
import random
import tempfile
import shutil
import zipfile
import signal
import requests
import psutil
from typing import Optional, Tuple

from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ---------- CONFIG ----------
BOT_TOKEN = "YOUR_BOT_TOKEN"
CHAT_ID = "CHAT_ID"
WAIT_SECONDS = 6
PROXY_FILE = "proxy.txt" #format -: ip:port:username:pass
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5500

app = Flask(__name__)

def load_proxies(filename=PROXY_FILE):
    if not os.path.exists(filename):
        return []
    out = []
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(line)
    return out

def parse_proxy(proxy_string: str):
    parts = proxy_string.split(":")
    if len(parts) >= 4:
        return {"host": parts[0], "port": parts[1], "username": parts[2], "password": parts[3]}
    elif len(parts) >= 2:
        return {"host": parts[0], "port": parts[1], "username": None, "password": None}
    return None

def create_proxy_auth_extension(proxy_config):
    ext_dir = tempfile.mkdtemp(prefix="proxy_ext_")
    manifest = {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "proxy_auth_ext",
        "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
        "background": {"scripts": ["background.js"]},
        "minimum_chrome_version": "22.0.0"
    }
    manifest_path = os.path.join(ext_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f)

    background_js = f"""
var config = {{
  mode: "fixed_servers",
  rules: {{
    singleProxy: {{
      scheme: "http",
      host: "{proxy_config['host']}",
      port: parseInt({proxy_config['port']})
    }},
    bypassList: ["localhost", "127.0.0.1"]
  }}
}};
chrome.proxy.settings.set({{value: config, scope: "regular"}}, function(){{}});
function callbackFn(details) {{
  return {{
    authCredentials: {{
      username: "{proxy_config.get('username') or ''}",
      password: "{proxy_config.get('password') or ''}"
    }}
  }};
}}
chrome.webRequest.onAuthRequired.addListener(callbackFn, {{urls: ["<all_urls>"]}}, ['blocking']);
"""
    bg_path = os.path.join(ext_dir, "background.js")
    with open(bg_path, "w", encoding="utf-8") as f:
        f.write(background_js)

    zip_path = os.path.join(tempfile.gettempdir(), f"proxy_ext_{int(time.time()*1000)}.zip")
    with zipfile.ZipFile(zip_path, 'w') as z:
        z.write(manifest_path, "manifest.json")
        z.write(bg_path, "background.js")

    shutil.rmtree(ext_dir, ignore_errors=True)
    return zip_path

# ---------- Chrome driver setup ----------
def kill_existing_chrome():
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if any(x in name for x in ("chrome", "chromedriver", "chromium")):
                proc.kill()
        except Exception:
            pass

def setup_driver_with_proxy(proxy_string: Optional[str] = None, headless: bool = True) -> Tuple[webdriver.Chrome, Optional[str], Optional[str]]:
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--window-size=1200,1000")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    if headless:
        chrome_options.add_argument("--headless=new")

    ext_zip = None
    profile_dir = None

    if proxy_string:
        proxy = parse_proxy(proxy_string)
        if proxy is None:
            raise ValueError("Invalid proxy string")
        if proxy.get("username") and proxy.get("password"):
            ext_zip = create_proxy_auth_extension(proxy)
            chrome_options.add_extension(ext_zip)
        else:
            chrome_options.add_argument(f"--proxy-server=http://{proxy['host']}:{proxy['port']}")
    profile_dir = tempfile.mkdtemp(prefix="selenium_profile_")
    chrome_options.add_argument(f"--user-data-dir={profile_dir}")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception:
        pass

    return driver, ext_zip, profile_dir

def send_photo_to_telegram(photo_path, caption=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": CHAT_ID, "caption": caption or ""}
            resp = requests.post(url, data=data, files=files, timeout=60)
        return resp.status_code == 200, resp.text
    except Exception as e:
        return False, str(e)

def extract_payment_id(url: str):
    try:
        if "/payments/" in url:
            after = url.split("/payments/", 1)[1]
            pid = after.split("/")[0]
            return pid
    except Exception:
        pass
    return None

SUCCESS_KEYWORDS = [
    "payment successful",
    "your payment has been completed",
    "payment authorised",
    "payment authorized",
    "payment captured",
    "payment captured successfully",
    "razorpay_signature"
]

FAILURE_KEYWORDS = [
    "payment failed",
    "your transaction was failed",
    "payment declined",
    "transaction failed",
    "authorization failed",
    "failed to capture"
]


def check_html_for_keywords(driver):
    try:
        html_content = driver.page_source or ""
        body_text = ""
        try:
            body_el = driver.find_element("tag name", "body")
            body_text = body_el.text or ""
        except Exception:
            pass
        combined_text = (html_content + " " + body_text).lower()

        if "razorpay_signature" in combined_text:
            return "success"
        for s in SUCCESS_KEYWORDS:
            if s.lower() in combined_text:
                return "success"
        for f in FAILURE_KEYWORDS:
            if f.lower() in combined_text:
                return "failure"
        return None

    except Exception:
        return None

# ---------- Main check workflow ----------
def check_url_and_capture(input_url: str):
    proxies = load_proxies()
    proxy_string = random.choice(proxies) if proxies else None
    kill_existing_chrome()
    time.sleep(0.4)

    driver = None
    ext_zip = None
    profile_dir = None
    screenshot_path = None
    try:
        try:
            driver, ext_zip, profile_dir = setup_driver_with_proxy(proxy_string, headless=True)
        except Exception as e:
            return {"success": False, "3ds": False, "status": "DriverError", "message": f"Failed to start Chrome driver: {e}"}

        driver.set_page_load_timeout(WAIT_SECONDS + 10)
        try:
            driver.get(input_url)
        except Exception:
            pass

        start = time.time()
        initial_url = driver.current_url or input_url
        initial_pid = extract_payment_id(initial_url or input_url)
        last_url = initial_url
        while True:
            elapsed = time.time() - start
            try:
                current_url = driver.current_url or ""
            except Exception:
                current_url = last_url
            try:
                html = driver.page_source or ""
            except Exception:
                html = ""

            k = check_html_for_keywords(html)
            if k == "success":

                try:
                    screenshot_path = os.path.join(tempfile.gettempdir(), f"rz_screenshot_{int(time.time())}.png")
                    try:
                        total_width = driver.execute_script("return Math.max(document.body.scrollWidth, document.documentElement.scrollWidth, window.innerWidth);")
                        total_height = driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, window.innerHeight);")
                        max_h = 15000
                        if total_height > max_h:
                            total_height = max_h
                        driver.set_window_size(total_width, total_height)
                        time.sleep(0.4)
                    except Exception:
                        pass
                    driver.save_screenshot(screenshot_path)
                except Exception:
                    screenshot_path = None

                ok, resp_text = (False, "NoScreenshot")
                if screenshot_path:
                    ok, resp_text = send_photo_to_telegram(screenshot_path, caption=f"Payment success screenshot of {current_url or input_url}")
                    try:
                        os.remove(screenshot_path)
                    except Exception:
                        pass

                return {
                    "3ds": True,
                    "Status": "Approved",
                    "message": "Payment Captured Successfully ✅",
                }

            if k == "failure":
                try:
                    screenshot_path = os.path.join(tempfile.gettempdir(), f"rz_screenshot_{int(time.time())}.png")
                    driver.save_screenshot(screenshot_path)
                except Exception:
                    screenshot_path = None
                ok, resp_text = (False, "NoScreenshot")
                if screenshot_path:
                    ok, resp_text = send_photo_to_telegram(screenshot_path, caption=f"Payment failure screenshot of {current_url or input_url}")
                    try:
                        os.remove(screenshot_path)
                    except Exception:
                        pass

                return {
                    "3ds": False,
                    "Status": "Declined",
                    "message": "Payment Failed / Declined",
                }
            if current_url and current_url != last_url:
                in_pid = extract_payment_id(input_url)
                cur_pid = extract_payment_id(current_url)
                if in_pid and cur_pid:
                    norm_in = in_pid.replace("pay_", "")
                    norm_cur = cur_pid.replace("pay_", "")
                    if norm_in == norm_cur:
                        try:
                            screenshot_path = os.path.join(tempfile.gettempdir(), f"rz_screenshot_{int(time.time())}.png")
                            driver.save_screenshot(screenshot_path)
                        except Exception:
                            screenshot_path = None
                        ok, resp_text = (False, "NoScreenshot")
                        if screenshot_path:
                            ok, resp_text = send_photo_to_telegram(screenshot_path, caption=f"Internal redirect (no 3DS) {current_url}")
                            try:
                                os.remove(screenshot_path)
                            except Exception:
                                pass

                        return {
                            "3ds": False,
                            "status": "3DS Not Found",
                            "message": "Redirected internally",
                        }
                    else:
                        try:
                            screenshot_path = os.path.join(tempfile.gettempdir(), f"rz_screenshot_{int(time.time())}.png")
                            driver.save_screenshot(screenshot_path)
                        except Exception:
                            screenshot_path = None
                        ok, resp_text = (False, "NoScreenshot")
                        if screenshot_path:
                            ok, resp_text = send_photo_to_telegram(screenshot_path, caption=f"Redirect detected (possible 3DS) {current_url}")
                            try:
                                os.remove(screenshot_path)
                            except Exception:
                                pass

                        return {
                            "3ds": True,
                            "status": "3DS Found",
                            "message": "3DS Authentication Required ✅",
                        }
                else:
                    try:
                        screenshot_path = os.path.join(tempfile.gettempdir(), f"rz_screenshot_{int(time.time())}.png")
                        driver.save_screenshot(screenshot_path)
                    except Exception:
                        screenshot_path = None
                    ok, resp_text = (False, "NoScreenshot")
                    if screenshot_path:
                        ok, resp_text = send_photo_to_telegram(screenshot_path, caption=f"Redirect detected (no PID) {current_url}")
                        try:
                            os.remove(screenshot_path)
                        except Exception:
                            pass

                    return {
                        "3ds": True,
                        "status": "3DS Found",
                        "message": "3DS Authentication Required ✅",
                    }
            if elapsed >= WAIT_SECONDS:
                return {
                    "3ds": False,
                    "status": "3DS Not Found",
                    "message": "No redirect detected within timeout",
                }

            last_url = current_url or last_url
            time.sleep(1)

    except Exception as e:
        return {"success": False, "3ds": False, "status": "Error", "message": str(e)}
    finally:
        # cleanup
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        try:
            if ext_zip and os.path.exists(ext_zip):
                os.remove(ext_zip)
        except Exception:
            pass
        try:
            if profile_dir and os.path.exists(profile_dir):
                shutil.rmtree(profile_dir, ignore_errors=True)
        except Exception:
            pass

# ---------- Flask route ----------
@app.route("/check", methods=["GET"])
def check_route():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Missing ?url parameter"}), 400
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL format"}), 400

    result = check_url_and_capture(url)
    return jsonify(result), 200

# ---------- Graceful shutdown ----------
def handle_signal(sig, frame):
    print(f"[!] Received signal {sig}, shutting down.")
    os._exit(0)

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

# ---------- Run ----------
if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT)
