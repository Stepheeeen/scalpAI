import asyncio
import psutil
import datetime
from telegram import Bot, Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest
import logging
import json
import os

MAX_TELEGRAM_MESSAGE_LENGTH = 3900

class TelegramLogHandler(logging.Handler):
    def __init__(self, notifier):
        super().__init__()
        self.notifier = notifier
        # Only these logger names send critical events to Telegram
        self.critical_loggers = {
            "Main": {"ERROR", "WARNING", "CRITICAL"},
            "CTraderClient": {"ERROR", "CRITICAL"},
            "OrderManager": {"ERROR", "CRITICAL"},
            "PerformanceTracker": {"CRITICAL"},
            "XGBoostGatekeeper": {"ERROR", "CRITICAL"},
        }

    def _should_send(self, record):
        """Only send ERROR, WARNING, or CRITICAL logs from whitelisted sources"""
        level_name = logging.getLevelName(record.levelno)
        # Prevent infinite logging loop: never send telegram or httpx errors to telegram
        if record.name in ("TelegramNotifier", "httpx") or record.name.startswith("telegram"):
            return False

        # Always send errors and warnings from critical loggers
        if record.levelno >= logging.ERROR:
            return True
        
        # Don't send DEBUG or INFO to Telegram to reduce noise
        if record.levelno < logging.WARNING:
            return False
        
        # Only send WARNING+ from our bot loggers
        logger_name = record.name
        for critical_logger, allowed_levels in self.critical_loggers.items():
            if logger_name.startswith(critical_logger) and level_name in allowed_levels:
                return True
        
        return False

    def emit(self, record):
        if not self.notifier.enabled or not self.notifier.bot:
            return

        if not self._should_send(record):
            return

        try:
            message = self.format(record)
            if not message:
                return

            # Skip spam messages
            if "High Latency" in message or "No trade signal" in message:
                return

            if len(message) > MAX_TELEGRAM_MESSAGE_LENGTH:
                message = message[:MAX_TELEGRAM_MESSAGE_LENGTH] + "\n\n<truncated>"

            loop = asyncio.get_running_loop()
            loop.create_task(self.notifier.send_message(message))
        except RuntimeError:
            pass
        except Exception:
            self.handleError(record)

class AccountManager:
    def __init__(self, accounts_file="accounts.json"):
        self.accounts_file = accounts_file
        self.accounts = self._load_accounts()
        
    def _load_accounts(self):
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading accounts: {e}")
        return {}
    
    def _save_accounts(self):
        try:
            with open(self.accounts_file, 'w') as f:
                json.dump(self.accounts, f, indent=2)
        except Exception as e:
            print(f"Error saving accounts: {e}")
    
    def add_account(self, account_id: str, description: str = ""):
        account_id = str(account_id).strip()
        if account_id in self.accounts:
            return False, "Account already exists"
        
        self.accounts[account_id] = {
            "description": description,
            "verified": False,
            "added_at": str(asyncio.get_event_loop().time())
        }
        self._save_accounts()
        return True, f"Account {account_id} added successfully"
    
    def verify_account(self, account_id: str):
        account_id = str(account_id).strip()
        if account_id not in self.accounts:
            return False, "Account not found"
        
        self.accounts[account_id]["verified"] = True
        self._save_accounts()
        return True, f"Account {account_id} marked as verified"
    
    def remove_account(self, account_id: str):
        account_id = str(account_id).strip()
        if account_id not in self.accounts:
            return False, "Account not found"
        
        del self.accounts[account_id]
        self._save_accounts()
        return True, f"Account {account_id} removed"
    
    def list_accounts(self):
        if not self.accounts:
            return "No accounts configured"
        
        result = "ð <b>Configured Accounts:</b>\n\n"
        for account_id, data in self.accounts.items():
            status = "✅ Verified" if data.get("verified", False) else "⏳ Unverified"
            desc = f" - {data.get('description', '')}" if data.get('description') else ""
            result += f"• {account_id} {status}{desc}\n"
        return result
    
    def get_verified_accounts(self):
        return [acc_id for acc_id, data in self.accounts.items() if data.get("verified", False)]

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, enabled: bool = True):
        self.enabled = enabled
        self.token = token
        self.chat_id = chat_id
        self.http_request = HTTPXRequest(
            connection_pool_size=128,
            pool_timeout=30.0,
            read_timeout=20.0,
            write_timeout=20.0,
            connect_timeout=10.0,
        ) if enabled and token else None
        self.bot = Bot(token=token, request=self.http_request) if enabled and token else None
        self.logger = logging.getLogger("TelegramNotifier")
        self.account_manager = AccountManager()
        self.command_handlers = {}
        self.application = None
        self.polling_task = None
        self.stop_callback = None
        self.restart_callback = None
        self.ctrader_token = None
        self.is_authorized = True # Default to true
        self.current_account_permission_scope = "Unknown"
        self._message_lock = asyncio.Lock()
        self.dashboard_msg_id = None
        self.bot_start_time = datetime.datetime.now()
        self.current_account_id = None
        self.current_account_balance = 0.0
        self.current_account_type = "None"
        self.bot_state = "🟡 Starting" # 🟡 Starting, 🟢 Trading, ⏳ Reconnecting..., 🛑 Stopped, ⚠️ Warning
        
        if self.enabled and self.token:
            self._setup_command_handlers()

    def get_system_stats(self):
        """Fetch VPS resource usage metrics"""
        try:
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            uptime_seconds = (datetime.datetime.now() - self.bot_start_time).total_seconds()
            hours, remainder = divmod(int(uptime_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime_str = f"{hours}h {minutes}m"
            return cpu, ram, uptime_str
        except:
            return 0.0, 0.0, "Unknown"

    def _get_dashboard_markup(self):
        """Generate the inline keyboard for the dashboard"""
        keyboard = [
            [
                InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_dash"),
                InlineKeyboardButton("👤 My Profile", callback_data="view_profile")
            ],
            [
                InlineKeyboardButton("🧪 Switch to DEMO", callback_data="switch_demo"),
                InlineKeyboardButton("🚀 Switch to LIVE", callback_data="switch_live")
            ],
            [
                InlineKeyboardButton("📊 Detailed KPIs", callback_data="view_kpis"),
                InlineKeyboardButton("🛑 Stop Bot", callback_data="confirm_stop")
            ]
        ]
        # If unauthorized, add the fix button
        if not self.is_authorized:
            keyboard.insert(0, [InlineKeyboardButton("🛠️ FIX PERMISSIONS", url="https://openapi.ctrader.com/apps")])
            
        return InlineKeyboardMarkup(keyboard)

    async def _render_dashboard_text(self):
        """Generate the dashboard text content"""
        cpu, ram, uptime = self.get_system_stats()
        acc_id = self.current_account_id or "---"
        acc_type = self.current_account_type or "Unknown"
        acc_bal = f"${self.current_account_balance:,.2f}" if self.current_account_balance else "---"
        pnl = 0.0
        daily_pnl = 0.0
        win_rate = 0.0
        if hasattr(self, 'performance_tracker') and self.performance_tracker:
            pnl = self.performance_tracker.net_pnl
            daily_pnl = self.performance_tracker.daily_pnl
            win_rate = self.performance_tracker.win_rate
            
        pnl_str = f"<b>{'+' if pnl >=0 else ''}${pnl:,.2f}</b>"
        daily_pnl_str = f"{'+' if daily_pnl >=0 else ''}${daily_pnl:,.2f}"
        
        # Connection & Authorization info
        conn_line = f"🤖 State: {self.bot_state}"
        if not self.is_authorized:
            conn_line = "🔐 State: 🟡 Authorization Needed"
            
        text = (
            f"🎮 <b>ScalpAI Command Center</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{conn_line}\n"
            f"⏱️ Uptime: <code>{uptime}</code> | WR: <code>{win_rate:.0f}%</code>\n"
            f"💻 CPU: <code>{cpu}%</code> | RAM: <code>{ram}%</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Account: <code>{acc_id}</code> ({acc_type})\n"
            f"💰 Balance: <b>{acc_bal}</b>\n"
            f"📈 Daily PnL: <code>{daily_pnl_str}</code>\n"
            f"📊 Total PnL: {pnl_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Last Update: {datetime.datetime.now().strftime('%H:%M:%S')}</i>"
        )
        return text

    def _setup_command_handlers(self):
        """Setup Telegram command handlers for account management"""
        self.command_handlers = {
            'start': self._cmd_start,
            'help': self._cmd_help,
            'add_account': self._cmd_add_account,
            'verify_account': self._cmd_verify_account,
            'remove_account': self._cmd_remove_account,
            'list_accounts': self._cmd_list_accounts,
            'switch_account': self._cmd_switch_account,
            'status': self._cmd_status,
            'permission': self._cmd_permission,
            'account': self._cmd_account,
            'set_balance': self._cmd_set_balance,
            'kpis': self._cmd_kpis,
            'performance': self._cmd_performance,
            'pnl': self._cmd_pnl,
            'stats': self._cmd_stats,
            'signals': self._cmd_signals,
            'reset_stats': self._cmd_reset_stats,
            'stop': self._cmd_stop,
            'restart': self._cmd_restart,
            'mode': self._cmd_mode,
            'dashboard': self._cmd_dashboard,
            'menu': self._cmd_dashboard,
            'profile': self._cmd_profile,
        }

    async def start_polling(self):
        """Start the Telegram bot polling for commands"""
        if not self.enabled or not self.token:
            return

        try:
            builder = Application.builder().token(self.token)
            if self.http_request:
                builder = builder.request(self.http_request).get_updates_request(self.http_request)
            self.application = builder.build()

            # Add command handlers
            for cmd, handler in self.command_handlers.items():
                self.application.add_handler(CommandHandler(cmd, handler))
                
            # Add alias for dashboard
            self.application.add_handler(CommandHandler("dashboard", self._cmd_dashboard))
            self.application.add_handler(CommandHandler("menu", self._cmd_dashboard))

            # Add callback query handler for buttons
            self.application.add_handler(CallbackQueryHandler(self._handle_callback))

            # Add message handler for unknown commands
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(
                error_callback=lambda error: self.logger.error(f"Telegram polling error: {error}")
            )
            self.logger.info("Telegram command polling started")
            await self.send_message("✅ <b>Telegram command interface is active.</b>\nUse /help to see available commands.")
        except Exception as e:
            self.logger.error(f"Failed to start Telegram polling: {e}")

    async def stop_polling(self):
        """Stop the Telegram bot polling"""
        if self.application:
            try:
                if self.application.updater and self.application.updater.running:
                    await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            except Exception as e:
                self.logger.error(f"Error stopping Telegram polling: {e}")

        if self.polling_task and not self.polling_task.done():
            self.polling_task.cancel()

    async def _cmd_start(self, update, context):
        """Handle /start command"""
        try:
            incoming_chat_id = str(update.effective_chat.id)
            self.logger.info(f"Received /start command from chat ID: {incoming_chat_id}")
            
            if incoming_chat_id != self.chat_id:
                self.logger.warning(f"Unauthorized /start attempt from chat ID: {incoming_chat_id} (expected: {self.chat_id})")
                return

            welcome_msg = (
                "ð¤ <b>XAUUSD Trading Bot</b>\n\n"
                "Available commands:\n"
                "/help - Show all commands\n"
                "/status - Bot status\n"
                "/kpis - Key performance indicators\n"
                "/performance - Trading performance\n"
                "/pnl - Profit & loss summary\n"
                "/stats - Trading statistics\n"
                "/signals - Signal analysis\n"
                "/permission - Show current trading permission scope\n"
                "/add_account &lt;id&gt; [description] - Add account\n"
                "/verify_account &lt;id&gt; - Verify account\n"
                "/remove_account &lt;id&gt; - Remove account\n"
                "/list_accounts - List all accounts\n"
                "/switch_account &lt;id&gt; - Switch to account\n"
                "/mode &lt;live|demo&gt; - Switch environment mode\n"
                "/reset_stats confirm - Reset statistics\n"
                "/stop - Stop bot execution\n\n"
                "All bot activity will be logged here automatically."
            )
            reply_keyboard = ReplyKeyboardMarkup(
                [["/status", "/stop"], ["/help", "/list_accounts"]],
                resize_keyboard=True,
                one_time_keyboard=False,
            )
            await update.message.reply_text(
                welcome_msg,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_keyboard,
            )
            self.logger.info("Successfully sent /start response")
        except Exception as e:
            self.logger.error(f"Error handling /start command: {e}")
            # Try to send a simple response even if there's an error
            try:
                await update.message.reply_text("ð¤ Bot is active! Use /help for commands.")
            except Exception as e2:
                self.logger.error(f"Failed to send fallback /start response: {e2}")

    async def _cmd_help(self, update, context):
        """Handle /help command"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        help_msg = (
            "ð <b>ScalpAI XAUUSD Trading Bot - Command Reference</b>\n\n"
            "ð¤ <b>Getting Started:</b>\n"
            "/start - Show welcome message and keyboard\n"
            "/help - Show this comprehensive help\n"
            "/status - Current bot status and account info\n\n"
            "ð <b>Performance Monitoring:</b>\n"
            "/kpis - Key performance indicators (signals, trades, P&L)\n"
            "/performance - Detailed trading performance\n"
            "/pnl - Profit & loss breakdown\n"
            "/stats - Trading statistics and AI metrics\n"
            "/signals - Signal generation analysis\n"
            "(Zero accepted trades means no signal passed the confidence threshold or an open position was already active.)\n\n"
            "ð¤ <b>Account Management:</b>\n"
            "/list_accounts - Show all configured accounts\n"
            "/account - Show current trading account details\n"
            "/permission - Show current trading permission scope\n"
            "/set_balance &lt;amount&gt; - Set initial account balance for tracking\n"
            "/add_account &lt;id&gt; [description] - Add trading account\n"
            "/verify_account &lt;id&gt; - Verify account connection\n"
            "/remove_account &lt;id&gt; - Remove account from bot\n"
            "/switch_account &lt;id&gt; - Switch to different account\n\n"
            "⚙️ <b>Bot Control:</b>\n"
            "/stop - Stop bot execution and Telegram polling\n"
            "/restart - Restart the bot (reconnect and resume trading)\n"
            "/mode &lt;live|demo&gt; - Switch between LIVE and DEMO environments\n"
            "/reset_stats confirm - Reset all performance statistics\n\n"
            "ð¡ <b>How to Use:</b>\n"
            "1. Add your cTrader account: /add_account 46801669\n"
            "2. Verify connection: /verify_account 46801669\n"
            "3. Monitor performance: /kpis, /status, /account\n"
            "4. Control trading: /stop to halt operations\n\n"
            "ð <b>Security:</b> Commands only work from authorized chat ID\n"
            "ð± <b>Keyboard:</b> Use reply keyboard buttons for quick access"
        )
        await update.message.reply_text(help_msg, parse_mode=ParseMode.HTML)
    
    async def _cmd_account(self, update, context):
        """Handle /account command"""
        if str(update.effective_chat.id) != self.chat_id:
            return

        account_id = self.current_account_id or "Not configured"
        account_type = getattr(self, 'current_account_type', 'Unknown')
        account_broker = getattr(self, 'current_account_broker', 'Unknown')
        account_login = getattr(self, 'current_account_login', 'Unknown')
        status = "Active" if self.current_account_id else "Not configured"
        
        # Get balance information
        if self.current_account_balance is not None:
            balance_info = f"${self.current_account_balance:.2f}"
            if hasattr(self, 'performance_tracker') and self.performance_tracker and self.performance_tracker.initial_balance > 0:
                balance_info = f"${self.performance_tracker.get_current_balance():.2f} (Initial: ${self.performance_tracker.initial_balance:.2f})"
        else:
            balance_info = "Not available"
            if hasattr(self, 'performance_tracker') and self.performance_tracker:
                current_balance = self.performance_tracker.get_current_balance()
                initial_balance = self.performance_tracker.initial_balance
                if initial_balance > 0:
                    balance_info = f"${current_balance:.2f} (Initial: ${initial_balance:.2f})"
                elif self.performance_tracker.net_pnl != 0:
                    balance_info = f"Unknown initial + ${self.performance_tracker.net_pnl:.2f} P&L"
                else:
                    balance_info = "Not set (use /set_balance &lt;amount&gt; to initialize)"
        
        account_msg = (
            "ð¤ <b>Trading Account Details</b>\n\n"
            f"Account ID: {account_id}\n"
            f"Login: {account_login}\n"
            f"Broker: {account_broker}\n"
            f"Account Type: {account_type}\n"
            f"Permission Scope: {self.current_account_permission_scope}\n"
            f"Status: {status}\n"
            f"Balance: {balance_info}\n\n"
            "ℹ️ This is the account the bot will use for trading when a signal is accepted.\n"
            "Use /set_balance &lt;amount&gt; to set your initial account balance for tracking."
        )
        await update.message.reply_text(account_msg, parse_mode=ParseMode.HTML)

    async def _cmd_set_balance(self, update, context):
        """Handle /set_balance command"""
        if str(update.effective_chat.id) != self.chat_id:
            return

        args = context.args
        if not args:
            await update.message.reply_text("❌ Usage: /set_balance &lt;amount&gt;\nExample: /set_balance 10000", parse_mode=ParseMode.HTML)
            return

        try:
            balance = float(args[0])
            if balance < 0:
                await update.message.reply_text("❌ Balance must be a positive number", parse_mode=ParseMode.HTML)
                return

            if hasattr(self, 'performance_tracker') and self.performance_tracker:
                self.performance_tracker.set_initial_balance(balance)
                await update.message.reply_text(
                    f"ð° <b>Initial Balance Set</b>\n"
                    f"Balance: ${balance:.2f}\n\n"
                    f"The bot will now track your account balance based on trading P&L.",
                    parse_mode=ParseMode.HTML
                )
            else:
                await update.message.reply_text("❌ Performance tracker not available", parse_mode=ParseMode.HTML)
        except ValueError:
            await update.message.reply_text("❌ Invalid balance amount. Please provide a valid number.", parse_mode=ParseMode.HTML)

    async def _cmd_stop(self, update, context):
        """Handle /stop command"""
        if str(update.effective_chat.id) != self.chat_id:
            return

        if self.stop_callback:
            await update.message.reply_text(
                "ð <b>Stop request received.</b> Shutting down bot...",
                parse_mode=ParseMode.HTML,
            )
            try:
                if asyncio.iscoroutinefunction(self.stop_callback):
                    await self.stop_callback()
                else:
                    self.stop_callback()
            except Exception as e:
                self.logger.error(f"Error running stop callback: {e}")
                await update.message.reply_text(
                    f"❌ Failed to stop bot cleanly: {e}",
                    parse_mode=ParseMode.HTML,
                )
        else:
            await update.message.reply_text(
                "❌ Stop command is not configured yet.",
                parse_mode=ParseMode.HTML,
            )

    async def _cmd_restart(self, update, context):
        """Handle /restart command"""
        if str(update.effective_chat.id) != self.chat_id:
            return

        if self.restart_callback:
            await update.message.reply_text(
                "ð <b>Restart request received.</b> Reconnecting to cTrader and resuming trading...",
                parse_mode=ParseMode.HTML,
            )
            try:
                if asyncio.iscoroutinefunction(self.restart_callback):
                    await self.restart_callback()
                else:
                    self.restart_callback()
                await update.message.reply_text(
                    "✅ <b>Bot restarted successfully!</b>\nBot is back online and ready to trade.",
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                self.logger.error(f"Error running restart callback: {e}")
                await update.message.reply_text(
                    f"❌ Failed to restart bot: {e}",
                    parse_mode=ParseMode.HTML,
                )
        else:
            await update.message.reply_text(
                "❌ Restart command is not configured yet.",
                parse_mode=ParseMode.HTML,
            )

    def set_stop_callback(self, callback):
        """Set callback that stops the bot from the Telegram command"""
        self.stop_callback = callback

    def set_restart_callback(self, callback):
        """Set callback that restarts the bot from the Telegram command"""
        self.restart_callback = callback

    def set_account_info(
        self,
        account_id: int,
        account_type: str = "Unknown",
        broker: str = "Unknown",
        login: str = "Unknown",
        balance: float = None,
        permission_scope: str = "Unknown",
    ):
        """Set current trading account information"""
        self.current_account_id = account_id
        self.current_account_type = account_type
        self.current_account_broker = broker
        self.current_account_login = login
        self.current_account_balance = balance
        self.current_account_permission_scope = permission_scope

    async def _cmd_add_account(self, update, context):
        """Handle /add_account command"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        args = context.args
        if not args:
            await update.message.reply_text("❌ Usage: /add_account &lt;account_id&gt; [description]", parse_mode=ParseMode.HTML)
            return
            
        account_id = args[0]
        description = " ".join(args[1:]) if len(args) > 1 else ""
        
        success, message = self.account_manager.add_account(account_id, description)
        status_icon = "✅" if success else "❌"
        await update.message.reply_text(f"{status_icon} {message}", parse_mode=ParseMode.HTML)
    
    async def _cmd_verify_account(self, update, context):
        """Handle /verify_account command"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        args = context.args
        if not args:
            await update.message.reply_text("❌ Usage: /verify_account &lt;account_id&gt;", parse_mode=ParseMode.HTML)
            return
            
        account_id = args[0]
        success, message = self.account_manager.verify_account(account_id)
        status_icon = "✅" if success else "❌"
        await update.message.reply_text(f"{status_icon} {message}", parse_mode=ParseMode.HTML)
    
    async def _cmd_remove_account(self, update, context):
        """Handle /remove_account command"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        args = context.args
        if not args:
            await update.message.reply_text("❌ Usage: /remove_account &lt;account_id&gt;", parse_mode=ParseMode.HTML)
            return
            
        account_id = args[0]
        success, message = self.account_manager.remove_account(account_id)
        status_icon = "✅" if success else "❌"
        await update.message.reply_text(f"{status_icon} {message}", parse_mode=ParseMode.HTML)
    
    async def _cmd_list_accounts(self, update, context):
        """Handle /list_accounts command"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        accounts_list = self.account_manager.list_accounts()
        await update.message.reply_text(accounts_list, parse_mode=ParseMode.HTML)
    
    async def _cmd_switch_account(self, update, context):
        """Handle /switch_account command"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        args = context.args
        if not args:
            await update.message.reply_text("❌ Usage: /switch_account &lt;account_id&gt;", parse_mode=ParseMode.HTML)
            return
            
        account_id = args[0]
        
        # Check if account exists and is verified
        if account_id not in self.account_manager.accounts:
            await update.message.reply_text(f"❌ Account {account_id} not found. Use /add_account first.", parse_mode=ParseMode.HTML)
            return
            
        if not self.account_manager.accounts[account_id].get("verified", False):
            await update.message.reply_text(f"⚠️ Account {account_id} is not verified. Use /verify_account first.", parse_mode=ParseMode.HTML)
            return
        
        # Signal to bot to switch account
        if hasattr(self, 'account_switch_callback') and self.account_switch_callback:
            try:
                await self.account_switch_callback(account_id)
                await update.message.reply_text(f"ð Switching to account {account_id}...", parse_mode=ParseMode.HTML)
            except Exception as e:
                await update.message.reply_text(f"❌ Failed to switch account: {e}", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("❌ Account switching not available (bot not running)", parse_mode=ParseMode.HTML)

    async def _cmd_mode(self, update, context):
        """Handle /mode command - switch between LIVE and DEMO"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        args = context.args
        if not args:
            current = self.current_account_type
            await update.message.reply_text(f"ℹ️ Current Mode: <b>{current}</b>\nUsage: /mode &lt;live|demo&gt;", parse_mode=ParseMode.HTML)
            return
            
        new_mode = args[0].upper()
        if new_mode not in ["LIVE", "DEMO"]:
            await update.message.reply_text("❌ Invalid mode. Use /mode live or /mode demo", parse_mode=ParseMode.HTML)
            return
            
        if new_mode == self.current_account_type:
            await update.message.reply_text(f"ℹ️ Bot is already in {new_mode} mode.", parse_mode=ParseMode.HTML)
            return

        # We trigger a restart with the new mode
        await update.message.reply_text(f"🔄 <b>Switching to {new_mode} mode...</b>\nBot will discover and connect to the matching account.", parse_mode=ParseMode.HTML)
        
        # We need a way to tell the bot its config has changed. 
        # For now, we can try to find the other account type if discovery logic is in the bot.
        # But a safer way is to update the env or just trigger the restart logic in the bot.
        if hasattr(self, 'mode_switch_callback') and self.mode_switch_callback:
            await self.mode_switch_callback(new_mode)
        else:
            # If no direct callback, we can try to use restart_callback if it handles re-loading config
            if self.restart_callback:
                # We assume the bot will re-read the environment or we provide a way to pass it.
                # Since we don't have a direct env writer here, we'll suggest manual .env edit if it fails.
                if asyncio.iscoroutinefunction(self.restart_callback):
                    await self.restart_callback()
                else:
                    self.restart_callback()
    
    async def _cmd_status(self, update, context):
        """Handle /status command"""
        if str(update.effective_chat.id) != self.chat_id:
            return

        self.logger.info("Received /status command")
            
        # Build account information
        account_info = ""
        if self.current_account_id:
            account_info = (
                f"Account ID: {self.current_account_id}\n"
                f"Login: {self.current_account_login}\n"
                f"Broker: {self.current_account_broker}\n"
                f"Account Type: {self.current_account_type}\n"
                f"Permission Scope: {self.current_account_permission_scope}\n"
            )
        else:
            account_info = "Account: Not configured\n"
        
        status_msg = (
            "ð <b>Bot Status</b>\n\n"
            "📊 <b>Bot Status</b>\n\n"
            "🤖 <b>Bot Information:</b>\n"
            "Status: Running\n"
            "Mode: Live Trading\n"
            "Symbol: XAUUSD\n\n"
            "👤 <b>Trading Account:</b>\n" +
            account_info +
            f"Verified Accounts: {len(self.account_manager.get_verified_accounts())}\n\n"
            "📈 <b>Quick Actions:</b>\n"
            "Use /kpis for performance\n"
            "Use /account for trading account details"
        )
        await update.message.reply_text(status_msg, parse_mode=ParseMode.HTML)

    async def _cmd_permission(self, update, context):
        """Handle /permission command - Explain Token Scope vs Account Linking"""
        if str(update.effective_chat.id) != self.chat_id:
            return

        permission_scope = getattr(self, 'current_account_permission_scope', 'Unknown')
        scope_text = permission_scope if permission_scope else 'Unknown'
        
        info_text = (
            f"🔐 <b>Trading Permission Scope</b>\n\n"
            f"<b>Token Level:</b> <code>{scope_text}</code>\n"
            f"<i>(This confirms your API token can place trades)</i>\n\n"
            "⚠️ <b>IMPORTANT:</b> If you get 'Account Not Authorized' errors, you must ALSO link your specific trading accounts to the App in the cTrader User Portal."
        )
        
        keyboard = [[InlineKeyboardButton("🛠️ LINK ACCOUNTS NOW", url="https://openapi.ctrader.com/apps")]]
        
        await update.message.reply_text(
            info_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def _cmd_kpis(self, update, context):
        """Handle /kpis command - Show comprehensive KPIs"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        if not hasattr(self, 'performance_tracker') or not self.performance_tracker:
            await update.message.reply_text("❌ Performance tracker not available", parse_mode=ParseMode.HTML)
            return
            
        kpis_msg = (
            "ð <b>Key Performance Indicators</b>\n\n"
            f"ð¯ <b>Signals:</b> {self.performance_tracker.signals_total}\n"
            f"✅ Accepted: {self.performance_tracker.signals_accepted}\n"
            f"❌ Rejected: {self.performance_tracker.signals_rejected}\n\n"
            f"ð <b>Trading:</b>\n"
            f"ð Attempts: {self.performance_tracker.trade_attempts}\n"
            f"ð¤ Orders: {self.performance_tracker.order_submissions}\n"
            f"ð Open Positions: {self.performance_tracker.open_positions}\n"
            f"✅ Closed Trades: {self.performance_tracker.closed_trades}\n\n"
            f"ð° <b>Results:</b>\n"
            f"ð Wins: {self.performance_tracker.wins}\n"
            f"ð¥ Losses: {self.performance_tracker.losses}\n"
            f"ð Success Rate: {self.performance_tracker.success_rate()*100:.1f}%\n"
            f"ðµ Net PnL: ${self.performance_tracker.net_pnl:.2f}\n"
            f"ð Avg PnL/Trade: ${self.performance_tracker.average_pnl():.2f}"
        )
        await update.message.reply_text(kpis_msg, parse_mode=ParseMode.HTML)
    
    async def _cmd_performance(self, update, context):
        """Handle /performance command - Alias for KPIs"""
        await self._cmd_kpis(update, context)
    
    async def _cmd_pnl(self, update, context):
        """Handle /pnl command - Show profit/loss details"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        if not hasattr(self, 'performance_tracker') or not self.performance_tracker:
            await update.message.reply_text("❌ Performance tracker not available", parse_mode=ParseMode.HTML)
            return
            
        pnl_msg = (
            "ð° <b>Profit & Loss Summary</b>\n\n"
            f"ðµ <b>Net PnL:</b> ${self.performance_tracker.net_pnl:.2f}\n"
            f"ð <b>Average per Trade:</b> ${self.performance_tracker.average_pnl():.2f}\n"
            f"✅ <b>Total Wins:</b> {self.performance_tracker.wins}\n"
            f"ð¥ <b>Total Losses:</b> {self.performance_tracker.losses}\n"
            f"ð <b>Success Rate:</b> {self.performance_tracker.success_rate()*100:.1f}%\n\n"
            f"ð <b>Open Positions:</b> {self.performance_tracker.open_positions}\n"
            f"ð <b>Closed Trades:</b> {self.performance_tracker.closed_trades}"
        )
        await update.message.reply_text(pnl_msg, parse_mode=ParseMode.HTML)
    
    async def _cmd_stats(self, update, context):
        """Handle /stats command - Show trading statistics"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        if not hasattr(self, 'performance_tracker') or not self.performance_tracker:
            await update.message.reply_text("❌ Performance tracker not available", parse_mode=ParseMode.HTML)
            return
            
        stats_msg = (
            "ð <b>Trading Statistics</b>\n\n"
            f"ð¯ <b>Signal Performance:</b>\n"
            f"Total Signals: {self.performance_tracker.signals_total}\n"
            f"Acceptance Rate: {(self.performance_tracker.signals_accepted/self.performance_tracker.signals_total*100 if self.performance_tracker.signals_total > 0 else 0):.1f}%\n\n"
            f"ð <b>Execution Stats:</b>\n"
            f"Trade Attempts: {self.performance_tracker.trade_attempts}\n"
            f"Order Success Rate: {(self.performance_tracker.order_submissions/self.performance_tracker.trade_attempts*100 if self.performance_tracker.trade_attempts > 0 else 0):.1f}%\n\n"
            f"⚡ <b>Live Trading:</b>\n"
            f"Mode: {'LIVE' if self.performance_tracker.live_mode else 'DEMO'}\n"
            f"Target Confidence: {self.performance_tracker.target_confidence:.2f}"
        )
        await update.message.reply_text(stats_msg, parse_mode=ParseMode.HTML)
    
    async def _cmd_signals(self, update, context):
        """Handle /signals command - Show signal analysis"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        if not hasattr(self, 'performance_tracker') or not self.performance_tracker:
            await update.message.reply_text("❌ Performance tracker not available", parse_mode=ParseMode.HTML)
            return
            
        signals_msg = (
            "ð¯ <b>Signal Analysis</b>\n\n"
            f"ð <b>Signal Generation:</b>\n"
            f"Total Signals: {self.performance_tracker.signals_total}\n"
            f"Accepted: {self.performance_tracker.signals_accepted}\n"
            f"Rejected: {self.performance_tracker.signals_rejected}\n\n"
            f"ð <b>AI Performance:</b>\n"
            f"Acceptance Rate: {(self.performance_tracker.signals_accepted/self.performance_tracker.signals_total*100 if self.performance_tracker.signals_total > 0 else 0):.1f}%\n"
            f"Target Confidence: {self.performance_tracker.target_confidence:.2f}\n\n"
            f"ð¡ <b>Signal Types:</b>\n"
            f"• 0 = No Trade (Hold)\n"
            f"• 1 = Buy Signal\n"
            f"• 2 = Sell Signal"
        )
        await update.message.reply_text(signals_msg, parse_mode=ParseMode.HTML)
    
    async def _cmd_reset_stats(self, update, context):
        """Handle /reset_stats command - Reset performance counters"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        if not hasattr(self, 'performance_tracker') or not self.performance_tracker:
            await update.message.reply_text("❌ Performance tracker not available", parse_mode=ParseMode.HTML)
            return
            
        # Ask for confirmation
        args = context.args
        if not args or args[0].lower() != 'confirm':
            await update.message.reply_text(
                "⚠️ <b>WARNING:</b> This will reset all performance statistics!\n\n"
                "To confirm, use: /reset_stats confirm",
                parse_mode=ParseMode.HTML
            )
            return
            
        # Reset the performance tracker
        self.performance_tracker.reset()
        await update.message.reply_text("✅ Performance statistics have been reset", parse_mode=ParseMode.HTML)
    
    async def _handle_message(self, update, context):
        """Handle non-command messages"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        # Ignore non-command messages or provide helpful response
        await update.message.reply_text(
            "ð¤ Use /help to see available commands",
            "🤖 Use /help to see available commands",
            parse_mode=ParseMode.HTML
        )
    
    async def _cmd_dashboard(self, update, context):
        """Handle /dashboard or /menu command"""
        if str(update.effective_chat.id) != self.chat_id:
            return
            
        text = await self._render_dashboard_text()
        markup = self._get_dashboard_markup()
        
        msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        self.dashboard_msg_id = msg.message_id

    async def update_dashboard(self):
        """Update the existing dashboard message if it exists"""
        if not self.enabled or not self.bot or not self.dashboard_msg_id:
            return
            
        async with self._message_lock:
            try:
                text = await self._render_dashboard_text()
                markup = self._get_dashboard_markup()
                await self.bot.edit_message_text(
                    chat_id=self.chat_id,
                    message_id=self.dashboard_msg_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=markup
                )
            except Exception as e:
                # If message is deleted or too old, we clear the ID to avoid spamming errors
                if "Message to edit not found" in str(e) or "message is not modified" in str(e):
                    pass
                else:
                    self.logger.debug(f"Dashboard update failed: {e}")

    async def _handle_callback(self, update, context):
        """Handle button clicks from the inline dashboard"""
        query = update.callback_query
        await query.answer() # Ack the button press
        
        data = query.data
        if data == "refresh_dash":
            await self.update_dashboard()
        elif data == "view_profile":
            await self._cmd_profile(update, context)
        elif data == "switch_live":
            if hasattr(self, 'mode_switch_callback') and self.mode_switch_callback:
                await self.mode_switch_callback("LIVE")
        elif data == "switch_demo":
            if hasattr(self, 'mode_switch_callback') and self.mode_switch_callback:
                await self.mode_switch_callback("DEMO")
        elif data == "view_kpis":
            await self._cmd_kpis(update, context)
        elif data == "confirm_stop":
            keyboard = [[InlineKeyboardButton("⛔ YES, STOP BOT", callback_data="final_stop")]]
            await query.edit_message_text(
                text="⚠️ <b>ARE YOU SURE?</b>\nThis will stop all trading operations immediately.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif data == "final_stop":
            if self.stop_callback:
                if asyncio.iscoroutinefunction(self.stop_callback):
                    await self.stop_callback()
                else:
                    self.stop_callback()

    async def _cmd_profile(self, update, context):
        """Handle /profile command"""
        chat_id = update.effective_chat.id
        if str(chat_id) != self.chat_id:
            return

        cpu, ram, uptime = self.get_system_stats()
        
        # Token Info
        token_preview = f"{self.ctrader_token[:8]}...{self.ctrader_token[-4:]}" if self.ctrader_token else "Not Set"
        
        profile_msg = (
            "👤 <b>Your ScalpAI Profile</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📍 <b>Telegram ID:</b> <code>{chat_id}</code>\n"
            f"🔑 <b>cTrader Token:</b> <code>{token_preview}</code>\n"
            f"🔄 <b>Auto-Refresh:</b> Enabled ✅\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <b>VPS Health:</b>\n"
            f"├ CPU Usage: {cpu}%\n"
            f"├ RAM Usage: {ram}%\n"
            f"└ Bot Uptime: {uptime}\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "ℹ️ <i>Bot is configured via .env file on VPS.</i>"
        )
        
        # Determine if this was a callback or a command
        if update.callback_query:
            await update.callback_query.message.reply_text(profile_msg, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(profile_msg, parse_mode=ParseMode.HTML)

    def set_account_switch_callback(self, callback):
        """Set callback for account switching"""
        self.account_switch_callback = callback

    def set_mode_switch_callback(self, callback):
        """Set callback for environment mode switching"""
        self.mode_switch_callback = callback
    
    def set_performance_tracker(self, tracker):
        """Set the performance tracker for KPI access"""
        self.performance_tracker = tracker
    
    def get_log_handler(self):
        """Get a TelegramLogHandler for logging integration"""
        return TelegramLogHandler(self)
    async def send_message(self, text: str):
        if not self.enabled or not self.bot:
            return

        async with self._message_lock:
            try:
                formatted_text = f"<b>[XAUUSD Bot]</b>\n{text}"
                if len(formatted_text) > MAX_TELEGRAM_MESSAGE_LENGTH:
                    formatted_text = formatted_text[:MAX_TELEGRAM_MESSAGE_LENGTH] + "\n\n<truncated>"

                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=formatted_text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                self.logger.error(f"Failed to send Telegram message: {e}")

    async def notify_trade(self, side: str, volume: float, price: float):
        msg = f"ð <b>Trade Executed</b>\nSide: {side}\nVolume: {volume}\nPrice: {price}"
        await self.send_message(msg)

    async def notify_reconnect(self, attempt: int, delay: float):
        msg = f"ð <b>Reconnecting...</b>\nAttempt: {attempt}\nWait: {delay}s"
        await self.send_message(msg)

    async def notify_error(self, error: str):
        msg = f"⚠️ <b>Error Alert</b>\n{error}"
        await self.send_message(msg)
        
    async def notify_status(self, status: str, latency: int):
        msg = f"ð <b>Status Update</b>\nStatus: {status}\nLatency: {latency}ms"
        await self.send_message(msg)