import asyncio
from adapters.zerodha_adapter import ZerodhaAdapter
from adapters.alpaca_adapter import AlpacaAdapter

async def main():
    brokers= [
        ZerodhaAdapter(api_key="fake_key",access_token="fake_token"),
        AlpacaAdapter(api_key="fake_key",secret_key="fake_secret")
    ]

    for broker in brokers:
        portfolio = await broker.get_portfolio()
        print(f"\nBroker: {portfolio['broker']}")
        print(f"Total value: {portfolio['total_value']}")
        for holding in portfolio["holdings"]:
            print(f"{holding['symbol']} x {holding['qty']} x {holding['current_price']}")

asyncio.run(main())