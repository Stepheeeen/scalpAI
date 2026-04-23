import logging
from openapi_pb2 import OpenApiMessages_pb2 as oa
from openapi_pb2 import OpenApiModelMessages_pb2 as model

class OrderManager:
    def __init__(self, client, notifier, account_id: int, performance=None):
        self.client = client
        self.notifier = notifier
        self.performance = performance
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
            if deal.closingDealId: # This is a closing deal
                # Calculate PnL and Commission
                pnl = deal.realizedPnL / 100.0 if hasattr(deal, 'realizedPnL') else 0.0
                comm = deal.commission / 100.0 if hasattr(deal, 'commission') else 0.0
                
                self.logger.info(f"💰 Trade Closed: PnL=${pnl:,.2f}, Comm=${comm:,.2f}")
                
                if self.performance:
                    self.performance.log_trade(pnl, comm)
                
                if pos.positionId in self.positions:
                    del self.positions[pos.positionId]
                    if self.performance:
                        self.performance.open_positions = len(self.positions)
                    self.logger.info(f"Position {pos.positionId} removed from tracking.")
                
                await self.notifier.send_message(
                    f"🏁 <b>Trade Closed</b>\n"
                    f"Side: {'BUY' if deal.tradeSide == model.BUY else 'SELL'}\n"
                    f"Price: {deal.executionPrice}\n"
                    f"PnL: <b>${pnl:,.2f}</b>"
                )
            else: # This is an opening deal
                self.positions[pos.positionId] = {
                    "entry_price": deal.executionPrice,
                    "side": "BUY" if deal.tradeSide == model.BUY else "SELL",
                    "has_be_set": False,
                    "symbol_id": pos.symbolId
                }
                if self.performance:
                    self.performance.open_positions = len(self.positions)
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

    async def check_exits(self, symbol_id: int, current_bid: float, current_ask: float):
        """Emergency exit: Closes any trade that reaches +2 pips profit (useful for test trades)"""
        TP_TARGET_PIPS = 2
        
        for pos_id, data in list(self.positions.items()):
            if data["symbol_id"] != symbol_id:
                continue
            
            entry = data["entry_price"]
            side = data["side"]
            
            if side == "BUY":
                profit_pips = (current_bid - entry) * 100
                if profit_pips >= TP_TARGET_PIPS:
                    self.logger.info(f"Target reached for BUY {pos_id}. Closing.")
                    await self.close_position(pos_id)
            else: # SELL
                profit_pips = (entry - current_ask) * 100
                if profit_pips >= TP_TARGET_PIPS:
                    self.logger.info(f"Target reached for SELL {pos_id}. Closing.")
                    await self.close_position(pos_id)

    async def close_position(self, position_id: int):
        """Close a specific position immediately"""
        req = oa.ProtoOAClosePositionReq()
        req.ctidTraderAccountId = self.account_id
        req.positionId = position_id
        # We need the volume to close. Let's find it. 
        # Actually, cTrader Open API v2 ProtoOAClosePositionReq closes the WHOLE position if volume not specified.
        # But for safety, we should fetch it or just send the request.
        
        try:
            await self.client.send(req)
            self.logger.info(f"Close request sent for {position_id}")
        except Exception as e:
            self.logger.error(f"Failed to close position {position_id}: {e}")

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
