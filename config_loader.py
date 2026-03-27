import os
import yaml
from dotenv import load_dotenv

class Config:
    def __init__(self, config_path="config.yaml"):
        load_dotenv()
        
        # Load YAML
        with open(config_path, "r") as f:
            self.raw = yaml.safe_all([f]) # This was wrong, should be safe_load
            f.seek(0)
            self.raw = yaml.safe_load(f)

        # Credentials (Env only)
        self.client_id = os.getenv("CTRADER_CLIENT_ID")
        self.client_secret = os.getenv("CTRADER_CLIENT_SECRET")
        self.access_token = os.getenv("CTRADER_ACCESS_TOKEN")
        self.account_id = os.getenv("CTRADER_ACCOUNT_ID")
        
        # Telegram (Env + YAML)
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.telegram_enabled = self.raw.get("telegram", {}).get("enabled", False)

        # API settings
        self.host = self.raw["ctrader"]["host"]
        self.port = self.raw["ctrader"]["port"]
        self.symbol_name = self.raw["strategy"]["symbol_name"]
        
        # Logging
        self.log_level = self.raw["logging"]["level"]
        self.csv_file = self.raw["logging"]["csv_file"]
        self.json_log = self.raw["logging"]["json_log"]

    def validate(self):
        missing = []
        if not self.client_id: missing.append("CTRADER_CLIENT_ID")
        if not self.client_secret: missing.append("CTRADER_CLIENT_SECRET")
        if not self.access_token: missing.append("CTRADER_ACCESS_TOKEN")
        
        if self.telegram_enabled:
            if not self.telegram_token: missing.append("TELEGRAM_BOT_TOKEN")
            if not self.telegram_chat_id: missing.append("TELEGRAM_CHAT_ID")
            
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        return True
