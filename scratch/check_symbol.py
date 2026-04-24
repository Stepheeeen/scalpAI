import asyncio
import os
from connection import CTraderClient
from openapi_pb2 import OpenApiMessages_pb2 as oa
from openapi_pb2 import OpenApiModelMessages_pb2 as model
from dotenv import load_dotenv

async def get_symbol_details():
    load_dotenv()
    client = CTraderClient(
        os.getenv("CTRADER_HOST", "live.ctraderapi.com"),
        int(os.getenv("CTRADER_PORT", 5035)),
        os.getenv("CTRADER_CLIENT_ID"),
        os.getenv("CTRADER_CLIENT_SECRET"),
        os.getenv("CTRADER_ACCESS_TOKEN")
    )
    
    await client.connect()
    await client.authenticate_application()
    
    # Get accounts
    accounts = await client.fetch_accounts_rest()
    account_id = accounts[0]["accountId"]
    await client.authenticate_account(account_id)
    
    # Get symbol list to find XAUUSD
    symbols_res = await client.get_symbols_list(account_id)
    symbol_id = None
    for s in symbols_res.symbol:
        if s.symbolName == "XAUUSD":
            symbol_id = s.symbolId
            break
            
    if not symbol_id:
        print("XAUUSD not found")
        return

    # Get detailed symbol info
    req = oa.ProtoOASymbolByIdReq()
    req.ctidTraderAccountId = account_id
    req.symbolId.append(symbol_id)
    msg = await client.request(req, model.PROTO_OA_SYMBOL_BY_ID_RES)
    res = oa.ProtoOASymbolByIdRes()
    res.ParseFromString(msg.payload)
    
    symbol = res.symbol[0]
    print(f"Symbol: {symbol.symbolName}")
    print(f"Digits: {symbol.digits}")
    print(f"Pip Size: {symbol.pipSize}")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(get_symbol_details())
