from bot import PrenotamiBot
import os
import json

def test_sound():
    print("--- Starting Sound Alert Test ---")
    
    # Ensure a config file exists or create a temporary one
    config_path = 'config.json'
    if not os.path.exists(config_path):
        print("config.json not found, creating dummy for test...")
        with open('dummy_config.json', 'w') as f:
            json.dump({}, f)
        config_path = 'dummy_config.json'

    # Instantiate bot
    try:
        bot = PrenotamiBot(config_path)
    except Exception as e:
        print(f"Failed to instantiate bot: {e}")
        return

    # Override config for testing purposes
    # Set duration to 0.1 minutes (6 seconds)
    bot.config['alert_duration_minutes'] = 0.1 
    
    print(f"Configured test duration: {bot.config['alert_duration_minutes']} minutes (approx 6 seconds)")
    print("You should hear the alert sound now...")
    
    bot.play_alert_sound()
    
    print("--- Test Complete ---")
    
    # Cleanup dummy if created
    if config_path == 'dummy_config.json':
        os.remove('dummy_config.json')

if __name__ == "__main__":
    test_sound()
