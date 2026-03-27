import asyncio
import logging
import time
import signal
from config_loader import Config
from connection import CTraderClient
from logger import TickLogger
from notifier import TelegramNotifier
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
        
        self.symbol_id = None
        self.account_id = None
        self.running = True

    async def on_spot_event(self, proto_msg):
        event = oa.ProtoOASpotEvent()
        event.ParseFromString(proto_msg.payload)
        
        bid = event.bid / 100000.0 if event.bid else 0.0
        ask = event.ask / 100000.0 if event.ask else 0.0
        server_time = event.timestamp if event.timestamp else 0
        
        if bid and ask:
            latency = self.tick_logger.log_tick(bid, ask, server_time)
            # Only print every 10 ticks or so to avoid console spam in HFT
            # or use a throttle
            if latency > 100: # Alert on high latency
                logger.warning(f"High Latency detected: {latency}ms")

    async def setup_session(self):
        # 1. Auth Application
        await self.client.authenticate_application()
        
        # 2. Discover/Auth Account
        if self.config.account_id:
            self.account_id = int(self.config.account_id)
        else:
            acc_list = await self.client.get_account_list()
            self.account_id = acc_list.ctidTraderAccount[0].ctidTraderAccountId
            logger.info(f"Discovered Account: {self.account_id}")

        await self.client.authenticate_account(self.account_id)
        
        # 3. Discover Symbol
        if not self.symbol_id:
            logger.info(f"Discovering Symbol ID for {self.config.symbol_name}...")
            symbols_res = await self.client.get_symbols_list(self.account_id)
            for s in symbols_res.symbol:
                if s.symbolName == self.config.symbol_name:
                    self.symbol_id = s.symbolId
                    break
        
        if not self.symbol_id:
            raise ValueError(f"Symbol {self.config.symbol_name} not found")

        # 4. Subscribe
        req = oa.ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(self.symbol_id)
        req.subscribeToSpotTimestamp = True
        
        self.client.add_callback(oa.PROTO_OA_SPOT_EVENT, self.on_spot_event)
        await self.client.send(req)
        logger.info(f"Subscribed to {self.config.symbol_name} (ID: {self.symbol_id})")

    async def run(self):
        backoff = 1
        max_backoff = 60
        
        await self.notifier.send_message("🤖 Bot Starting...")
        
        while self.running:
            try:
                if await self.client.connect():
                    await self.setup_session()
                    await self.notifier.send_message("✅ Connected and Subscribed")
                    backoff = 1 # Reset backoff on success
                    
                    # Watch the connection
                    while self.client.is_connected and self.running:
                        await asyncio.sleep(1)
                else:
                    raise ConnectionError("Failed to establish websocket connection")

            except Exception as e:
                logger.error(f"Bot Loop Error: {e}")
                if self.running:
                    await self.notifier.notify_error(f"Connection Lost: {e}")
                    logger.info(f"Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
            finally:
                await self.client.disconnect()

    def stop(self):
        self.running = False
        logger.info("Stopping bot...")

async def main():
    bot = HFTBot()
    
    # Handle signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, bot.stop)

    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
