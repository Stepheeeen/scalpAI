import asyncio
import struct
import websockets
import time
import logging
from typing import Dict, Optional, Callable, List
from google.protobuf.message import Message
from openapi_pb2 import OpenApiCommonMessages_pb2 as common
from openapi_pb2 import OpenApiMessages_pb2 as oa
from openapi_pb2 import OpenApiModelMessages_pb2 as model
from openapi_pb2 import OpenApiCommonModelMessages_pb2 as common_model

class CTraderClient:
    def __init__(self, host: str, port: int, client_id: str, client_secret: str, access_token: str):
        self.uri = f"wss://{host}:{port}"
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.callbacks: Dict[int, List[Callable]] = {}
        self.account_id: Optional[int] = None
        
        # Tasks
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.read_task: Optional[asyncio.Task] = None
        self.watchdog_task: Optional[asyncio.Task] = None
        
        # State
        self.is_connected = False
        self.last_msg_time = time.time()
        self.logger = logging.getLogger("CTraderClient")
        
    def add_callback(self, payload_type: int, callback: Callable):
        if payload_type not in self.callbacks:
            self.callbacks[payload_type] = []
        self.callbacks[payload_type].append(callback)

    async def connect(self):
        self.logger.info(f"Connecting to {self.uri}...")
        try:
            self.ws = await websockets.connect(self.uri, ping_interval=None) # We handle heartbeats manually
            self.is_connected = True
            self.last_msg_time = time.time()
            self.read_task = asyncio.create_task(self._read_loop())
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self.watchdog_task = asyncio.create_task(self._watchdog_loop())
            self.logger.info("Connected successfully.")
            return True
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False

    async def disconnect(self):
        self.is_connected = False
        self.logger.info("Disconnecting...")
        tasks = [self.heartbeat_task, self.read_task, self.watchdog_task]
        for task in tasks:
            if task: task.cancel()
        
        if self.ws:
            await self.ws.close()
        self.logger.info("Disconnected.")

    def _pack_message(self, message: Message, client_msg_id: Optional[str] = None) -> bytes:
        proto_msg = common.ProtoMessage()
        if hasattr(message, "payloadType"):
            proto_msg.payloadType = message.payloadType
        else:
            # For common messages that don't have payloadType field in the message itself
            if isinstance(message, common.ProtoHeartbeatEvent):
                proto_msg.payloadType = common.HEARTBEAT_EVENT
        
        proto_msg.payload = message.SerializeToString()
        if client_msg_id:
            proto_msg.clientMsgId = client_msg_id
        
        payload = proto_msg.SerializeToString()
        return struct.pack("<I", len(payload)) + payload

    async def send(self, message: Message, client_msg_id: Optional[str] = None):
        if not self.ws or not self.is_connected:
            raise ConnectionError("Not connected")
        data = self._pack_message(message, client_msg_id)
        await self.ws.send(data)

    async def _read_loop(self):
        try:
            async for message in self.ws:
                if not self.is_connected: break
                
                self.last_msg_time = time.time()
                if isinstance(message, bytes):
                    # Fixed: websockets.recv() returns the full frame if it's binary
                    # but since we are using 'async for', it's the same.
                    # The 4 bytes are prefix, but Websockets might have already handled framing?
                    # No, cTrader uses its own framing OVER the websocket frame or as the full content.
                    # Usually, the whole message received is 4 bytes + payload.
                    
                    length = struct.unpack("<I", message[:4])[0]
                    payload = message[4:]
                    
                    proto_msg = common.ProtoMessage()
                    proto_msg.ParseFromString(payload)
                    await self._handle_message(proto_msg)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Read loop error: {e}")
            asyncio.create_task(self.disconnect())

    async def _handle_message(self, proto_msg: common.ProtoMessage):
        payload_type = proto_msg.payloadType
        
        if payload_type in self.callbacks:
            for cb in self.callbacks[payload_type]:
                asyncio.create_task(cb(proto_msg))
        
        # Internal handling
        if payload_type == common.HEARTBEAT_EVENT:
            pass
        elif payload_type == model.PROTO_OA_ERROR_RES:
            err = oa.ProtoOAErrorRes()
            err.ParseFromString(proto_msg.payload)
            self.logger.error(f"API Error: {err.errorCode} - {err.description}")
        elif payload_type == common.ERROR_RES:
            err = common.ProtoErrorRes()
            err.ParseFromString(proto_msg.payload)
            self.logger.error(f"Common Error: {err.errorCode} - {err.description}")

    async def _heartbeat_loop(self):
        try:
            while self.is_connected:
                await asyncio.sleep(10)
                hb = common.ProtoHeartbeatEvent()
                await self.send(hb)
        except asyncio.CancelledError:
            pass

    async def _watchdog_loop(self):
        try:
            while self.is_connected:
                await asyncio.sleep(5)
                if time.time() - self.last_msg_time > 30:
                    self.logger.warning("No message received for 30s. Triggering reconnect.")
                    await self.disconnect()
                    break
        except asyncio.CancelledError:
            pass

    # High-level API calls
    async def place_market_order(self, account_id: int, symbol_id: int, side: str, volume: int, sl_pips: int = None, tp_pips: int = None):
        req = oa.ProtoOANewOrderReq()
        req.ctidTraderAccountId = account_id
        req.symbolId = symbol_id
        req.orderType = model.MARKET
        req.tradeSide = model.BUY if side.upper() == "BUY" else model.SELL
        req.volume = volume # In 0.01 units
        
        # 1 pip for Gold = 0.01. 
        # relativeStopLoss is in 1/100000 of unit of price.
        # So 1 pip = 0.01 * 100,000 = 1000 units in protocol.
        if sl_pips:
            req.relativeStopLoss = sl_pips * 1000
        if tp_pips:
            req.relativeTakeProfit = tp_pips * 1000
            
        print(f"Sending MARKET {side} for {volume} units...")
        return await self.request(req, model.PROTO_OA_EXECUTION_EVENT)

    async def request(self, req: Message, response_type: int) -> common.ProtoMessage:
        future = asyncio.get_running_loop().create_future()
        
        async def callback(msg):
            if not future.done():
                future.set_result(msg)
                
        self.add_callback(response_type, callback)
        await self.send(req)
        try:
            return await asyncio.wait_for(future, timeout=10)
        finally:
            self.callbacks[response_type].remove(callback)

    async def authenticate_application(self):
        req = oa.ProtoOAApplicationAuthReq()
        req.clientId = self.client_id
        req.clientSecret = self.client_secret
        msg = await self.request(req, model.PROTO_OA_APPLICATION_AUTH_RES)
        res = oa.ProtoOAApplicationAuthRes()
        res.ParseFromString(msg.payload)
        return res

    async def authenticate_account(self, account_id: int):
        self.account_id = account_id
        req = oa.ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = account_id
        req.accessToken = self.access_token
        msg = await self.request(req, model.PROTO_OA_ACCOUNT_AUTH_RES)
        res = oa.ProtoOAAccountAuthRes()
        res.ParseFromString(msg.payload)
        return res
