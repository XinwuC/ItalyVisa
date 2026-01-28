import json
import time
import os
import sys
import platform
import logging
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

class PrenotamiBot:
    def __init__(self, config_path='config.json', browser_type=None):
        self.config = self._load_config(config_path)
        if browser_type:
            self.config['browser_type'] = browser_type
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # Sanity check for residence_proof_file
        if 'residence_proof_file' in self.config and self.config['residence_proof_file']:
            if not os.path.exists(self.config['residence_proof_file']):
                raise FileNotFoundError(f"Residence proof file not found at: {self.config['residence_proof_file']}")

    def _load_config(self, path):
        with open(path, 'r') as f:
            return json.load(f)

    def start(self):
        self.playwright = sync_playwright().start()
        browser_type_str = self.config.get('browser_type', 'chrome').lower()
        disable_extensions = self.config.get('disable_extensions', False)
        headless = self.config.get('headless', False)
        
        launch_args = [
            '--start-maximized',
            '--disable-features=Translate',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
        ]
        if disable_extensions:
            launch_args.append('--disable-extensions')
        
        # LOGIC BRANCH 1: Safari / Firefox (Standard Launch, No Persistent Profile)
        if browser_type_str in ['safari', 'firefox']:
            if browser_type_str == 'safari':
                logging.info("Launching Safari (WebKit)...")
                browser_engine = self.playwright.webkit
            else:
                logging.info("Launching Firefox...")
                browser_engine = self.playwright.firefox

            logging.warning(f"Using standard launch for {browser_type_str} (No persistent profile).")
            self.browser = browser_engine.launch(headless=headless, args=launch_args)
            self.context = self.browser.new_context(no_viewport=True)
            self.page = self.context.new_page()

        # LOGIC BRANCH 2: Chrome / Edge (Persistent Profile)
        else:
            # Chrome/Edge
            logging.info(f"Launching {browser_type_str} (Chromium)...")
            browser_engine = self.playwright.chromium
            
            # Enforce local dedicated profile for stability
            config_profile_path = self.config.get('chrome_profile_path')
            if config_profile_path:
                chrome_profile_path = os.path.abspath(os.path.expanduser(config_profile_path))
            else:
                chrome_profile_path = os.path.join(os.getcwd(), "chrome_bot_profile")
            
            logging.info(f"Using Dedicated Bot Profile: {chrome_profile_path}")
            
            if not os.path.exists(chrome_profile_path):
                 logging.info("Profile not found. Creating new profile... (You will need to login once)")
            
            try:
                # Persistent context launches the browser AND context together
                logging.info("Attempting to launch persistent context...")

                self.context = browser_engine.launch_persistent_context(
                    user_data_dir=chrome_profile_path,
                    headless=headless,
                    args=launch_args,
                    ignore_default_args=['--no-sandbox', '--enable-automation'],
                    channel='chrome' if browser_type_str == 'chrome' else 'msedge',
                    no_viewport=True, # Important to match window size
                    timeout=60000 
                )
                logging.info("Browser launched successfully.")
            except Exception as e:
                msg = str(e)
                if "SingletonLock" in msg or "ProcessSingleton" in msg or "File exists" in msg:
                    logging.error("❌ CHROME INVALID STATE: It appears Chrome is already running.")
                    logging.error("👉 ACTION REQUIRED: Ensure no stale chrome processes are running.")
                    sys.exit(1)
                raise e

            self.browser = None # Managed by context
            
            if self.context.pages:
                self.page = self.context.pages[0]
                logging.info("Attached to existing first page.")
            else:
                self.page = self.context.new_page()
                logging.info("Created new page.")

            # Force bring to front/check
            try:
                url = self.page.url
                logging.info(f"Current page URL: {url}")
            except Exception as e:
                logging.error(f"Failed to check page URL: {e}")
        
        # Common setup
        # Inject script to hide webdriver property (stealth mode)
        if self.context:
            self.context.add_init_script("""
                // Common stealth: Pass generic webdriver checks
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                
                // Pass chrome-specific checks
                if (!window.chrome) {
                    window.chrome = {
                        runtime: {}
                    };
                }
                
                // Mask permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: 'denied', onchange: null }) :
                        originalQuery(parameters)
                );
                
                // Mock plugins to look like real Chrome
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Mock languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
            """)

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
        """
        Attempts to log in once. Returns True if successful or already logged in, False otherwise.
        """
        if self.is_logged_in():
             logging.info("Already logged in.")
             return True

        # login_url = f"https://prenotami.esteri.it/Home?ReturnUrl=%2fServices%2fBooking%2f{service_id}"
        login_url = f"https://prenotami.esteri.it/"

        logging.info(f"Loggin in...")
        # Navigate
        self.page.goto(login_url, timeout=60000)
        
        if self.is_captcha_page():
            logging.warning("Captcha/WAF detected after login page navigation.")
            return False
        
        # Check if session persisted
        if self.is_logged_in():
            logging.info("Already logged in after navigation.")
            return True

        # Fill & Submit
        logging.info("Filling credentials...")
        self.page.fill("#login-email", self.config['email'])
        self.page.fill("#login-password", self.config['password'])
        self.page.click("#captcha-trigger")
        
        # Wait for navigation/reload
        self.page.wait_for_load_state('networkidle', timeout=10000)
       
        # Verify
        if self.is_logged_in():
            logging.info("Login successful!")
            return True

        return False

    def switch_language(self, lang_code):
        """
        Switches the website language using specific href tags.
        """
        it_selector = "a[href*='/Language/ChangeLanguage?lang=1']"
        en_selector = "a[href*='/Language/ChangeLanguage?lang=2']"

        is_en_target = "en" in lang_code.lower()
        
        # Check current state
        en_btn = self.page.locator(en_selector).first
        it_btn = self.page.locator(it_selector).first
        
        # If buttons aren't found, we can't switch
        if en_btn.count() == 0 or it_btn.count() == 0:
            return

        en_active = "active" in (en_btn.get_attribute("class") or "")
        it_active = "active" in (it_btn.get_attribute("class") or "")

        if is_en_target:
            if en_active:
                logging.info("English is already active.")
                return
            logging.info("Switching to English...")
            en_btn.click()
            self.page.wait_for_load_state('networkidle')
        else:
            if it_active:
                logging.info("Italian is already active.")
                return
            logging.info("Switching to Italian (Explicitly requested)...")
            it_btn.click()
            self.page.wait_for_load_state('networkidle')

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

    def is_captcha_page(self):
        """
        Checks if the current URL suggests a Captcha/WAF block.
        """
        href = self.page.evaluate("window.location.href")
        if "perfdrive.com" in href.lower():
            logging.warning(f"Captcha URL: {href}")
            return True
        return False

    def fill_booking_form(self):
        logging.info("Attempting to auto-fill form...")
        
        logging.info("Checking if form is ready (all dropdowns loaded)...")
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
            logging.warning("Timeout waiting for ALL form dropdowns. Form might not be ready.")
            try:
                # Debug: Screenshot and dump content
                timestamp = int(time.time())
                screenshot_path = f"debug_timeout_{timestamp}.png"
                self.page.screenshot(path=screenshot_path)
                logging.info(f"Saved debug screenshot to {screenshot_path}")
                logging.info(f"Page Title: {self.page.title()}")
                logging.info(f"Page Content Snippet: {self.page.content()[:500]}")
            except Exception as e:
                logging.error(f"Failed to save debug info: {e}")
            return False

        form_valid = True

        # 1. Select Booking Type = Individual booking (Value 1)
        self.page.select_option("#typeofbookingddl", "1")
        
        # 2. Select Passport Type = Ordinary (Value 3)
        self.page.select_option("#ddls_0", "3")
        
        # 3. Reason for Visit = Tourism (Value 42)
        self.page.select_option("#ddls_1", "42")
        logging.info("Selected: Individual, Ordinary, Tourism")

        # 4. Residence Address
        address = self.config.get('residence_address', '')
        if address:
            self.page.fill("#DatiAddizionaliPrenotante_2___testo", address)
        else:
            logging.error("Error: 'residence_address' missing.")
            form_valid = False
        
        # 5. File Upload
        file_path = self.config.get('residence_proof_file', '')
        if file_path and os.path.exists(file_path):
            self.page.set_input_files("#File_0", file_path)
        else:
            logging.error(f"Error: Invalid 'residence_proof_file': {file_path}")
            form_valid = False

        # 6. Notes
        notes = self.config.get('booking_notes', '')
        if notes:
            self.page.fill("#BookingNotes", notes)

        # 7. Privacy Policy
        self.page.check("#PrivacyCheck")

        # 8. Forward
        if form_valid:
            logging.info("All required fields filled. Clicking Forward...")
            self.page.click("#btnAvanti")
            self.page.wait_for_load_state('networkidle')
            return True
        else:
            logging.warning("Validation failed. Not clicking Forward.")
            return False

    def run(self):
        self.start()
        service_id = self.config.get('service_id', '4996')
        retry_interval = self.config.get('retry_interval', 5)
        booking_url = f"https://prenotami.esteri.it/Services/Booking/{service_id}"
        
        while True:
            try:
                # 1. Check URL Actions
                while self.is_captcha_page():
                    logging.warning(f"Captcha detected. Playing alert and waiting for {retry_interval}s...")
                    self.play_alert_sound(duration_seconds=retry_interval)

                current_url = self.page.evaluate("window.location.href")
                if "/BookingCalendar" in current_url:
                    logging.info(f"Status: Booking Calendar reached ({current_url}). Action: Handover")
                    self.play_alert_sound()
                    break 

                elif "/Services/Booking" in current_url:
                    logging.info(f"Status: Booking Form ({current_url}). Action: Fill & Submit")
                    if self.fill_booking_form():
                        # If submission apparently successful, check URL next loop
                        pass
                
                elif self.login():
                    self.switch_language("en")
                    # All else -> Go to Booking Page
                    logging.info(f"Status: Other URL ({current_url}). Action: Go to Booking Page")
                    if current_url != booking_url:
                        self.page.goto(booking_url)                            
                        self.page.wait_for_load_state('networkidle', timeout=10000)
                else:
                    logging.warning(f"login failed, retry in {retry_interval}s")
                    time.sleep(self.config.get('retry_interval', 1))    
            except PlaywrightError as e:
                # Check for "Target page, context or browser has been closed"
                if "Target page, context or browser has been closed" in str(e):
                    logging.warning("Browser was closed by user. Exiting...")
                    sys.exit(0)
                logging.error(f"Playwright error in main loop: {e}")
                time.sleep(self.config.get('retry_interval', 1))    
            except Exception as e:
                logging.critical(f"Critical error in main loop: {e}")
                time.sleep(self.config.get('retry_interval', 1))    
            
        logging.info("Process finished. Keeping browser open.")
        while True:
            time.sleep(1)

    def play_alert_sound(self, duration_seconds=None):
        """
        Plays system alert sound for a specified duration.
        """
        try:
            if duration_seconds is None:
                duration_seconds = self.config.get('alert_duration_minutes', 10) * 60
            
            end_time = time.time() + duration_seconds
            system_name = platform.system()

            while time.time() < end_time:
                if system_name == 'Darwin':
                    os.system('afplay /System/Library/Sounds/Glass.aiff')
                    os.system('say "Booking ready! Check now!"')
                elif system_name == 'Windows':
                    import winsound
                    winsound.Beep(1000, 400)
                    winsound.Beep(2500, 400)
                else:
                    logging.warning('Sound beep') 
                
                time.sleep(0.5)
        except Exception as e:
            logging.error(f"Sound error: {e}")
