import argparse
import logging
import logging.handlers
import os
from bot import PrenotamiBot

def main():
    parser = argparse.ArgumentParser(description="Prenotami Bot")
    parser.add_argument("-b", "--browser", help="Browser type (chrome, edge, firefox, safari)")
    parser.add_argument("-c", "--config", default="config.json", help="Path to config file")
    args = parser.parse_args()

    # Setup logging
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, "prenotami.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.handlers.RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5),
            logging.StreamHandler()
        ]
    )

    bot = PrenotamiBot(config_path=args.config, browser_type=args.browser)
    bot.run()

if __name__ == "__main__":
    main()

