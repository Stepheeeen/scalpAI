#!/usr/bin/env python3
"""
cTrader API Authentication Diagnostic Tool
Run this to identify which part of the auth chain is failing
"""
import asyncio
import os
import sys
import logging
from dotenv import load_dotenv

# Add parent dir to path
sys.path.insert(0, '/root/scalpAI')

from config_loader import Config
from connection import CTraderClient

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("AuthDiagnostic")

async def diagnose():
    """Run diagnostic tests"""
    logger.info("="*70)
    logger.info("cTRADER API AUTHENTICATION DIAGNOSTIC")
    logger.info("="*70)
    
    # Step 1: Check environment variables
    logger.info("\n[STEP 1] Checking environment variables...")
    load_dotenv()
    
    checks = {
        "CTRADER_CLIENT_ID": os.getenv("CTRADER_CLIENT_ID"),
        "CTRADER_CLIENT_SECRET": os.getenv("CTRADER_CLIENT_SECRET"),
        "CTRADER_ACCESS_TOKEN": os.getenv("CTRADER_ACCESS_TOKEN"),
        "CTRADER_REFRESH_TOKEN": os.getenv("CTRADER_REFRESH_TOKEN"),
        "CTRADER_ACCOUNT_ID": os.getenv("CTRADER_ACCOUNT_ID"),
        "BOT_ENVIRONMENT": os.getenv("BOT_ENVIRONMENT", "NOT SET (defaults to DEMO)"),
    }
    
    for key, value in checks.items():
        status = "✓" if value else "✗"
        display_val = value[:20] + "..." if value and len(value) > 20 else value
        logger.info(f"  {status} {key}: {display_val}")
        if key == "CTRADER_REFRESH_TOKEN" and not value:
            logger.error(f"     ⚠️ CRITICAL: {key} is missing!")
            logger.error(f"        This will cause token refresh to FAIL")
            logger.error(f"        Check if 'REFRESH_TOKEN' (wrong name) exists instead")
    
    # Step 2: Load configuration
    logger.info("\n[STEP 2] Loading configuration...")
    try:
        config = Config()
        config.validate()
        logger.info(f"  ✓ Configuration loaded successfully")
        logger.info(f"    - Host: {config.host}")
        logger.info(f"    - Port: {config.port}")
        logger.info(f"    - Bot Environment: {config.bot_env}")
    except Exception as e:
        logger.error(f"  ✗ Configuration failed: {e}")
        return False
    
    # Step 3: Create client
    logger.info("\n[STEP 3] Creating cTrader client...")
    try:
        client = CTraderClient(
            config.host,
            config.port,
            config.client_id,
            config.client_secret,
            config.access_token,
            config.refresh_token
        )
        logger.info(f"  ✓ Client created")
        logger.info(f"    - Refresh token available: {client.refresh_token is not None}")
    except Exception as e:
        logger.error(f"  ✗ Client creation failed: {e}")
        return False
    
    # Step 4: Connect
    logger.info("\n[STEP 4] Connecting to cTrader API...")
    try:
        if not await client.connect():
            logger.error(f"  ✗ Connection failed (see errors above)")
            return False
        logger.info(f"  ✓ Connected successfully")
    except Exception as e:
        logger.error(f"  ✗ Connection error: {e}")
        return False
    
    # Step 5: Authenticate application
    logger.info("\n[STEP 5] Authenticating application...")
    try:
        res = await client.authenticate_application()
        logger.info(f"  ✓ Application authenticated")
    except Exception as e:
        logger.error(f"  ✗ Application auth failed: {e}")
        if "CH_CLIENT_AUTH_FAILURE" in str(e):
            logger.error(f"    → Check CTRADER_CLIENT_ID and CTRADER_CLIENT_SECRET")
        elif "CH_CLIENT_NOT_AUTHENTICATED" in str(e):
            logger.error(f"    → Client not properly initialized")
        await client.disconnect()
        return False
    
    # Step 6: Get account list
    logger.info("\n[STEP 6] Getting account list...")
    try:
        account_list = await client.get_account_list()
        accounts = account_list.ctidTraderAccount
        logger.info(f"  ✓ Got account list ({len(accounts)} accounts)")
        
        if not accounts:
            logger.warning(f"  ⚠️ No accounts returned by API!")
            logger.warning(f"    → This usually means token doesn't have access to any accounts")
            logger.warning(f"    → Check: Is the token valid? Has it been revoked?")
        
        for i, acc in enumerate(accounts):
            acc_type = "LIVE" if acc.isLive else "DEMO"
            logger.info(f"    [{i}] Account {acc.ctidTraderAccountId} ({acc_type})")
            
    except Exception as e:
        logger.error(f"  ✗ Get account list failed: {e}")
        if "CH_ACCESS_TOKEN_INVALID" in str(e):
            logger.error(f"    → Access token is invalid or expired")
            logger.error(f"    → Attempting automatic refresh...")
            try:
                if client.refresh_token:
                    await client.refresh_token_call()
                    logger.info(f"    → Token refreshed successfully!")
                    logger.info(f"    → Updated token: {client.access_token[:20]}...")
                    logger.warning(f"    → Make sure to save new token to .env file!")
                    # Retry
                    account_list = await client.get_account_list()
                    logger.info(f"  ✓ Got account list after refresh")
                else:
                    logger.error(f"    → No refresh token available - cannot auto-recover")
            except Exception as e2:
                logger.error(f"    → Token refresh also failed: {e2}")
        await client.disconnect()
        return False
    
    # Step 7: Test account authorization
    if accounts:
        # Use configured account or first one
        target_account = None
        if config.account_id:
            target_account = next(
                (a for a in accounts if str(a.ctidTraderAccountId) == str(config.account_id)),
                None
            )
            if not target_account:
                logger.warning(f"  ⚠️ Configured account {config.account_id} not found in returned list!")
        else:
            target_account = accounts[0]
        
        logger.info(f"\n[STEP 7] Testing account authorization...")
        logger.info(f"  Testing account: {target_account.ctidTraderAccountId}")
        logger.info(f"  Account type: {'LIVE' if target_account.isLive else 'DEMO'}")
        logger.info(f"  Bot environment: {config.bot_env}")
        
        try:
            res = await client.authenticate_account(target_account.ctidTraderAccountId)
            logger.info(f"  ✓ Account authorized successfully")
            
            # Try to get trader info
            logger.info(f"\n[STEP 8] Getting trader information...")
            trader_res = await client.get_trader_info(target_account.ctidTraderAccountId)
            trader = trader_res.trader
            
            m_digits = trader.moneyDigits if hasattr(trader, 'moneyDigits') else 2
            balance = trader.balance / (10 ** m_digits)
            can_trade = getattr(trader, 'canTrade', False)
            access_rights = getattr(trader, 'accessRights', None)
            
            logger.info(f"  ✓ Trader information retrieved")
            logger.info(f"    - Balance: {balance:,.2f}")
            logger.info(f"    - Can trade: {can_trade}")
            logger.info(f"    - Access rights: {access_rights}")
            logger.info(f"    - Broker: {getattr(trader, 'brokerName', 'Unknown')}")
            logger.info(f"    - Trader login: {getattr(trader, 'traderLogin', 'Unknown')}")
            
            if not can_trade:
                logger.warning(f"  ⚠️ This token has VIEW-ONLY access (cannot trade)")
            
        except Exception as e:
            logger.error(f"  ✗ Account auth or trader info failed: {e}")
            if "not authorized" in str(e).lower():
                logger.error(f"    → Account is not authorized for this token")
                logger.error(f"    → SOLUTION: Link account in cTrader web portal:")
                logger.error(f"               1. Go to cTrader web portal")
                logger.error(f"               2. Settings → API Apps")
                logger.error(f"               3. Find your app")
                logger.error(f"               4. Grant permission to this trading account")
            elif "CH_CTID_TRADER_ACCOUNT_NOT_FOUND" in str(e):
                logger.error(f"    → Account ID doesn't exist in cTrader system")
                logger.error(f"    → Check if CTRADER_ACCOUNT_ID value is correct")
    
    await client.disconnect()
    logger.info(f"\n[SUMMARY] Diagnostic complete")
    logger.info("="*70)
    return True

if __name__ == "__main__":
    result = asyncio.run(diagnose())
    sys.exit(0 if result else 1)
