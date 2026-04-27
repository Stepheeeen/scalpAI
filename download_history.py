import asyncio
import os
import sys
import time
import logging
from datetime import datetime, timedelta
import pandas as pd

from config_loader import Config
from connection import CTraderClient
from openapi_pb2 import OpenApiMessages_pb2 as oa
from openapi_pb2 import OpenApiModelMessages_pb2 as model

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DownloadHistory")

async def main():
    config = Config()
    config.validate()
    
    client = CTraderClient(
        config.host, config.port, config.client_id, config.client_secret, 
        config.access_token, config.refresh_token
    )
    
    logger.info("Connecting to cTrader...")
    if not await client.connect():
        logger.error("Failed to connect")
        return
        
    await client.authenticate_application()
    
    # Use Websocket API instead of REST API to avoid timeouts
    accounts_res = await client.get_account_list()
    env_is_live = (config.bot_env == "LIVE")
    
    matched_accounts = []
    for acc in accounts_res.ctidTraderAccount:
        if hasattr(acc, 'isLive') and acc.isLive == env_is_live:
            matched_accounts.append(acc)
    
    if not matched_accounts:
        logger.error("No valid account found")
        return
        
    account_id = matched_accounts[0].ctidTraderAccountId
    logger.info(f"Authenticating account {account_id}...")
    await client.authenticate_account(account_id)
    
    logger.info(f"Fetching symbol ID for {config.symbol_name}...")
    sym_res = await client.get_symbols_list(account_id)
    symbol_id = None
    for sym in sym_res.symbol:
        if sym.symbolName == config.symbol_name:
            symbol_id = sym.symbolId
            break
            
    if not symbol_id:
        logger.error(f"Symbol {config.symbol_name} not found")
        return
        
    logger.info(f"Symbol ID: {symbol_id}")
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=5) # 5 days of tick data
    
    current_end = end_time
    all_bids = []
    
    # Download BID ticks
    logger.info("Downloading BID ticks...")
    while current_end > start_time:
        current_start = current_end - timedelta(hours=12) # 12 hour chunks
        
        req = oa.ProtoOAGetTickDataReq()
        req.ctidTraderAccountId = account_id
        req.symbolId = symbol_id
        req.type = model.BID
        req.fromTimestamp = int(current_start.timestamp() * 1000)
        req.toTimestamp = int(current_end.timestamp() * 1000)
        
        try:
            logger.info(f"Fetching BIDs from {current_start.strftime('%Y-%m-%d %H:%M')} to {current_end.strftime('%Y-%m-%d %H:%M')}...")
            res_msg = await client.request(req, model.PROTO_OA_GET_TICKDATA_RES)
            res = oa.ProtoOAGetTickDataRes()
            res.ParseFromString(res_msg.payload)
            
            divisor = 100000.0
            for tb in res.tickData:
                all_bids.append({
                    "timestamp": tb.timestamp,
                    "bid": tb.tick / divisor
                })
                
        except Exception as e:
            logger.error(f"Error fetching chunk: {e}")
            break
            
        current_end = current_start
        await asyncio.sleep(1)
        
    current_end = end_time
    all_asks = []
    
    # Download ASK ticks
    logger.info("Downloading ASK ticks...")
    while current_end > start_time:
        current_start = current_end - timedelta(hours=12)
        
        req = oa.ProtoOAGetTickDataReq()
        req.ctidTraderAccountId = account_id
        req.symbolId = symbol_id
        req.type = model.ASK
        req.fromTimestamp = int(current_start.timestamp() * 1000)
        req.toTimestamp = int(current_end.timestamp() * 1000)
        
        try:
            logger.info(f"Fetching ASKs from {current_start.strftime('%Y-%m-%d %H:%M')} to {current_end.strftime('%Y-%m-%d %H:%M')}...")
            res_msg = await client.request(req, model.PROTO_OA_GET_TICKDATA_RES)
            res = oa.ProtoOAGetTickDataRes()
            res.ParseFromString(res_msg.payload)
            
            divisor = 100000.0
            for tb in res.tickData:
                all_asks.append({
                    "timestamp": tb.timestamp,
                    "ask": tb.tick / divisor
                })
                
        except Exception as e:
            logger.error(f"Error fetching chunk: {e}")
            break
            
        current_end = current_start
        await asyncio.sleep(1)
        
    await client.disconnect()
    
    if not all_bids or not all_asks:
        logger.error("No data fetched")
        return
        
    logger.info("Merging BID and ASK ticks...")
    df_bids = pd.DataFrame(all_bids)
    df_asks = pd.DataFrame(all_asks)
    
    # Merge as of nearest timestamp since bids and asks might not perfectly align
    df_bids = df_bids.sort_values(by="timestamp")
    df_asks = df_asks.sort_values(by="timestamp")
    
    df = pd.merge_asof(df_bids, df_asks, on="timestamp", direction="nearest")
    df.to_csv("live_gold_data.csv", index=False)
    logger.info(f"✅ Successfully downloaded {len(df)} ticks and saved to live_gold_data.csv")

if __name__ == "__main__":
    asyncio.run(main())
