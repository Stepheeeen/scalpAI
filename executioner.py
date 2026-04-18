import logging
from openapi_pb2 import OpenApiMessages_pb2 as oa
from openapi_pb2 import OpenApiModelMessages_pb2 as model

class OrderManager:
    def __init__(self, client, notifier, account_id: int):
        self.client = client
        self.notifier = notifier
        self.account_id = account_id
        self.positions = {} # position_id -> {entry_price, side, has_be_set}
        self.logger = logging.getLogger("OrderManager")

    async def handle_execution_event(self, proto_msg):
        event = oa.ProtoOAExecutionEvent()
        event.ParseFromString(proto_msg.payload)
        
        execution_type = event.executionType
        
        if execution_type == model.ORDER_FILLED:
            pos = event.position
            deal = event.deal
            
            # 1. Check if it's an OPEN or CLOSE
            # deal.volume is total volume. For opening, it matches position.volume.
            if deal.closingDealId: # This is a closing deal
                if pos.positionId in self.positions:
                    del self.positions[pos.positionId]
                    self.logger.info(f"Position {pos.positionId} closed.")
            else: # This is an opening deal
                self.positions[pos.positionId] = {
                    "entry_price": deal.executionPrice,
                    "side": "BUY" if deal.tradeSide == model.BUY else "SELL",
                    "has_be_set": False,
                    "symbol_id": pos.symbolId
                }
                self.logger.info(f"Position {pos.positionId} opened at {deal.executionPrice}")
                await self.notifier.notify_trade(
                    "BUY" if deal.tradeSide == model.BUY else "SELL", 
                    deal.volume / 100.0, 
                    deal.executionPrice
                )

    async def check_break_even(self, symbol_id: int, current_bid: float, current_ask: float):
        """Checks all open positions for 5 pips profit to move SL to Entry."""
        BE_THRESHOLD_PIPS = 5
        
        for pos_id, data in list(self.positions.items()):
            if data["symbol_id"] != symbol_id or data["has_be_set"]:
                continue
            
            entry = data["entry_price"]
            side = data["side"]
            
            # Gold 1 pip = 0.01. 5 pips = 0.05
            if side == "BUY":
                profit_pips = (current_bid - entry) * 100
                if profit_pips >= BE_THRESHOLD_PIPS:
                    await self._move_to_be(pos_id, entry)
                    data["has_be_set"] = True
            else: # SELL
                profit_pips = (entry - current_ask) * 100
                if profit_pips >= BE_THRESHOLD_PIPS:
                    await self._move_to_be(pos_id, entry)
                    data["has_be_set"] = True

    async def _move_to_be(self, position_id: int, entry_price: float):
        self.logger.info(f"Moving SL to Break-Even for position {position_id}")
        req = oa.ProtoOAAmendPositionSLTPReq()
        req.ctidTraderAccountId = self.account_id
        req.positionId = position_id
        req.stopLoss = entry_price
        
        try:
            await self.client.send(req)
            await self.notifier.send_message(f"🛡️ <b>Break-Even Set</b> for Pos {position_id}")
        except Exception as e:
            self.logger.error(f"Failed to set Break-Even: {e}")
