# ItalyVisa Booking Bot

A Python automation tool for booking appointments on the Prenotami website using Playwright.

## Features
- Automated Login (with manual CAPTCHA solving support)
- Auto-retry logic for busy slots
- Language switching support (English/Italian)
- Session persistence

## Setup
1. Install Python 3.9+
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
3. Configure `config.json` (see `config.example.json` if available, or create one based on walkthrough).

## Usage
```bash
python main.py
```

## Note
Do not commit `config.json` as it contains your private credentials.
