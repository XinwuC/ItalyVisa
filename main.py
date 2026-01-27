import argparse
from bot import PrenotamiBot

def main():
    parser = argparse.ArgumentParser(description="Prenotami Bot")
    parser.add_argument("-b", "--browser", help="Browser type (chrome, edge, firefox, safari)")
    args = parser.parse_args()

    bot = PrenotamiBot(browser_type=args.browser)
    bot.run()

if __name__ == "__main__":
    main()

