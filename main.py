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
from performance import PerformanceTracker
from openapi_pb2 import OpenApiMessages_pb2 as oa
from openapi_pb2 import OpenApiModelMessages_pb2 as model

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
        # Debug: Log tokens being used
        logger.info(f"[DEBUG] Using CTRADER_ACCESS_TOKEN: {self.config.access_token}")
        logger.info(f"[DEBUG] Using CTRADER_REFRESH_TOKEN: {self.config.refresh_token}")
        # Core Components
        self.client = CTraderClient(
            self.config.host, 
            self.config.port, 
            self.config.client_id, 
            def __init__(self):
                import os
                self.config = Config()
                self.config.validate()
                logger.info("[DEBUG] HFTBot instance created. PID: %s", os.getpid())
                logger.info(f"[DEBUG] Telegram Bot Token: {self.config.telegram_token}")
                logger.info(f"[DEBUG] Telegram Chat ID: {self.config.telegram_chat_id}")
                logger.info(f"[DEBUG] Using CTRADER_ACCESS_TOKEN: {self.config.access_token}")
                logger.info(f"[DEBUG] Using CTRADER_REFRESH_TOKEN: {self.config.refresh_token}")
                # Core Components
                self.client = CTraderClient(
                    self.config.host, 
                    self.config.port, 
                    self.config.client_id, 
                    self.config.client_secret, 
                    self.config.access_token,
                    self.config.refresh_token
                )
                self.client.on_token_refreshed = self.save_new_tokens
                self.tick_logger = TickLogger(self.config.csv_file)
                self.notifier = TelegramNotifier(
                    self.config.telegram_token, 
                    self.config.telegram_chat_id, 
                    self.config.telegram_enabled
                )
                self.notifier.ctrader_token = self.config.access_token
                # HFT Logic Components
                self.feature_factory = FeatureFactory(window_ms=1000)
                self.brain = XGBoostGatekeeper(self.config.model_path, self.config.allow_mock_model)
                self.performance = PerformanceTracker(
                    notifier=self.notifier,
                    audit_logger=self.tick_logger,
                    live_mode=not self.config.dry_run,
                    target_confidence=self.config.target_confidence,
                )
                # Set performance tracker for KPI access via Telegram
                self.notifier.set_performance_tracker(self.performance)
                self.notifier.stop_callback = self.stop
                self.notifier.restart_callback = self.restart
                self.notifier.mode_switch_callback = self.switch_mode
                self.executioner = None # Init after account_id is known
                self.can_trade = False
                self.trade_permission_notice_sent = False
                self.symbol_id = None
                self.account_id = None
                self.running = True
                self.heartbeat_task = None

                log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
                logging.getLogger().setLevel(log_level)
                if self.notifier.enabled:
                    handler = self.notifier.get_log_handler()
                    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
                    logging.getLogger().addHandler(handler)
                    logger.info("Telegram logging enabled for all bot activity.")
                    self.notifier.set_account_switch_callback(self.switch_account)
                    self.notifier.set_mode_switch_callback(self.switch_mode)
                    self.notifier.set_stop_callback(self.stop)
                    self.notifier.set_restart_callback(self.restart)
                    # Start Telegram command polling
                    asyncio.create_task(self.notifier.start_polling())
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

            signal_type, confidence = self.brain.get_signal(features)
            accepted_signal = signal_type != 0 and confidence >= self.config.target_confidence and not self.executioner.positions
            self.performance.record_signal(signal_type, confidence, features, accepted_signal)

            if signal_type == 0 or confidence < self.config.target_confidence:
                logger.debug(f"Signal rejected: type={signal_type} confidence={confidence:.3f}")
                return

            if self.executioner.positions:
                logger.debug("Signal ignored: position already open")
                return

            side = "BUY" if signal_type == 1 else "SELL"
            logger.info(f"🎯 Signal: {side} @ {confidence*100:.1f}%")

            if self.config.dry_run:
                logger.debug(f"Dry run: skipping {side} order")
                await self.notifier.send_message(
                    f"🧪 <b>Dry Run Signal</b> — {side} @ {confidence*100:.1f}%"
                )
                self.performance.record_trade_attempt(side, 0, self.symbol_id, "dry_run")
                return

            if not self.can_trade:
                logger.warning("Trade permission missing or disabled; skipping order placement.")
                if not self.trade_permission_notice_sent:
                    self.trade_permission_notice_sent = True
                    await self.notifier.send_message(
                        "⚠️ <b>Trade Permission Missing</b>\n"
                        "Your API token currently has VIEW-only access and cannot place orders. "
                        "Please enable TRADE permission for the account and restart the bot."
                    )
                return

            self.performance.record_trade_attempt(side, 100, self.symbol_id, "placed")
            try:
                await self.client.place_market_order(
                    self.account_id,
                    self.symbol_id,
                    side,
                    volume=100,
                    sl_pips=self.config.risk_stop_loss_pips,
                    tp_pips=self.config.risk_take_profit_pips
                )
                await self.notifier.send_message(f"🚀 <b>Order Placed</b> — {side} order executed")
            except Exception as e:
                logger.error(f"❌ Execution Error: {e}")
                await self.notifier.notify_error(f"Order Execution Failed: {e}")

            # 5. Manage Existing Trades (Break-Even)
            if self.executioner.positions:
                await self.executioner.check_break_even(self.symbol_id, bid, ask)

            # 6. Periodic Healthy Log
            if latency > 100:
                 logger.warning(f"High Latency: {latency}ms")
        except Exception as e:
            logger.error(f"❌ Error processing spot event: {e}")
            await self.notifier.notify_error(f"Spot Event Processing Error: {e}")

    async def _heartbeat_loop(self):
        """Asynchronous heartbeat loop to update the dashboard instead of spamming messages"""
        self.notifier.bot_state = "🟢 Trading"
        while self.running:
            try:
                # Update dashboard every 1 minute for near real-time state
                await asyncio.sleep(60) 
                
                # Check connection status to update state
                if not self.client.is_connected:
                    self.notifier.bot_state = "⏳ Reconnecting..."
                else:
                    self.notifier.bot_state = "🟢 Trading"
                
                # Update account status in notifier for rendering
                if self.account_id:
                    self.notifier.current_account_id = self.account_id
                    
                    try:
                        trader_resp = await self.client.get_trader_info(self.account_id)
                        trader = trader_resp.trader
                        money_digits = trader.moneyDigits if hasattr(trader, 'moneyDigits') else 0
                        balance = trader.balance / (10 ** money_digits)
                        self.notifier.current_account_balance = balance
                        self.notifier.current_account_type = "LIVE" if trader.live else "DEMO"
                    except:
                        pass # Ignore temporary poll errors
                
                await self.notifier.update_dashboard()
            except Exception as e:
                logger.error(f"Pulse Error: {e}")
                await asyncio.sleep(10)

    async def save_new_tokens(self, access_token, refresh_token):
        """Update .env with new tokens from cTrader refresh"""
        try:
            env_path = ".env"
            if not os.path.exists(env_path):
                return
                
            new_lines = []
            with open(env_path, 'r') as f:
                for line in f:
                    if line.startswith("CTRADER_ACCESS_TOKEN="):
                        new_lines.append(f"CTRADER_ACCESS_TOKEN={access_token}\n")
                    elif line.startswith("CTRADER_REFRESH_TOKEN="):
                        new_lines.append(f"CTRADER_REFRESH_TOKEN={refresh_token}\n")
                    else:
                        new_lines.append(line)
            
            # If refresh_token wasn't in the file, append it
            if not any(l.startswith("CTRADER_REFRESH_TOKEN=") for l in new_lines):
                 new_lines.append(f"CTRADER_REFRESH_TOKEN={refresh_token}\n")

            with open(env_path, 'w') as f:
                f.writelines(new_lines)
            
            self.notifier.ctrader_token = access_token
            logger.info("✅ Tokens updated in .env file.")
        except Exception as e:
            logger.error(f"Failed to save new tokens: {e}")

    async def setup_session(self):
        await self.client.authenticate_application()
        # Force token refresh before fetching account list
        try:
            await self.client.refresh_token_call()
            logger.info("[DEBUG] Forced token refresh before get_account_list.")
        except Exception as e:
            logger.error(f"[DEBUG] Forced token refresh failed: {e}")
        acc_list = await self.client.get_account_list()
        
        # 1. Dashboard: List all available accounts
        logger.info("="*60)
        logger.info(f"📋 DISCOVERED ACCOUNTS (Env: {self.config.bot_env})")
        logger.info("-" * 60)
        logger.info(f"{'ID':<12} | {'TYPE':<6} | {'BROKER':<15} | {'BALANCE':<12}")
        logger.info("-" * 60)
        
        authorized_accounts = []
        target_account = None
        
        for acc in acc_list.ctidTraderAccount:
            try:
                t_resp = await self.client.get_trader_info(acc.ctidTraderAccountId)
                t = t_resp.trader
                m_digits = t.moneyDigits if hasattr(t, 'moneyDigits') else 0
                bal = t.balance / (10 ** m_digits)
                acc_type = "LIVE" if acc.isLive else "DEMO"
                broker = t.brokerName if hasattr(t, 'brokerName') else 'Unknown'
                
                logger.info(f"{acc.ctidTraderAccountId:<12} | {acc_type:<6} | {broker[:15]:<15} | ${bal:,.2f}")
                authorized_accounts.append({
                    "id": acc.ctidTraderAccountId,
                    "type": acc_type,
                    "account": acc,
                    "trader": t
                })
                
                # Auto-select logic
                if self.config.account_id and int(self.config.account_id) == acc.ctidTraderAccountId:
                    target_account = acc
            except Exception as e:
                if "not authorized" in str(e).lower():
                    logger.warning(f"🔒 Account {acc.ctidTraderAccountId} found but NOT AUTHORIZED. Check cTrader dashboard.")
                else:
                    logger.debug(f"Could not fetch info for acc {acc.ctidTraderAccountId}: {e}")

        logger.info("="*60)

        # 2. Final Selection Strategy
        final_acc = None
        if target_account:
            final_acc = target_account
            self.account_id = final_acc.ctidTraderAccountId
        elif not authorized_accounts:
            # DORMANT MODE: Wait for user to authorize an account
            logger.error("❌ NO AUTHORIZED ACCOUNTS FOUND. Entering Dormant Mode...")
            self.notifier.is_authorized = False
            self.notifier.bot_state = "🛑 Account Locked"
            await self.notifier.update_dashboard()
            
            while self.running and not authorized_accounts and self.client.is_connected:
                await asyncio.sleep(30) # Poll every 30s
                # Re-check account list effectively
                try:
                    acc_list = await self.client.get_account_list()
                    for acc in acc_list.ctidTraderAccount:
                        try:
                            await self.client.get_trader_info(acc.ctidTraderAccountId)
                            # If we get here, it's authorized!
                            logger.info(f"✅ Authorization detected for {acc.ctidTraderAccountId}. Resuming...")
                            # Trigger a restart of the session setup
                            return await self.setup_session() 
                        except:
                            continue
                except:
                    pass
            return
            
        else:
            # Selection priority: matching env, then any authorized
            env_matches = [a for a in authorized_accounts if a["type"] == self.config.bot_env]
            if env_matches:
                final_acc = env_matches[0]["account"]
                logger.info(f"✅ Auto-selected {self.config.bot_env} account: {final_acc.ctidTraderAccountId}")
            else:
                final_acc = authorized_accounts[0]["account"]
                logger.warning(f"⚠️ No exact match for Env {self.config.bot_env}. Falling back to Authorized Account: {final_acc.ctidTraderAccountId}")
            
            self.account_id = final_acc.ctidTraderAccountId

        await self.client.authenticate_account(self.account_id)
        
        # Verify mode vs intended environment
        is_live = any(a.isLive for a in acc_list.ctidTraderAccount if a.ctidTraderAccountId == self.account_id)
        current_mode = "LIVE" if is_live else "DEMO"
        
        if self.config.bot_env != current_mode:
            if self.config.bot_env == "LIVE" and current_mode == "DEMO":
                 logger.warning(f"⚠️ Account {self.config.account_id} not available or authorized. Entering Safety Demo Mode.")
                 self.notifier.is_authorized = False
                 await self.notifier.send_message(
                     "🛡️ <b>Safety Demo Mode Activated</b>\n"
                     "Your Live account is not authorized for trading.\n\n"
                     "Fix permissions via the 🛠️ <b>Fix Permissions</b> button in /menu, then restart the bot."
                 )
            elif self.config.bot_env == "DEMO" and current_mode == "LIVE":
                 logger.critical("FORCING STOP: Tried to run DEMO logic on LIVE account!")
                 await self.notifier.send_message("🛑 <b>STOPPED</b>: Safety trigger. Tried to run DEMO on LIVE account.")
                 self.stop()
                 return
        else:
            self.notifier.is_authorized = True

        # Initialize Performance and Executioner
        trader_resp = await self.client.get_trader_info(self.account_id)
        trader_info = trader_resp.trader
        m_digits = trader_info.moneyDigits if hasattr(trader_info, 'moneyDigits') else 0
        balance = trader_info.balance / (10 ** m_digits)
        self.performance.set_initial_balance(balance)
        self.performance.live_mode = is_live
        
        # Check actual trading permission
        self.can_trade = getattr(trader_info, 'canTrade', False)
        perm_scope = "FULL (Trade + View)" if self.can_trade else "VIEW ONLY"
        
        broker = trader_info.brokerName if hasattr(trader_info, 'brokerName') else 'Unknown'
        login = trader_info.traderLogin if hasattr(trader_info, 'traderLogin') else 'Unknown'
        
        self.notifier.set_account_info(
            self.account_id,
            current_mode,
            broker,
            login,
            balance=balance,
            permission_scope=perm_scope
        )

        self.executioner = OrderManager(self.client, self.notifier, self.account_id, self.performance)
        self.client.add_callback(model.PROTO_OA_EXECUTION_EVENT, self.executioner.handle_execution_event)

        if not self.symbol_id:
            logger.debug(f"Discovering Symbol ID for {self.config.symbol_name}...")
            symbols_res = await self.client.get_symbols_list(self.account_id)
            for s in symbols_res.symbol:
                if s.symbolName == self.config.symbol_name:
                    self.symbol_id = s.symbolId
                    break
        
        if not self.symbol_id:
            raise ValueError(f"Symbol {self.config.symbol_name} not found")

        # Subscribe to spots
        self.client.add_callback(model.PROTO_OA_SPOT_EVENT, self.on_spot_event)
        req = oa.ProtoOASubscribeSpotsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId.append(self.symbol_id)
        req.subscribeToSpotTimestamp = True
        await self.client.send(req)
        
        # Start Heartbeat if not already running
        if not self.heartbeat_task:
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info(f"📊 {current_mode} Bot Synchronized: {self.config.symbol_name} (ID: {self.account_id})")


    async def switch_account(self, new_account_id: str):
        """Switch to a different account"""
        try:
            new_account_id = int(new_account_id)
            
            # Disconnect current session
            await self.client.disconnect()
            await asyncio.sleep(1)  # Brief pause
            
            # Update account
            self.account_id = new_account_id
            self.symbol_id = None  # Will be rediscovered
            
            # Update account info in notifier
            account_type = "Demo" if self.config.dry_run else "Live"
            self.notifier.set_account_info(self.account_id, account_type)
            
            # Clear executioner to reinitialize with new account
            if self.executioner:
                self.executioner = None
            
            # Clear positions tracking
            self.performance.reset()
            
            logger.info(f"Switched to account {new_account_id}")
            await self.notifier.send_message(f"🔄 <b>Account Switched</b>\nNew Account: {new_account_id}")
            
            # Force reconnection with new account
            self.running = True  # Ensure we continue running
            
        except Exception as e:
            logger.error(f"Failed to switch account: {e}")
            await self.notifier.send_message(f"❌ <b>Account Switch Failed</b>\nError: {e}")
            raise

    async def switch_mode(self, new_mode: str):
        """Switch between LIVE and DEMO environments"""
        try:
            logger.info(f"🔄 Switching environment to {new_mode}...")
            self.config.bot_env = new_mode.upper()
            
            # Disconnect to trigger a clean setup_session with the new env preference
            if self.client and self.client.is_connected:
                await self.client.disconnect()
                
            await self.notifier.send_message(f"🔄 <b>Environment Switched</b>\nNew Target: {new_mode}")
        except Exception as e:
            logger.error(f"Failed to switch mode: {e}")
            await self.notifier.send_message(f"❌ <b>Mode Switch Failed</b>\nError: {e}")

    async def run(self):
        import os
        backoff = 1
        max_backoff = 60
        mode_str = "DRY RUN MODE" if self.config.dry_run else "FULL LOGIC ENABLED"
        await self.notifier.send_message(f"🤖 <b>Bot Online</b> ({mode_str})")
        logger.info("[DEBUG] HFTBot.run() started. PID: %s", os.getpid())
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
                logger.exception("Bot Loop Error")
                logger.error(f"[DEBUG] Exception in HFTBot.run(): {e}")
                if self.running:
                    await self.notifier.notify_error(f"System Error: {e}")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, max_backoff)
            finally:
                await self.client.disconnect()
                logger.info("[DEBUG] HFTBot.run() finished. PID: %s", os.getpid())

    def stop(self):
        import os
        self.running = False
        logger.info("Stopping bot...")
        logger.info("[DEBUG] HFTBot.stop() called. PID: %s", os.getpid())
        # Stop Telegram polling
        if self.notifier.enabled:
            asyncio.create_task(self.notifier.stop_polling())

    def restart(self):
        import os
        logger.info("🔄 Restarting bot...")
        logger.info("[DEBUG] HFTBot.restart() called. PID: %s", os.getpid())
        # Disconnect the current client to trigger reconnection
        if self.client and self.client.is_connected:
            asyncio.create_task(self.client.disconnect())
            logger.info("✅ Disconnected from cTrader. Bot will automatically reconnect...")

async def main():
    bot = HFTBot()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, bot.stop)
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())