import asyncio
from adapters.zerodha_adapter import ZerodhaAdapter

async def main():
    broker = ZerodhaAdapter(api_key="fake key",access_token="fake token")

    print("---quote---")
    quote = await broker.get_quote("INFY")
    print(quote)

    print("\n---place order---")
    order = await broker.place_order("INFY",10,"BUY","Market")
    print(order)

    print("\n---Positions---")
    positions = await broker.get_positions()
    print(positions)

    print("\n---portofolio---")
    portfolio = await broker.get_portfolio()
    print(portfolio)

asyncio.run(main())