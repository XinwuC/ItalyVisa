import json
import time
import os
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

class PrenotamiBot:
    def __init__(self, config_path='config.json'):
        self.config = self._load_config(config_path)
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
        else:
            # Default to Chrome
            print("Launching Chrome...")
            self.browser = self.playwright.chromium.launch(
                headless=self.config.get('headless', False),
                channel='chrome'
            )
        self.context = self.browser.new_context(
             locale=self.config.get('language', 'en-US')
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
            # self.page.reload()
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

    def navigate_to_booking(self):
        # Ensure login before action
        self.login()
        
        print("Navigating to Services...")
        try:
            self.page.goto("https://prenotami.esteri.it/Services", timeout=60000)
            
            # Direct access: Find the booking button with specific ID
            service_id = self.config.get('service_id', '4996')
            button_selector = f"a[href='/Services/Booking/{service_id}']"
            print(f"Looking for booking button with selector: {button_selector}")
            
            self.page.wait_for_selector(button_selector, timeout=60000)
            
            buttons = self.page.locator(button_selector)
            if buttons.count() > 0:
                print("Found booking button(s).")
                # buttons.first.click() # Removed as requested
                return True
            else:
                print("Booking button not found.")
                return False
        except Exception as e:
             print(f"Error navigating to booking: {e}")
             return False

    def booking_retry_loop(self):
        """
        Clicks the booking button repeatedly until successful or user stops.
        """
        max_retries = 1000 # essentially infinite, or as configured
        retry_interval = self.config.get('retry_interval', 1)
        
        print("Starting booking retry loop...")
        
        while True:
            # Check login status periodically or before action
            try:
                self.login()
            except Exception as e:
                print(f"Login check failed inside loop: {e}")
                
            # 1. Click the button (we need to re-locate it as page might have refreshed/changed)
            # Find the active tab/booking button again
            try:
                 # Check if we moved to the next page (Booking Form)
                if "Services/Booking" in self.page.url:
                     print("Successfully moved to booking page!")
                     return True
                
                # Re-find the button directly
                service_id = self.config.get('service_id', '4996')
                button_selector = f"a[href='/Services/Booking/{service_id}']"
                
                try:
                    self.page.wait_for_selector(button_selector, timeout=5000)
                except:
                    print("Button not found (wait timeout), refreshing...")
                    self.page.reload()
                    self.page.wait_for_load_state('networkidle')
                    continue

                buttons = self.page.locator(button_selector)
                
                # Check for popup BEFORE clicking
                try:
                    popup_selector = ".jconfirm-buttons button.btn.btn-blue"
                    # Immediate check, no wait
                    popup_btn = self.page.locator(popup_selector)
                    if popup_btn.count() > 0:
                        btn = popup_btn.first
                        if btn.is_visible():
                            print("Popup detected (pre-click). Clicking 'ok'...")
                            btn.click()
                except:
                    pass

                if buttons.count() > 0:
                    print("Clicking Book button...")
                    buttons.first.click()
                else:
                    print("Button not found (count 0), refreshing...")
                    self.page.reload()
                    continue

                # Check for popup "ok" button with timeout
                try:
                    popup_selector = ".jconfirm-buttons button.btn.btn-blue"
                    # Wait up to 2 seconds for popup to appear
                    self.page.wait_for_selector(popup_selector, timeout=2000)
                    
                    popup_btn = self.page.locator(popup_selector)
                    if popup_btn.count() > 0:
                        btn = popup_btn.first
                        if btn.is_visible():
                            print("Popup detected. Clicking 'ok'...")
                            btn.click()
                except:
                    # Timeout means no popup appeared, which is fine
                    pass

                
            except Exception as e:
                print(f"Error in waiting loop: {e}")
                time.sleep(1)
                self.page.reload()

    def run(self):
        self.start()
        try:
            self.login()
            
            # Navigate to services - attempting English first
            self.switch_language('en-US')
            success = self.navigate_to_booking()
            
            if not success:
                # Fallback to Italian logic
                # User says: "Server side often switch back to IT automatically... skip switching to EN"
                # User also says: "don't need to explicit switch back to IT"
                print("English navigation seems to have failed or we are in IT default mode. Continuing...")
                # We do NOT explicitly call switch_language('it-IT') unless necessary, 
                # but if we are here because EN navigation failed, we assume we are just proceeding in whatever state (likely IT).
                
                # We retry navigation one more time (it matches broadly "switch to Italy instead" intent by just accepting the IT state)
                success = self.navigate_to_booking()

            if success:
               self.booking_retry_loop()
               # If loop returns True, we are on form page
               # self.handle_form() # To be implemented
               print("Process finished (at form stage). keeping browser open for manual entry.")
               
               # Keep alive for user
               while True:
                   time.sleep(1)
                   
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            print("Session ended.")
            # self.stop() # Don't stop automatically so user can see result
