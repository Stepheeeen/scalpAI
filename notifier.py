import asyncio
from telegram import Bot
from telegram.constants import ParseMode
import logging

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, enabled: bool = True):
        self.enabled = enabled
        self.token = token
        self.chat_id = chat_id
        self.bot = Bot(token=token) if enabled and token else None
        self.logger = logging.getLogger("TelegramNotifier")

    async def send_message(self, text: str):
        if not self.enabled or not self.bot:
            return
        
        try:
            # Use basic formatting for HFT alerts
            formatted_text = f"<b>[XAUUSD Bot]</b>\n{text}"
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=formatted_text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            self.logger.error(f"Failed to send Telegram message: {e}")

    async def notify_trade(self, side: str, volume: float, price: float):
        msg = f"🚀 <b>Trade Executed</b>\nSide: {side}\nVolume: {volume}\nPrice: {price}"
        await self.send_message(msg)

    async def notify_reconnect(self, attempt: int, delay: float):
        msg = f"🔄 <b>Reconnecting...</b>\nAttempt: {attempt}\nWait: {delay}s"
        await self.send_message(msg)

    async def notify_error(self, error: str):
        msg = f"⚠️ <b>Error Alert</b>\n{error}"
        await self.send_message(msg)
        
    async def notify_status(self, status: str, latency: int):
        msg = f"📊 <b>Status Update</b>\nStatus: {status}\nLatency: {latency}ms"
        await self.send_message(msg)
