import requests
import time

COINS = ["bitcoin", "ethereum", "solana"]
URL = "https://api.coingecko.com/api/v3/simple/price?ids={}&vs_currencies=usd"

start = time.time()
for coin in COINS:
    r = requests.get(URL.format(coin))
    print(f"{coin}: {r.json()}")
print(f"Total time: {time.time() - start:.2f}s")
