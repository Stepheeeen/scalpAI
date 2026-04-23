import logging
import json
import os
from datetime import datetime

class PerformanceTracker:
    def __init__(self, notifier, daily_profit_target=0, max_daily_loss=0, stats_file="session_stats.json", **kwargs):
        self.notifier = notifier
        self.audit_logger = kwargs.get('audit_logger')
        self.live_mode = kwargs.get('live_mode', False)
        self.daily_profit_target = daily_profit_target
        self.max_daily_loss = max_daily_loss
        self.stats_file = stats_file
        
        self.logger = logging.getLogger("PerformanceTracker")
        
        # Session Stats
        self.initial_balance = 0.0
        self.net_pnl = 0.0
        self.daily_pnl = 0.0
        self.total_commission = 0.0
        self.trades_count = 0
        self.wins = 0
        self.live_mode = False
        
        self._load_stats()

    def set_initial_balance(self, balance: float):
        if self.initial_balance == 0:
            self.initial_balance = balance
            self.logger.info(f"💰 Initial balance set: ${balance:,.2f}")

    def log_trade(self, pnl: float, commission: float = 0.0):
        """Record trade results and update metrics"""
        self.net_pnl += pnl
        self.daily_pnl += pnl
        self.total_commission += commission
        self.trades_count += 1
        
        if pnl > 0:
            self.wins += 1
            
        self.logger.info(f"📈 Trade logged: PnL=${pnl:,.2f}, Total Session PnL=${self.net_pnl:,.2f}")
        self._save_stats()
        
        # Check targets
        asyncio = __import__('asyncio')
        if self.is_daily_limit_reached():
            msg = f"🛑 <b>Daily Limit Reached</b>\nNet PnL: ${self.daily_pnl:,.2f}\nTarget: ${self.daily_profit_target}\nMax Loss: ${self.max_daily_loss}"
            asyncio.create_task(self.notifier.send_message(msg))

    def is_daily_limit_reached(self) -> bool:
        """Returns True if profit target or max loss is hit"""
        if self.daily_profit_target > 0 and self.daily_pnl >= self.daily_profit_target:
            return True
        if self.max_daily_loss > 0 and self.daily_pnl <= -self.max_daily_loss:
            return True
        return False

    @property
    def win_rate(self) -> float:
        if self.trades_count == 0:
            return 0.0
        return (self.wins / self.trades_count) * 100

    def reset(self):
        """Reset stats for a new session"""
        self.net_pnl = 0.0
        self.daily_pnl = 0.0
        self.total_commission = 0.0
        self.trades_count = 0
        self.wins = 0
        self._save_stats()

    def _save_stats(self):
        try:
            stats = {
                "initial_balance": self.initial_balance,
                "net_pnl": self.net_pnl,
                "daily_pnl": self.daily_pnl,
                "total_commission": self.total_commission,
                "trades_count": self.trades_count,
                "wins": self.wins,
                "last_update": datetime.now().isoformat()
            }
            with open(self.stats_file, 'w') as f:
                json.dump(stats, f)
        except Exception as e:
            self.logger.error(f"Failed to save stats: {e}")

    def _load_stats(self):
        if not os.path.exists(self.stats_file):
            return
            
        try:
            with open(self.stats_file, 'r') as f:
                stats = json.load(f)
                
            # Only load if it's the same day
            last_upd = datetime.fromisoformat(stats.get("last_update", "2000-01-01"))
            if last_upd.date() == datetime.now().date():
                self.initial_balance = stats.get("initial_balance", 0.0)
                self.net_pnl = stats.get("net_pnl", 0.0)
                self.daily_pnl = stats.get("daily_pnl", 0.0)
                self.total_commission = stats.get("total_commission", 0.0)
                self.trades_count = stats.get("trades_count", 0)
                self.wins = stats.get("wins", 0)
                self.logger.info("✅ Session stats restored from disk.")
            else:
                self.logger.info("📅 New day detected. Starting with fresh stats.")
        except Exception as e:
            self.logger.error(f"Failed to load stats: {e}")