import json
import time
import os
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

class PrenotamiBot:
    def __init__(self, config_path='config.json', browser_type=None):
        self.config = self._load_config(config_path)
        if browser_type:
            self.config['browser_type'] = browser_type
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.form_memory_path = 'form_memory.json'
        self.form_data = self._load_form_memory()

    def _load_config(self, path):
        with open(path, 'r') as f:
            return json.load(f)

    def _load_form_memory(self):
        if os.path.exists(self.form_memory_path):
            try:
                with open(self.form_memory_path, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def _save_form_memory(self):
        with open(self.form_memory_path, 'w') as f:
            json.dump(self.form_data, f, indent=4)

    def start(self):
        self.playwright = sync_playwright().start()
        browser_type = self.config.get('browser_type', 'chrome').lower()
        
        if browser_type == 'safari':
            print("Launching Safari (WebKit)...")
            self.browser = self.playwright.webkit.launch(
                headless=self.config.get('headless', False)
            )
        elif browser_type == 'edge':
            print("Launching Microsoft Edge...")
            self.browser = self.playwright.chromium.launch(
                headless=self.config.get('headless', False),
                channel='msedge',
                args=['--start-maximized']
            )
        elif browser_type == 'firefox':
            print("Launching Firefox...")
            self.browser = self.playwright.firefox.launch(
                headless=self.config.get('headless', False)
            )
        else:
            # Default to Chrome
            print("Launching Chrome...")
            self.browser = self.playwright.chromium.launch(
                headless=self.config.get('headless', False),
                channel='chrome',
                args=['--start-maximized']
            )
        
        self.context = self.browser.new_context(
             locale=self.config.get('language', 'en-US'),
             no_viewport=True
        )
        self.page = self.context.new_page()
        # Add listener to prevent auto-dismissal of dialogs (alerts/confirms)
        self.page.on("dialog", lambda dialog: print(f"Dialog opened: {dialog.message}"))

    def stop(self):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def login(self):
        # 1. Check if already logged in using body class
        try:
            body_class = self.page.get_attribute("body", "class") or ""
            if "loggedin" in body_class:
                print("Already logged in (body.loggedin detected).")
                return True
        except Exception:
            pass # Continue to login flow

        max_retries = 5
        for attempt in range(max_retries):
            print(f"Login attempt {attempt + 1}/{max_retries}...")
            
            print("Navigating to login page...")
            try:
                self.page.goto("https://prenotami.esteri.it/", timeout=60000)
            except PlaywrightTimeoutError:
                print("Timeout loading login page, retrying...")
                self.page.reload()
                continue
            
            # Re-check login status after navigation (cookies might persist)
            try:
                if "loggedin" in (self.page.get_attribute("body", "class") or ""):
                     print("Already logged in.")
                     return True
            except:
                pass

            print("Filling credentials...")
            try:
                self.page.fill("#login-email", self.config['email'])
                self.page.fill("#login-password", self.config['password'])
            except Exception as e:
                print(f"Error filling form (might be on error page): {e}")
                self.page.reload()
                continue
            
            # Attempt to click login button
            print("Attempting to click Login button...")
            try:
                self.page.click("#captcha-trigger")
            except Exception as e:
                print(f"Could not auto-click login button: {e}")
            
            # 1. Success Check: Look for body.loggedin
            try:
                if "loggedin" in (self.page.get_attribute("body", "class") or ""):
                    print("Login successful (body.loggedin detected)!")
                    return True
            except:
                pass

            # If we reached here (break or timeout), we didn't return.
            # So we reload and try again.
            time.sleep(2)
            
        raise Exception("Failed to login after multiple attempts.")

    def switch_language(self, lang_code):
        """
        Switches the website language using specific href tags.
        """
        print(f"Checking language status for target: {lang_code}...")
        try:
            # Selectors based on user info
            # IT: <a class="" href="/Language/ChangeLanguage?lang=1">ITA</a>
            # EN: <a class="active" href="/Language/ChangeLanguage?lang=2">ENG</a>
            
            # Note: The selectors are precise based on href
            it_selector = "a[href*='/Language/ChangeLanguage?lang=1']"
            en_selector = "a[href*='/Language/ChangeLanguage?lang=2']"

            is_en_target = "en" in lang_code.lower()
            
            # Check current state
            en_btn = self.page.locator(en_selector).first
            it_btn = self.page.locator(it_selector).first
            
            # If buttons aren't found, we can't switch
            if en_btn.count() == 0 or it_btn.count() == 0:
                print("Language buttons not found. Skipping switch.")
                return

            en_active = "active" in (en_btn.get_attribute("class") or "")
            it_active = "active" in (it_btn.get_attribute("class") or "")

            print(f"Current State - EN Active: {en_active}, IT Active: {it_active}")

            if is_en_target:
                if en_active:
                    print("English is already active.")
                    return
                # User advised: If server switches back to IT, skip switching to EN.
                # We will try ONCE. If we are here, it means EN is not active.
                print("Switching to English...")
                en_btn.click()
                self.page.wait_for_load_state('networkidle')
            else:
                # Target is IT
                # User advised: "you don't need to explicit switch back to IT"
                if it_active:
                     print("Italian is already active.")
                     return
                
                print("Switching to Italian (Explicitly requested)...")
                it_btn.click()
                self.page.wait_for_load_state('networkidle')

        except Exception as e:
            print(f"Failed to switch language: {e}")

    def booking_retry_loop(self):
        """
        Directly navigates to the booking page and retries until successful.
        """
        service_id = self.config.get('service_id', '4996')
        url = f"https://prenotami.esteri.it/Services/Booking/{service_id}"
        
        print(f"Starting direct booking retry loop for: {url}")
        
        while True:
            try:
                # 0. Check Login
                self.login()
                
                # 1. Direct Navigate
                print(f"Navigating to {url}...")
                self.page.goto(url, wait_until="load", timeout=60000)
                
                # 2. Check Success: URL contains /Services/Booking
                # Note: If it successfully stays on Booking or redirects to Booking form, it's a win.
                if "/Services/Booking" in self.page.url:
                     print("Successfully moved to booking page!")
                     return True
                
                # 3. Check for popup (OK button)
                try:
                    popup_selector = ".jconfirm-buttons button.btn.btn-blue"
                    # Wait shortly for any potential error popup
                    self.page.wait_for_selector(popup_selector, timeout=2000)
                    
                    popup_btn = self.page.locator(popup_selector)
                    if popup_btn.count() > 0:
                        btn = popup_btn.first
                        if btn.is_visible():
                            print("Popup detected. Clicking 'ok'...")
                            btn.click()
                except:
                    pass
                
                # Small sleep before next attempt to avoid spamming too fast
                time.sleep(self.config.get('retry_interval', 1))

            except Exception as e:
                print(f"Error in booking loop: {e}")
                time.sleep(2)

    def run(self):
        self.start()
        try:
            self.login()
            
            # Directly start the retry loop after login
            self.booking_retry_loop()
            
            # Process finished - stay open for human
            print("Process finished. keeping browser open for manual entry.")
            while True:
                time.sleep(1)
                   
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            print("Session ended.")
            # self.stop() # Don't stop automatically so user can see result
