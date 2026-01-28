import json
import time
import os
import platform
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
                self.switch_language("en")
                return True
        except Exception:
            pass # Continue to login flow

        max_retries = self.config.get('max_login_retries', 100)
        for attempt in range(max_retries):
            print(f"Login attempt {attempt + 1}/{max_retries}...")
            
            print("Navigating to login page...")
            try:
                self.page.goto(f"https://prenotami.esteri.it/Home?ReturnUrl=%2fServices%2fBooking%2f{self.config['service_id']}", timeout=60000)
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

    def is_logged_in(self):
        try:
            # Check body class or specific element
            if "loggedin" in (self.page.get_attribute("body", "class") or ""):
                return True
            return False
        except:
            return False

    def is_error_page(self):
        return "Error" in self.page.url

    def booking_retry_loop(self):
        """
        Directly navigates to the booking page and retries until successful.
        Returns code: 'SUCCESS', 'LOGOUT', 'ERROR' (though error usually means retry)
        """
        service_id = self.config.get('service_id', '4996')
        url = f"https://prenotami.esteri.it/Services/Booking/{service_id}"
        
        print(f"Starting direct booking retry loop for: {url}")
        
        while True:
            try:
                # 0. Check Login Status
                if not self.is_logged_in():
                    print("Detected logout in booking loop. Restarting flow.")
                    return 'LOGOUT'

                # 1. Direct Navigate
                print(f"Navigating to {url}...")
                if url != self.page.url:
                    self.page.goto(url, wait_until="load", timeout=60000)
                
                # Check for Error page immediately after navigation
                if self.is_error_page():
                    print("Hit Error page. Retrying...")
                    time.sleep(self.config.get('retry_interval', 1))
                    continue

                # 2. Check Success: URL contains /Services/Booking
                if "/Services/Booking" in self.page.url:
                    self.switch_language("en")
                    print("Successfully moved to booking page!")
                    return 'SUCCESS'
                
                # 3. Check for popup (OK button)
                try:
                    popup_selector = ".jconfirm-buttons button.btn.btn-blue"
                    # Wait shortly for any potential error popup
                    try:
                        self.page.wait_for_selector(popup_selector, timeout=2000)
                        popup_btn = self.page.locator(popup_selector)
                        if popup_btn.count() > 0:
                            btn = popup_btn.first
                            if btn.is_visible():
                                print("Popup detected. Clicking 'ok'...")
                                btn.click()
                    except:
                        pass
                except:
                    pass
                
                # Small sleep before next attempt
                time.sleep(self.config.get('retry_interval', 1))

            except Exception as e:
                print(f"Error in booking loop: {e}")
                time.sleep(2)

    def fill_booking_form(self):
        print("Attempting to auto-fill form...")
        try:
            print("Checking if form is ready (all dropdowns loaded)...")
            # Wait for dropdown options (confirm JS loaded)
            try:
                self.page.wait_for_function(
                    """
                    document.querySelector('#typeofbookingddl') && document.querySelector('#typeofbookingddl').options.length > 0 &&
                    document.querySelector('#ddls_0') && document.querySelector('#ddls_0').options.length > 0 &&
                    document.querySelector('#ddls_1') && document.querySelector('#ddls_1').options.length > 0
                    """, 
                    timeout=5000
                )
            except PlaywrightTimeoutError:
                print("Timeout waiting for ALL form dropdowns. Form might not be ready.")
                return False

            form_valid = True

            # 1. Select Booking Type = Individual booking (Value 1)
            self.page.select_option("#typeofbookingddl", "1")
            
            # 2. Select Passport Type = Ordinary (Value 3)
            self.page.select_option("#ddls_0", "3")
            
            # 3. Reason for Visit = Tourism (Value 42)
            self.page.select_option("#ddls_1", "42")
            print("Selected: Individual, Ordinary, Tourism")

            # 4. Residence Address
            address = self.config.get('residence_address', '')
            if address:
                self.page.fill("#DatiAddizionaliPrenotante_2___testo", address)
            else:
                print("Error: 'residence_address' missing.")
                form_valid = False
            
            # 5. File Upload
            file_path = self.config.get('residence_proof_file', '')
            if file_path and os.path.exists(file_path):
                self.page.set_input_files("#File_0", file_path)
            else:
                print(f"Error: Invalid 'residence_proof_file': {file_path}")
                form_valid = False

            # 6. Notes
            notes = self.config.get('booking_notes', '')
            if notes:
                self.page.fill("#BookingNotes", notes)

            # 7. Privacy Policy
            self.page.check("#PrivacyCheck")

            # 8. Forward
            if form_valid:
                print("All required fields filled. Clicking Forward...")
                self.page.click("#btnAvanti")
                self.page.wait_for_load_state('networkidle')
                return True
            else:
                print("Validation failed. Not clicking Forward.")
                return False

        except Exception as e:
            print(f"Error auto-filling form: {e}")
            return False

    def run(self):
        self.start()
        service_id = self.config.get('service_id', '4996')
        booking_url = f"https://prenotami.esteri.it/Services/Booking/{service_id}"
        
        while True:
            try:
                # 1. Check Login
                if not self.is_logged_in():
                    print("Status: Not logged in. Action: Login")
                    self.login()
                    time.sleep(2)
                    continue

                # 2. Check Language
                self.switch_language("en")

                current_url = self.page.url

                # 3. Check URL Actions
                if "/BookingCalendar" in current_url:
                    print(f"Status: Booking Calendar reached ({current_url}). Action: Handover")
                    self.play_alert_sound()
                    break

                elif "/Services/Booking" in current_url:
                    print(f"Status: Booking Form ({current_url}). Action: Fill & Submit")
                    if self.fill_booking_form():
                        # If submission apparently successful, check URL next loop
                        pass
                
                else:
                    # All else -> Go to Booking Page
                    print(f"Status: Other URL ({current_url}). Action: Go to Booking Page")
                    if current_url != booking_url:
                        self.page.goto(booking_url)
                        self.page.wait_for_load_state('networkidle')
                
                time.sleep(self.config.get('retry_interval', 1))

            except Exception as e:
                print(f"Critical error in main loop: {e}")
                time.sleep(5)
            
        print("Process finished. Keeping browser open.")
        while True:
            time.sleep(1)

    def play_alert_sound(self):
        """
        Plays a system alert sound for configured duration (default 10 mins).
        Supports macOS (afplay/say) and Windows (winsound). Fallback to generic beep.
        """
        try:
            duration_mins = self.config.get('alert_duration_minutes', 10)
            end_time = time.time() + (duration_mins * 60)
            print(f"Playing ALARM sound for {duration_mins} minutes...")
            
            system_name = platform.system()

            if system_name == 'Darwin':
                # Play a system sound on macOS
                while time.time() < end_time:
                    # Glass sound + Voice
                    os.system('afplay /System/Library/Sounds/Glass.aiff')
                    os.system('say "Booking ready! Check now!"')
                    time.sleep(1) 
            elif system_name == 'Windows':
                # Windows
                import winsound
                while time.time() < end_time:
                    # Siren-like effect
                    winsound.Beep(1000, 400)
                    winsound.Beep(2500, 400)
            else:
                # Fallback for other OS
                while time.time() < end_time:
                    print('\a') # Beep
                    time.sleep(1)
        except Exception as e:
            print(f"Sound error: {e}")
            print('\a') # Fallback beep
            # self.stop() # Don't stop automatically so user can see result
