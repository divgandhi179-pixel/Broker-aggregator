import asyncio
import aiohttp
import time

COINS = ["bitcoin", "ethereum", "solana"]
URL = "https://api.coingecko.com/api/v3/simple/price?ids={}&vs_currencies=usd"


async def fetch(session, coin):
    async with session.get(URL.format(coin)) as response:
        data = await response.json()
        print(f"{coin}: {data}")
        return data


async def main():
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            fetch(session, "bitcoin"),
            fetch(session, "ethereum"),
            fetch(session, "solana"),
        )
    print(f"\nAll done. Got {len(results)} prices.")


start = time.time()
asyncio.run(main())
print(f"Total time: {time.time() - start:.2f}s")
