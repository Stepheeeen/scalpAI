import asyncio
import logging
import time
import signal
from config_loader import Config
from connection import CTraderClient
from logger import TickLogger
from notifier import TelegramNotifier
from features import FeatureFactory
from brain import XGBoostGatekeeper
from executioner import OrderManager
from openapi_pb2 import OpenApiMessages_pb2 as oa

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Main")

class HFTBot:
    def __init__(self):
        self.config = Config()
        self.config.validate()
        
        # Core Components
        self.client = CTraderClient(
            self.config.host, 
            self.config.port, 
            self.config.client_id, 
            self.config.client_secret, 
            self.config.access_token
        )
        self.tick_logger = TickLogger(self.config.csv_file)
        self.notifier = TelegramNotifier(
            self.config.telegram_token, 
            self.config.telegram_chat_id, 
            self.config.telegram_enabled
        )
        
        # HFT Logic Components
        self.feature_factory = FeatureFactory(window_ms=1000)
        self.brain = XGBoostGatekeeper()
        self.executioner = None # Init after account_id is known
        
        self.symbol_id = None
        self.account_id = None
        self.running = True

    async def on_spot_event(self, proto_msg):
        event = oa.ProtoOASpotEvent()
        event.ParseFromString(proto_msg.payload)
        
        bid = event.bid / 100000.0 if event.bid else 0.0
        ask = event.ask / 100000.0 if event.ask else 0.0
        server_time = event.timestamp if event.timestamp else int(time.time() * 1000)
        
        if not bid or not ask:
            return

        # 1. Log Raw Tick
        latency = self.tick_logger.log_tick(bid, ask, server_time)
        
        # 2. Add to Feature Factory
        self.feature_factory.add_tick(bid, ask, server_time)
        
        # 3. Get Features and AI Confidence
        features = self.feature_factory.get_features()
        if not features:
            return

        confidence = self.brain.get_confidence(features)
        
        # 4. Check for Trade Execution
        # Condition: High Confidence + No existing position (simple logic for now)
        if confidence > 0.82 and not self.executioner.positions:
            # Determine Side based on Velocity (Step 2)
            side = "BUY" if features["velocity_100ms"] > 0 else "SELL"
            
            logger.info(f"🚀 AI Signal: {side} with {confidence*100:.1f}% confidence feat: {features}")
            try:
                # 100 units = 1.0 lot in Gold? No, usually 1 lot = 100 ounces.
                # In cTrader, volume 1000 = 10 units? 
                # Let's use a small volume for safety: 100 = 1.0 unit.
                await self.client.place_market_order(
                    self.account_id, 
                    self.symbol_id, 
                    side, 
                    volume=100, # 1.0 units (mini)
                    sl_pips=15, 
                    tp_pips=25
                )
            except Exception as e:
                logger.error(f"Execution Error: {e}")

        # 5. Manage Existing Trades (Break-Even)
        if self.executioner.positions:
            await self.executioner.check_break_even(self.symbol_id, bid, ask)

        # 6. Periodic Healthy Log
        if latency > 100:
             logger.warning(f"High Latency: {latency}ms")

    async def setup_session(self):
        await self.client.authenticate_application()
        
        if self.config.account_id:
            self.account_id = int(self.config.account_id)
        else:
            acc_list = await self.client.get_account_list()
            self.account_id = acc_list.ctidTraderAccount[0].ctidTraderAccountId
            logger.info(f"Discovered Account: {self.account_id}")

        await self.client.authenticate_account(self.account_id)
        
        # Initialize Executioner once account is known
        self.executioner = OrderManager(self.client, self.notifier, self.account_id)
        self.client.add_callback(oa.PROTO_OA_EXECUTION_EVENT, self.executioner.handle_execution_event)

        if not self.symbol_id:
            logger.info(f"Discovering Symbol ID for {self.config.symbol_name}...")
            symbols_res = await self.client.get_symbols_list(self.account_id)
            for s in symbols_res.symbol:
                if s.symbolName == self.config.symbol_name:
                    self.symbol_id = s.symbolId
                    break
        
        if not self.symbol_id:
            raise ValueError(f"Symbol {self.config.symbol_name} not found")

        # Subscribe to spots
        self.client.add_callback(oa.PROTO_OA_SPOT_EVENT, self.on_spot_event)
        req = oa.ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(self.symbol_id)
        req.subscribeToSpotTimestamp = True
        await self.client.send(req)
        
        logger.info(f"Bot Fully Synchronized on {self.config.symbol_name} (ID: {self.symbol_id})")

    async def run(self):
        backoff = 1
        max_backoff = 60
        
        await self.notifier.send_message("🤖 <b>Bot Online</b> (Full Logic Enabled)")
        
        while self.running:
            try:
                if await self.client.connect():
                    await self.setup_session()
                    backoff = 1 
                    while self.client.is_connected and self.running:
                        await asyncio.sleep(1)
                else:
                    raise ConnectionError("WebSocket connection failed")

            except Exception as e:
                logger.error(f"Bot Loop Error: {e}")
                if self.running:
                    await self.notifier.notify_error(f"System Error: {e}")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
            finally:
                await self.client.disconnect()

    def stop(self):
        self.running = False
        logger.info("Stopping bot...")

async def main():
    bot = HFTBot()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, bot.stop)
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
