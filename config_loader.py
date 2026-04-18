import os
import yaml
from dotenv import load_dotenv

class Config:
    def __init__(self, config_path="config.yaml"):
        load_dotenv()
        
        # Load YAML
        with open(config_path, "r") as f:
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
        strategy = self.raw.get("strategy", {})
        self.symbol_name = strategy.get("symbol_name", "XAUUSD")
        self.target_confidence = strategy.get("target_confidence", 0.82)
        self.dry_run = strategy.get("dry_run", True)
        
        # Risk Management
        risk = self.raw.get("risk", {})
        self.risk_stop_loss_pips = risk.get("stop_loss_pips", 15)
        self.risk_take_profit_pips = risk.get("take_profit_pips", 25)
        self.risk_auto_break_even_pips = risk.get("auto_break_even_pips", 5)

        # Logging
        logging_cfg = self.raw.get("logging", {})
        self.log_level = logging_cfg.get("level", "INFO")
        self.csv_file = logging_cfg.get("csv_file", "live_gold_data.csv")
        self.json_log = logging_cfg.get("json_log", "bot_audit.log")

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
