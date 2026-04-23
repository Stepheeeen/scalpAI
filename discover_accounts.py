#!/usr/bin/env python3
"""
Discover cTrader accounts available with your API credentials.
Run this to see which account IDs you can use in CTRADER_ACCOUNT_ID.
"""
import asyncio
import logging
from config_loader import Config
from connection import CTraderClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AccountDiscovery")

async def discover():
    """Connect and discover available accounts"""
    logger.info("🔍 Discovering available cTrader accounts...")
    
    config = Config()
    client = CTraderClient(
        config.host,
        config.port,
        config.client_id,
        config.client_secret,
        config.access_token
    )
    
    try:
        if not await client.connect():
            logger.error("❌ Failed to connect to cTrader API")
            return
        
        logger.info("✅ Connected to cTrader API")
        
        # Authenticate application first
        logger.info("🔐 Authenticating application...")
        await client.authenticate_application()
        logger.info("✅ Application authenticated")
        
        # Get account list
        logger.info("📋 Requesting account list...")
        account_list_resp = await client.get_account_list()
        
        if not account_list_resp.ctidTraderAccount:
            logger.warning("⚠️ No accounts found")
            return
        
        logger.info("\n" + "="*60)
        logger.info("📋 AVAILABLE ACCOUNTS:")
        logger.info("="*60)
        
        for account in account_list_resp.ctidTraderAccount:
            acc_id = account.ctidTraderAccountId
            broker = account.brokerName if hasattr(account, 'brokerName') else 'Unknown'
            logger.info(f"  • Account ID: {acc_id}")
            logger.info(f"    Broker: {broker}")
            logger.info(f"    Type: {'Live' if account.isLive else 'Demo'}")
            logger.info("")
        
        logger.info("="*60)
        if account_list_resp.ctidTraderAccount:
            first_id = account_list_resp.ctidTraderAccount[0].ctidTraderAccountId
            logger.info(f"\n✅ Update your .env file:")
            logger.info(f"   CTRADER_ACCOUNT_ID={first_id}")
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
    finally:
        await client.disconnect()

async def main():
    await discover()

if __name__ == "__main__":
    asyncio.run(main())

