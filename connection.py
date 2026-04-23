import asyncio
import struct
import websockets
import time
import logging
import httpx
from typing import Dict, Optional, Callable, List
from google.protobuf.message import Message
from openapi_pb2 import OpenApiCommonMessages_pb2 as common
from openapi_pb2 import OpenApiMessages_pb2 as oa
from openapi_pb2 import OpenApiModelMessages_pb2 as model
from openapi_pb2 import OpenApiCommonModelMessages_pb2 as common_model
from openapi_pb2 import OpenApiModelMessages_pb2 as model

HEARTBEAT_EVENT = common.ProtoHeartbeatEvent().payloadType
COMMON_ERROR_RES = common.ProtoErrorRes().payloadType

class CTraderClient:
    def __init__(self, host: str, port: int, client_id: str, client_secret: str, access_token: str, refresh_token: str = None):
        self.uri = f"wss://{host}:{port}"
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
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
        self.logger.info("ð Connecting to cTrader...")
        max_retries = 3
        retry_count = 0
        retry_delay = 2
        
        import ssl
        import certifi
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        while retry_count < max_retries:
            try:
                self.ws = await websockets.connect(self.uri, ping_interval=None, ssl=ssl_context) # We handle heartbeats manually
                self.is_connected = True
                self.last_msg_time = time.time()
                self.read_task = asyncio.create_task(self._read_loop())
                self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                self.watchdog_task = asyncio.create_task(self._watchdog_loop())
                self.logger.info("✅ Connected successfully.")
                return True
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    self.logger.warning(f"⚠️ Connection attempt {retry_count} failed: {e}. Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 10)  # Exponential backoff up to 10s
                else:
                    self.logger.error(f"❌ Connection failed after {max_retries} attempts: {e}")
                    return False

    async def disconnect(self):
        self.is_connected = False
        self.logger.debug("Disconnecting...")
        tasks = [self.heartbeat_task, self.read_task, self.watchdog_task]
        for task in tasks:
            if task:
                try:
                    task.cancel()
                except Exception as e:
                    self.logger.debug(f"Error cancelling task: {e}")
        
        if self.ws:
            try:
                await self.ws.close()
            except Exception as e:
                self.logger.debug(f"Error closing websocket: {e}")
        self.logger.debug("Disconnected.")

    def _pack_message(self, message: Message, client_msg_id: Optional[str] = None) -> bytes:
        proto_msg = common.ProtoMessage()
        if hasattr(message, "payloadType"):
            proto_msg.payloadType = message.payloadType
        else:
            # For common messages that don't have payloadType field in the message itself
            if isinstance(message, common.ProtoHeartbeatEvent):
                proto_msg.payloadType = HEARTBEAT_EVENT
        
        proto_msg.payload = message.SerializeToString()
        if client_msg_id:
            proto_msg.clientMsgId = client_msg_id
        
        return proto_msg.SerializeToString()

    async def send(self, message: Message, client_msg_id: Optional[str] = None):
        try:
            if not self.ws or not self.is_connected:
                raise ConnectionError("Not connected to cTrader API")
            data = self._pack_message(message, client_msg_id)
            await self.ws.send(data)
        except ConnectionError as e:
            self.logger.error(f"❌ Connection error while sending: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Error sending message: {e}")
            raise

    async def _read_loop(self):
        try:
            async for message in self.ws:
                if not self.is_connected: break
                
                try:
                    self.last_msg_time = time.time()
                    if isinstance(message, bytes):
                        proto_msg = common.ProtoMessage()
                        proto_msg.ParseFromString(message)
                        await self._handle_message(proto_msg)
                except Exception as e:
                    self.logger.error(f"❌ Error processing message: {e}")
                    # Continue processing despite individual message errors
                    continue
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"❌ Read loop error: {e}")
            asyncio.create_task(self.disconnect())

    async def _handle_message(self, proto_msg: common.ProtoMessage):
        payload_type = proto_msg.payloadType
        self.logger.debug(f"Received payload: {payload_type} ({len(proto_msg.payload)} bytes)")
        
        if payload_type in self.callbacks:
            for cb in self.callbacks[payload_type]:
                asyncio.create_task(cb(proto_msg))
        
        # Internal handling
        if payload_type == HEARTBEAT_EVENT:
            pass
        elif payload_type == model.PROTO_OA_ERROR_RES:
            err = oa.ProtoOAErrorRes()
            err.ParseFromString(proto_msg.payload)
            self.logger.debug(f"API Error: {err.errorCode} - {err.description}")
        elif payload_type == COMMON_ERROR_RES:
            err = common.ProtoErrorRes()
            err.ParseFromString(proto_msg.payload)
            self.logger.debug(f"Common Error: {err.errorCode} - {err.description}")

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
            
        client_msg_id = f"ord_{int(time.time()*1000)}"
        self.logger.debug(f"Placing {side} order: {volume}u SL={sl_pips} TP={tp_pips} ID={client_msg_id}")
        return await self.request(req, model.PROTO_OA_EXECUTION_EVENT, client_msg_id=client_msg_id)

    async def request(self, req: Message, response_type: int, client_msg_id: Optional[str] = None) -> common.ProtoMessage:
        future = asyncio.get_running_loop().create_future()
        
        async def callback(msg):
            # If client_msg_id is provided, we should ideally match it.
            # For now, we accept any message of the expected type if it's the first one.
            if not future.done():
                if client_msg_id and hasattr(msg, 'clientMsgId') and msg.clientMsgId != client_msg_id:
                    return # Not our response
                future.set_result(msg)

        async def error_callback(msg):
            if not future.done():
                err = oa.ProtoOAErrorRes()
                err.ParseFromString(msg.payload)
                # Only set exception if it matches our clientMsgId (if possible)
                if client_msg_id and hasattr(msg, 'clientMsgId') and msg.clientMsgId != client_msg_id:
                    return
                future.set_exception(RuntimeError(f"API Error: {err.errorCode} - {err.description}"))

        async def common_error_callback(msg):
            if not future.done():
                err = common.ProtoErrorRes()
                err.ParseFromString(msg.payload)
                if client_msg_id and hasattr(msg, 'clientMsgId') and msg.clientMsgId != client_msg_id:
                    return
                future.set_exception(RuntimeError(f"Common Error: {err.errorCode} - {err.description}"))
                
        async def order_error_callback(msg):
            if not future.done():
                err = oa.ProtoOAOrderErrorEvent()
                err.ParseFromString(msg.payload)
                if client_msg_id and hasattr(msg, 'clientMsgId') and msg.clientMsgId != client_msg_id:
                    return
                future.set_exception(RuntimeError(f"Order Error: {err.errorCode} - {err.description}"))
                
        self.add_callback(response_type, callback)
        self.add_callback(model.PROTO_OA_ERROR_RES, error_callback)
        self.add_callback(COMMON_ERROR_RES, common_error_callback)
        self.add_callback(model.PROTO_OA_ORDER_ERROR_EVENT, order_error_callback)
        
        req_name = type(req).__name__
        self.logger.debug(f"Sending {req_name} (ID: {client_msg_id or 'None'})...")
        
        try:
            await self.send(req, client_msg_id=client_msg_id)
        except Exception as e:
            self.logger.error(f"❌ Failed to send request {req_name}: {e}")
            raise
            
        try:
            # Increase timeout to 15s for execution events which can be slower
            return await asyncio.wait_for(future, timeout=15)
        except asyncio.TimeoutError:
            self.logger.error(f"❌ Request timeout ({req_name}) after 15s. ID: {client_msg_id}")
            raise
        except Exception as e:
            self.logger.debug(f"Request failed: {req_name} - {e}")
            raise
        finally:
            try:
                if callback in self.callbacks.get(response_type, []):
                    self.callbacks[response_type].remove(callback)
                if error_callback in self.callbacks.get(model.PROTO_OA_ERROR_RES, []):
                    self.callbacks[model.PROTO_OA_ERROR_RES].remove(error_callback)
                if common_error_callback in self.callbacks.get(COMMON_ERROR_RES, []):
                    self.callbacks[COMMON_ERROR_RES].remove(common_error_callback)
                if order_error_callback in self.callbacks.get(model.PROTO_OA_ORDER_ERROR_EVENT, []):
                    self.callbacks[model.PROTO_OA_ORDER_ERROR_EVENT].remove(order_error_callback)
            except Exception as e:
                self.logger.debug(f"Error cleaning up callbacks: {e}")

    async def fetch_accounts_rest(self):
        """Fetch all linked trading accounts via Spotware REST API"""
        url = f"https://api.spotware.com/connect/tradingaccounts?access_token={self.access_token}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if "data" not in data:
                raise ValueError("Unexpected REST API response format")
            return data["data"]

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
        try:
            msg = await self.request(req, model.PROTO_OA_ACCOUNT_AUTH_RES)
        except RuntimeError as e:
            if "CH_ACCESS_TOKEN_INVALID" in str(e) and self.refresh_token:
                await self.refresh_token_call()
                req.accessToken = self.access_token
                msg = await self.request(req, model.PROTO_OA_ACCOUNT_AUTH_RES)
            else:
                raise
        res = oa.ProtoOAAccountAuthRes()
        res.ParseFromString(msg.payload)
        return res

    async def refresh_token_call(self):
        """Refresh the access token using the refresh token"""
        if not self.refresh_token:
            raise ValueError("Refresh token not provided")
            
        self.logger.info("🔄 Refreshing access token...")
        req = oa.ProtoOARefreshTokenReq()
        req.refreshToken = self.refresh_token
        msg = await self.request(req, model.PROTO_OA_REFRESH_TOKEN_RES)
        res = oa.ProtoOARefreshTokenRes()
        res.ParseFromString(msg.payload)
        
        self.access_token = res.accessToken
        self.refresh_token = res.refreshToken
        self.logger.info("✅ Token refreshed successfully.")
        
        # Notify that token has changed (to be saved by caller)
        if hasattr(self, 'on_token_refreshed') and self.on_token_refreshed:
            await self.on_token_refreshed(self.access_token, self.refresh_token)
            
        return res

    async def get_account_list(self):
        req = oa.ProtoOAGetAccountListByAccessTokenReq()
        req.accessToken = self.access_token
        msg = await self.request(req, model.PROTO_OA_GET_ACCOUNTS_BY_ACCESS_TOKEN_RES)
        res = oa.ProtoOAGetAccountListByAccessTokenRes()
        res.ParseFromString(msg.payload)
        return res

    async def get_trader_info(self, account_id: int):
        req = oa.ProtoOATraderReq()
        req.ctidTraderAccountId = account_id
        msg = await self.request(req, model.PROTO_OA_TRADER_RES)
        res = oa.ProtoOATraderRes()
        res.ParseFromString(msg.payload)
        return res

    async def reconcile_account(self, account_id: int):
        """Fetch open positions and current margin info"""
        req = oa.ProtoOAReconcileReq()
        req.ctidTraderAccountId = account_id
        msg = await self.request(req, model.PROTO_OA_RECONCILE_RES)
        res = oa.ProtoOAReconcileRes()
        res.ParseFromString(msg.payload)
        return res

    async def get_symbols_list(self, account_id: int):
        req = oa.ProtoOASymbolsListReq()
        req.ctidTraderAccountId = account_id
        req.includeArchivedSymbols = False
        msg = await self.request(req, model.PROTO_OA_SYMBOLS_LIST_RES)
        res = oa.ProtoOASymbolsListRes()
        res.ParseFromString(msg.payload)
        return res